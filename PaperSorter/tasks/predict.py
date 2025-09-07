#!/usr/bin/env python3
#
# Copyright (c) 2024-2025 Seoul National University
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

from ..feed_database import FeedDatabase
from ..embedding_database import EmbeddingDatabase
from ..feed_predictor import FeedPredictor
from ..log import log, initialize_logging
from ..cli.base import BaseCommand, registry
import xgboost as xgb
import numpy as np
import yaml
import pickle
import argparse
import psycopg2
import psycopg2.extras
from psycopg2.extras import execute_batch
from pgvector.psycopg2 import register_vector


class PredictCommand(BaseCommand):
    """Generate embeddings and predictions for articles."""

    name = 'predict'
    help = 'Generate embeddings and predictions for articles'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add predict-specific arguments."""
        parser.add_argument(
            '--max-papers',
            type=int,
            default=500,
            help='Maximum number of recent papers to process (0 for all)'
        )
        parser.add_argument(
            '--all',
            dest='process_all',
            action='store_true',
            help='Process all papers without limit (equivalent to --max-papers 0)'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Batch size for database operations and embedding generation'
        )

    def handle(self, args: argparse.Namespace, context) -> int:
        """Execute the predict command."""
        initialize_logging('predict', args.log_file, args.quiet)
        try:
            main(
                config=args.config,
                max_papers=args.max_papers,
                process_all=args.process_all,
                batch_size=args.batch_size,
                log_file=args.log_file,
                quiet=args.quiet
            )
            return 0
        except Exception as e:
            log.error(f"Predict failed: {e}")
            return 1

# Register the command
registry.register(PredictCommand)


def generate_embeddings_for_feeds(feed_ids, feeddb, embeddingdb, config_path, batch_size):
    """Generate embeddings using the unified FeedPredictor implementation."""
    if not feed_ids:
        return []

    predictor = FeedPredictor(feeddb, embeddingdb, config_path)
    successful_feeds = predictor.generate_embeddings_batch(feed_ids, batch_size)

    # Return the embeddings for successful feeds
    embeddings = []
    for feed_id in successful_feeds:
        embeddingdb.cursor.execute(
            "SELECT embedding FROM embeddings WHERE feed_id = %s", (feed_id,)
        )
        result = embeddingdb.cursor.fetchone()
        if result:
            embeddings.append({"feed_id": feed_id, "embedding": result["embedding"]})

    return embeddings


def main(config, max_papers, process_all, batch_size, log_file, quiet):
    """Generate embeddings and predictions for articles in the database.

    Creates vector embeddings for articles and optionally generates interest
    predictions using trained models. Essential for semantic search and recommendations.
    """

    # Handle --all flag: set max_papers to 0 to process all papers
    if process_all:
        max_papers = 0

    # Load configuration
    with open(config, "r") as f:
        config_data = yaml.safe_load(f)

    db_config = config_data["db"]

    # Initialize FeedDatabase and EmbeddingDatabase
    feeddb = FeedDatabase(config)
    embeddingdb = EmbeddingDatabase(config)

    # Connect to PostgreSQL
    log.info("Connecting to PostgreSQL database...")
    db = psycopg2.connect(
        host=db_config["host"],
        database=db_config["database"],
        user=db_config["user"],
        password=db_config["password"],
    )
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Register pgvector extension
    register_vector(db)

    # First, get counts of feeds with and without embeddings
    if max_papers == 0:
        # Count all feeds
        cursor.execute("""
            SELECT
                COUNT(*) FILTER (WHERE e.embedding IS NOT NULL) as with_embeddings,
                COUNT(*) FILTER (WHERE e.embedding IS NULL) as without_embeddings
            FROM feeds f
            LEFT JOIN embeddings e ON f.id = e.feed_id
        """)
    else:
        # Count only the most recent 'max_papers' feeds
        cursor.execute("""
            WITH recent_feeds AS (
                SELECT f.id
                FROM feeds f
                ORDER BY f.added DESC
                LIMIT %s
            )
            SELECT
                COUNT(*) FILTER (WHERE e.embedding IS NOT NULL) as with_embeddings,
                COUNT(*) FILTER (WHERE e.embedding IS NULL) as without_embeddings
            FROM recent_feeds rf
            JOIN feeds f ON f.id = rf.id
            LEFT JOIN embeddings e ON f.id = e.feed_id
        """, (max_papers,))

    counts = cursor.fetchone()
    feeds_with_embeddings_count = counts['with_embeddings'] or 0
    feeds_without_embeddings_count = counts['without_embeddings'] or 0

    log.info(f"Found {feeds_with_embeddings_count} feeds with embeddings, {feeds_without_embeddings_count} without embeddings")

    if feeds_without_embeddings_count == 0 and feeds_with_embeddings_count == 0:
        log.info("No papers found")
        return

    if max_papers == 0:
        log.info(f"Processing all papers in batches of {batch_size}...")
    else:
        log.info(f"Processing {max_papers} most recent papers in batches of {batch_size}...")

    # Now process only feeds without embeddings incrementally
    feeds_without_embeddings = []
    feeds_with_embeddings = []  # Will be populated after generating embeddings
    offset = 0

    # Query for feeds without embeddings
    if max_papers == 0:
        # Process all feeds without embeddings
        base_query = """
            SELECT f.*
            FROM feeds f
            WHERE NOT EXISTS (
                SELECT 1 FROM embeddings e WHERE e.feed_id = f.id
            )
            ORDER BY f.added DESC
            LIMIT %s OFFSET %s
        """
    else:
        # Process only from the most recent 'max_papers' feeds
        base_query = """
            WITH recent_feeds AS (
                SELECT f.id
                FROM feeds f
                ORDER BY f.added DESC
                LIMIT %s
            )
            SELECT f.*
            FROM recent_feeds rf
            JOIN feeds f ON f.id = rf.id
            WHERE NOT EXISTS (
                SELECT 1 FROM embeddings e WHERE e.feed_id = f.id
            )
            ORDER BY f.added DESC
            LIMIT %s OFFSET %s
        """

    # Process feeds without embeddings in batches
    while offset < feeds_without_embeddings_count:
        if max_papers == 0:
            cursor.execute(base_query, (batch_size, offset))
        else:
            cursor.execute(base_query, (max_papers, batch_size, offset))

        batch_feeds = cursor.fetchall()

        if not batch_feeds:
            break

        feeds_without_embeddings.extend(batch_feeds)
        offset += len(batch_feeds)

        log.debug(f"Loaded batch of {len(batch_feeds)} feeds without embeddings (total: {len(feeds_without_embeddings)}/{feeds_without_embeddings_count})")

    log.info(
        f"Total papers: {feeds_with_embeddings_count} with embeddings, {feeds_without_embeddings_count} without"
    )

    # If there are feeds with embeddings and we want to run predictions, load them
    if feeds_with_embeddings_count > 0:
        log.info(f"Loading {feeds_with_embeddings_count} feeds with existing embeddings for prediction...")
        offset = 0

        if max_papers == 0:
            # Load all feeds with embeddings
            query_with_embeddings = """
                SELECT f.*, e.embedding
                FROM feeds f
                JOIN embeddings e ON f.id = e.feed_id
                ORDER BY f.added DESC
                LIMIT %s OFFSET %s
            """
        else:
            # Load only from the most recent 'max_papers' feeds
            query_with_embeddings = """
                WITH recent_feeds AS (
                    SELECT f.id
                    FROM feeds f
                    ORDER BY f.added DESC
                    LIMIT %s
                )
                SELECT f.*, e.embedding
                FROM recent_feeds rf
                JOIN feeds f ON f.id = rf.id
                JOIN embeddings e ON f.id = e.feed_id
                ORDER BY f.added DESC
                LIMIT %s OFFSET %s
            """

        # Load feeds with embeddings in batches
        while offset < feeds_with_embeddings_count:
            if max_papers == 0:
                cursor.execute(query_with_embeddings, (batch_size, offset))
            else:
                cursor.execute(query_with_embeddings, (max_papers, batch_size, offset))

            batch_feeds = cursor.fetchall()

            if not batch_feeds:
                break

            feeds_with_embeddings.extend(batch_feeds)
            offset += len(batch_feeds)

            log.debug(f"Loaded batch of {len(batch_feeds)} feeds with embeddings (total: {len(feeds_with_embeddings)}/{feeds_with_embeddings_count})")

    # Generate embeddings for feeds that don't have them
    if feeds_without_embeddings:
        log.info(f"Generating embeddings for {len(feeds_without_embeddings)} papers...")

        # Process embedding generation in batches to avoid overwhelming the API
        feed_ids_without_embeddings = [f["id"] for f in feeds_without_embeddings]

        # Use FeedPredictor to generate embeddings (it handles batching internally)
        all_new_embeddings = generate_embeddings_for_feeds(
            feed_ids_without_embeddings, feeddb, embeddingdb, config, batch_size
        )

        # Add newly embedded feeds to the list
        if all_new_embeddings:
            log.info(f"Successfully generated {len(all_new_embeddings)} embeddings")
            # Create a mapping for faster lookup
            embedding_map = {emb["feed_id"]: emb["embedding"] for emb in all_new_embeddings}

            for feed in feeds_without_embeddings:
                if feed["id"] in embedding_map:
                    feed["embedding"] = embedding_map[feed["id"]]
                    feeds_with_embeddings.append(feed)

    # Get all active models
    log.info("Loading active models...")
    cursor.execute("""
        SELECT m.*, c.name as channel_name
        FROM models m
        LEFT JOIN channels c ON m.id = c.model_id
        WHERE m.is_active = TRUE
        ORDER BY m.id
    """)

    active_models = cursor.fetchall()

    if not active_models:
        log.warning("No active models found")
        cursor.close()
        db.close()
        return

    log.info(f"Found {len(active_models)} active models")

    # Get model directory from config
    model_dir = config_data.get("models", {}).get("path", ".")

    # Prepare embeddings array
    feed_ids = [f["id"] for f in feeds_with_embeddings]
    embeddings = np.array(
        [f["embedding"] for f in feeds_with_embeddings], dtype=np.float64
    )

    # Process predictions for each model
    for model_info in active_models:
        model_id = model_info["id"]
        model_path = f"{model_dir}/model-{model_id}.pkl"
        channel_name = model_info["channel_name"] or f"Model {model_id}"

        log.info(f"Processing model {model_id} ({channel_name})...")

        # Find feeds that don't have predictions for this model
        cursor.execute(
            """
            SELECT feed_id
            FROM predicted_preferences
            WHERE model_id = %s AND feed_id = ANY(%s)
        """,
            (model_id, feed_ids),
        )

        already_predicted = {row["feed_id"] for row in cursor.fetchall()}
        feeds_to_predict = [fid for fid in feed_ids if fid not in already_predicted]

        if not feeds_to_predict:
            log.info(f"All papers already have predictions for model {model_id}")
            continue

        log.info(
            f"Found {len(feeds_to_predict)} papers without predictions for model {model_id}"
        )

        try:
            # Load model
            with open(model_path, "rb") as f:
                model_data = pickle.load(f)

            model = model_data["model"]
            scaler = model_data["scaler"]

            # Get embeddings for feeds that need predictions
            feed_idx_map = {fid: idx for idx, fid in enumerate(feed_ids)}
            predict_indices = [feed_idx_map[fid] for fid in feeds_to_predict]
            embeddings_to_predict = embeddings[predict_indices]

            # Scale embeddings
            embeddings_scaled = scaler.transform(embeddings_to_predict)

            # Create DMatrix for prediction
            dmatrix = xgb.DMatrix(embeddings_scaled)

            # Predict
            predictions = model.predict(dmatrix)

            # Store predictions in database in batches
            log.info(f"Storing {len(predictions)} predictions for model {model_id}...")

            # Use execute_batch for better performance with many predictions
            prediction_data = [
                (feed_id, model_id, float(score))
                for feed_id, score in zip(feeds_to_predict, predictions)
            ]

            execute_batch(
                cursor,
                """
                INSERT INTO predicted_preferences (feed_id, model_id, score)
                VALUES (%s, %s, %s)
                ON CONFLICT (feed_id, model_id) DO UPDATE
                SET score = EXCLUDED.score
                """,
                prediction_data,
                page_size=min(1000, batch_size)  # Use batch_size for consistency
            )

            db.commit()

            # Log summary statistics
            log.info(
                f"Model {model_id} predictions: min={predictions.min():.3f}, max={predictions.max():.3f}, mean={predictions.mean():.3f}"
            )

        except Exception as e:
            log.error(f"Failed to process model {model_id}: {e}")
            continue

    # Close database connection
    cursor.close()
    db.close()

    log.info("Prediction task completed")
