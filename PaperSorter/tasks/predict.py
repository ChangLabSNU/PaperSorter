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
from ..config import get_config
import pickle
import argparse
import psycopg2
import psycopg2.extras
from psycopg2.extras import execute_batch
from pgvector.psycopg2 import register_vector
from typing import Dict, List, Sequence, Tuple


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
            '--embedding-batch',
            type=int,
            default=100,
            help='Batch size for embedding generation'
        )
        parser.add_argument(
            '--prediction-batch',
            type=int,
            default=2000,
            help='Batch size for model prediction writes'
        )

    def handle(self, args: argparse.Namespace, context) -> int:
        """Execute the predict command."""
        initialize_logging('predict', args.log_file, args.quiet)
        try:
            main(
                config=args.config,
                max_papers=args.max_papers,
                process_all=args.process_all,
                embedding_batch=args.embedding_batch,
                prediction_batch=args.prediction_batch,
                log_file=args.log_file,
                quiet=args.quiet
            )
            return 0
        except KeyboardInterrupt:
            log.warning("Interrupted by user; exiting predict cleanly.")
            return 130
        except Exception as e:
            log.error(f"Predict failed: {e}")
            return 1

# Register the command
registry.register(PredictCommand)


def generate_embeddings_for_feeds(feed_ids, feeddb, embeddingdb, batch_size):
    """Generate embeddings using the unified FeedPredictor implementation."""
    if not feed_ids:
        return []

    predictor = FeedPredictor(feeddb, embeddingdb)
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


def _load_config() -> Dict:
    """Load config using centralized singleton."""
    return get_config().raw


def _connect_postgres(db_cfg: Dict) -> Tuple[psycopg2.extensions.connection, psycopg2.extensions.cursor]:
    """Connect to PostgreSQL and return connection and RealDictCursor with pgvector registered."""
    db = psycopg2.connect(
        host=db_cfg["host"],
        database=db_cfg["database"],
        user=db_cfg["user"],
        password=db_cfg["password"],
    )
    register_vector(db)
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return db, cursor


def _count_feeds(cursor, max_papers: int) -> Tuple[int, int]:
    """Return counts of feeds with and without embeddings based on max_papers window."""
    if max_papers == 0:
        cursor.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE e.embedding IS NOT NULL) as with_embeddings,
                COUNT(*) FILTER (WHERE e.embedding IS NULL) as without_embeddings
            FROM feeds f
            LEFT JOIN embeddings e ON f.id = e.feed_id
            """
        )
    else:
        cursor.execute(
            """
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
            """,
            (max_papers,),
        )

    counts = cursor.fetchone() or {}
    return (counts.get("with_embeddings") or 0, counts.get("without_embeddings") or 0)


def _query_without_embeddings(max_papers: int) -> str:
    if max_papers == 0:
        return (
            """
            SELECT f.*
            FROM feeds f
            WHERE NOT EXISTS (
                SELECT 1 FROM embeddings e WHERE e.feed_id = f.id
            )
            ORDER BY f.added DESC
            LIMIT %s OFFSET %s
            """
        )
    return (
        """
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
    )


def _query_with_embeddings(max_papers: int) -> str:
    if max_papers == 0:
        return (
            """
            SELECT f.*, e.embedding
            FROM feeds f
            JOIN embeddings e ON f.id = e.feed_id
            ORDER BY f.added DESC
            LIMIT %s OFFSET %s
            """
        )
    return (
        """
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
    )


def _query_embeddings_for_prediction_no_offset(max_papers: int) -> str:
    """Query rows that have embeddings and no prediction for the given model (no OFFSET)."""
    if max_papers == 0:
        return (
            """
            SELECT f.id, e.embedding
            FROM feeds f
            JOIN embeddings e ON f.id = e.feed_id
            WHERE NOT EXISTS (
                SELECT 1 FROM predicted_preferences pp
                WHERE pp.feed_id = f.id AND pp.model_id = %s
            )
            ORDER BY f.added DESC
            LIMIT %s
            """
        )
    return (
        """
        WITH recent_feeds AS (
            SELECT f.id
            FROM feeds f
            ORDER BY f.added DESC
            LIMIT %s
        )
        SELECT f.id, e.embedding
        FROM recent_feeds rf
        JOIN feeds f ON f.id = rf.id
        JOIN embeddings e ON f.id = e.feed_id
        WHERE NOT EXISTS (
            SELECT 1 FROM predicted_preferences pp
            WHERE pp.feed_id = f.id AND pp.model_id = %s
        )
        ORDER BY f.added DESC
        LIMIT %s
        """
    )


def _query_without_embeddings_no_offset(max_papers: int) -> str:
    if max_papers == 0:
        return (
            """
            SELECT f.*
            FROM feeds f
            WHERE NOT EXISTS (
                SELECT 1 FROM embeddings e WHERE e.feed_id = f.id
            )
            ORDER BY f.added DESC
            LIMIT %s
            """
        )
    return (
        """
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
        LIMIT %s
        """
    )


def _generate_missing_embeddings_stream(
    cursor,
    max_papers: int,
    feeds_without_count: int,
    embedding_batch: int,
    feeddb: FeedDatabase,
    embeddingdb: EmbeddingDatabase,
) -> None:
    """Stream through feeds missing embeddings and generate them in batches without caching in memory."""
    query = _query_without_embeddings_no_offset(max_papers)
    processed = 0
    while processed < feeds_without_count:
        if max_papers == 0:
            cursor.execute(query, (embedding_batch,))
        else:
            cursor.execute(query, (max_papers, embedding_batch))
        batch = cursor.fetchall()
        if not batch:
            break

        feed_ids = [row["id"] for row in batch]
        _ = generate_embeddings_for_feeds(feed_ids, feeddb, embeddingdb, embedding_batch)

        processed += len(batch)
        remaining = max(0, feeds_without_count - processed)
        pct = (processed / feeds_without_count * 100.0) if feeds_without_count else 100.0
        log.info(
            f"Embeddings progress: {processed}/{feeds_without_count} ({pct:.1f}%), remaining={remaining}"
        )


def _load_active_models(cursor) -> List[Dict]:
    """Return all active models independent of channels."""
    cursor.execute(
        """
        SELECT m.*
        FROM models m
        WHERE m.is_active = TRUE
        ORDER BY m.id
        """
    )
    return cursor.fetchall() or []


def _count_pending_predictions(cursor, model_id: int, max_papers: int) -> int:
    if max_papers == 0:
        cursor.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM feeds f
            JOIN embeddings e ON f.id = e.feed_id
            WHERE NOT EXISTS (
                SELECT 1 FROM predicted_preferences pp
                WHERE pp.feed_id = f.id AND pp.model_id = %s
            )
            """,
            (model_id,),
        )
    else:
        cursor.execute(
            """
            WITH recent_feeds AS (
                SELECT f.id
                FROM feeds f
                ORDER BY f.added DESC
                LIMIT %s
            )
            SELECT COUNT(*) AS cnt
            FROM recent_feeds rf
            JOIN feeds f ON f.id = rf.id
            JOIN embeddings e ON f.id = e.feed_id
            WHERE NOT EXISTS (
                SELECT 1 FROM predicted_preferences pp
                WHERE pp.feed_id = f.id AND pp.model_id = %s
            )
            """,
            (max_papers, model_id),
        )
    row = cursor.fetchone() or {}
    return int(row.get("cnt", 0))


def _predict_for_model_stream(
    cursor,
    db,
    model_id: int,
    model_dir: str,
    max_papers: int,
    prediction_batch: int,
    total_to_predict: int,
) -> None:
    """Predict preferences for a single model by streaming embeddings in batches."""
    query = _query_embeddings_for_prediction_no_offset(max_papers)

    # Load model components
    model, scaler, _ = _load_model(model_dir, model_id)

    processed = 0
    sum_scores = 0.0
    gmin = None
    gmax = None

    while True:
        if max_papers == 0:
            cursor.execute(query, (model_id, prediction_batch))
        else:
            cursor.execute(query, (max_papers, model_id, prediction_batch))

        batch = cursor.fetchall()
        if not batch:
            break

        feed_ids = [row["id"] for row in batch]
        emb_matrix = np.array([row["embedding"] for row in batch], dtype=np.float64)

        predictions = _predict_scores(model, scaler, emb_matrix)

        _store_predictions(cursor, db, model_id, feed_ids, predictions, prediction_batch)

        # Batch stats
        batch_min = float(np.min(predictions)) if len(predictions) else 0.0
        batch_max = float(np.max(predictions)) if len(predictions) else 0.0
        batch_mean = float(np.mean(predictions)) if len(predictions) else 0.0

        # Update global stats
        processed += len(predictions)
        sum_scores += float(np.sum(predictions))
        gmin = batch_min if gmin is None else min(gmin, batch_min)
        gmax = batch_max if gmax is None else max(gmax, batch_max)
        remaining = max(0, total_to_predict - processed)
        pct = (processed / total_to_predict * 100.0) if total_to_predict else 100.0

        # Single-line batch log with stats and progress
        log.info(
            f"Model {model_id}: batch={len(predictions)} min={batch_min:.3f} max={batch_max:.3f} mean={batch_mean:.3f} | progress {processed}/{total_to_predict} ({pct:.1f}%), remaining={remaining}"
        )

    if processed > 0:
        log.info(
            f"Model {model_id} summary: total={processed}, min={gmin:.3f}, max={gmax:.3f}, mean={(sum_scores/processed):.3f}"
        )


def _load_model(model_dir: str, model_id: int):
    model_path = f"{model_dir}/model-{model_id}.pkl"
    with open(model_path, "rb") as f:
        model_data = pickle.load(f)
    return model_data["model"], model_data["scaler"], model_path


def _predict_scores(model, scaler, embeddings: np.ndarray) -> np.ndarray:
    embeddings_scaled = scaler.transform(embeddings)
    dmatrix = xgb.DMatrix(embeddings_scaled)
    return model.predict(dmatrix)


def _store_predictions(
    cursor,
    db,
    model_id: int,
    feed_ids: Sequence[int],
    scores: Sequence[float],
    batch_size: int,
) -> None:
    prediction_data = [
        (feed_id, model_id, float(score)) for feed_id, score in zip(feed_ids, scores)
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
        page_size=min(1000, batch_size),
    )
    db.commit()


def main(
    config,
    max_papers,
    process_all,
    embedding_batch,
    prediction_batch,
    log_file,
    quiet,
):
    """Generate embeddings and predictions for articles in the database.

    Creates vector embeddings for articles and optionally generates interest
    predictions using trained models. Essential for semantic search and recommendations.
    """

    # Handle --all flag: set max_papers to 0 to process all papers
    if process_all:
        max_papers = 0

    if config:
        get_config(config)
    config_data = _load_config()
    db_config = config_data["db"]

    feeddb = FeedDatabase()
    embeddingdb = EmbeddingDatabase()

    # Connect to PostgreSQL
    log.info("Connecting to PostgreSQL database...")
    db, cursor = _connect_postgres(db_config)

    # First, get counts of feeds with and without embeddings
    feeds_with_embeddings_count, feeds_without_embeddings_count = _count_feeds(
        cursor, max_papers
    )

    log.info(f"Found {feeds_with_embeddings_count} feeds with embeddings, {feeds_without_embeddings_count} without embeddings")

    if feeds_without_embeddings_count == 0 and feeds_with_embeddings_count == 0:
        log.info("No papers found")
        return

    if max_papers == 0:
        log.info(
            f"Processing all papers (embedding batch={embedding_batch}, prediction batch={prediction_batch})..."
        )
    else:
        log.info(
            f"Processing {max_papers} most recent papers (embedding batch={embedding_batch}, prediction batch={prediction_batch})..."
        )

    log.info(
        f"Total papers: {feeds_with_embeddings_count} with embeddings, {feeds_without_embeddings_count} without"
    )

    # Generate embeddings for feeds that don't have them (streamed, no caching)
    if feeds_without_embeddings_count > 0:
        log.info(
            f"Generating embeddings in batches of {embedding_batch} for {feeds_without_embeddings_count} papers without embeddings..."
        )
        _generate_missing_embeddings_stream(
            cursor,
            max_papers,
            feeds_without_embeddings_count,
            embedding_batch,
            feeddb,
            embeddingdb,
        )

    # Get all active models
    log.info("Loading active models...")
    active_models = _load_active_models(cursor)

    if not active_models:
        log.warning("No active models found")
        cursor.close()
        db.close()
        return

    log.info(f"Found {len(active_models)} active models")

    # Get model directory from config
    model_dir = config_data.get("models", {}).get("path", ".")

    # Process predictions for each model (streaming batches)
    for model_info in active_models:
        model_id = model_info["id"]
        model_name = model_info.get("name") or f"Model {model_id}"

        log.info(f"Processing model {model_id} ({model_name})...")

        try:
            pending = _count_pending_predictions(cursor, model_id, max_papers)
            if pending == 0:
                log.info(f"All papers already have predictions for model {model_id}")
                continue
            log.info(f"Pending predictions for model {model_id}: {pending}")
            _predict_for_model_stream(
                cursor,
                db,
                model_id,
                model_dir,
                max_papers,
                prediction_batch,
                pending,
            )
        except Exception as e:
            log.error(f"Failed to process model {model_id}: {e}")
            continue

    # Close database connection
    cursor.close()
    db.close()

    log.info("Prediction task completed")
