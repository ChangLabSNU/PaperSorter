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
import xgboost as xgb
import numpy as np
import click
import pickle
import psycopg2
import psycopg2.extras
from psycopg2.extras import execute_batch
from pgvector.psycopg2 import register_vector
import yaml


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


@click.option(
    "--config", "-c", default="./config.yml", help="Database configuration file."
)
@click.option("--count", default=500, help="Number of recent feeds to process.")
@click.option("--batch-size", default=500, help="Batch size for database operations and embedding generation.")
@click.option("--log-file", default=None, help="Log file.")
@click.option("-q", "--quiet", is_flag=True, help="Suppress log output.")
def main(config, count, batch_size, log_file, quiet):
    """Generate embeddings and predictions for articles in the database.

    Creates vector embeddings for articles and optionally generates interest
    predictions using trained models. Essential for semantic search and recommendations.
    """
    initialize_logging(task="predict", logfile=log_file, quiet=quiet)

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

    # Process feeds in batches to avoid memory issues
    log.info(f"Processing {count} most recent feeds in batches of {batch_size}...")

    feeds_with_embeddings = []
    feeds_without_embeddings = []
    total_processed = 0

    # Process in batches using OFFSET and LIMIT
    for offset in range(0, count, batch_size):
        current_batch_size = min(batch_size, count - offset)

        cursor.execute(
            """
            SELECT f.*, e.embedding
            FROM feeds f
            LEFT JOIN embeddings e ON f.id = e.feed_id
            ORDER BY f.added DESC
            LIMIT %s OFFSET %s
        """,
            (current_batch_size, offset),
        )

        batch_feeds = cursor.fetchall()

        if not batch_feeds:
            break

        # Separate feeds with and without embeddings for this batch
        for feed in batch_feeds:
            if feed["embedding"] is None:
                feeds_without_embeddings.append(feed)
            else:
                feeds_with_embeddings.append(feed)

        total_processed += len(batch_feeds)

        if len(batch_feeds) < current_batch_size:
            # No more feeds available
            break

    if total_processed == 0:
        log.info("No feeds found")
        return

    log.info(
        f"Processed {total_processed} feeds: {len(feeds_with_embeddings)} with embeddings, {len(feeds_without_embeddings)} without"
    )

    # Generate embeddings for feeds that don't have them
    if feeds_without_embeddings:
        log.info(f"Generating embeddings for {len(feeds_without_embeddings)} feeds...")

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
            log.info(f"All feeds already have predictions for model {model_id}")
            continue

        log.info(
            f"Found {len(feeds_to_predict)} feeds without predictions for model {model_id}"
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
