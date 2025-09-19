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

from typing import Optional, Sequence

from .config import get_config
from .db import DatabaseManager
from .embedding_database import EmbeddingDatabase
from .feed_database import FeedDatabase
from .log import log
from .services.feed_prediction import FeedPredictionService


class FeedPredictor:
    """Common functionality for generating embeddings, predicting feed preferences and managing broadcast queues."""

    def __init__(self, feeddb, embeddingdb):
        self.feeddb = feeddb
        self.embeddingdb = embeddingdb
        self.config = get_config().raw
        self._service = FeedPredictionService(self.config, feeddb, embeddingdb)

    def generate_embeddings_batch(self, feed_ids, batch_size=100):
        """
        Generate embeddings for feeds that don't have them yet.

        Args:
            feed_ids: List of feed IDs to process
            batch_size: Size of batches for API calls

        Returns:
            List of paper IDs that successfully got embeddings
        """
        return self._service.embedding_generator.generate(feed_ids, batch_size)

    def predict_and_queue_feeds(
        self,
        feed_ids,
        model_dir,
        force_rescore=False,
        batch_size=100,
        refresh_embeddings=False,
    ):
        """
        Predict preferences for papers and add high-scoring ones to broadcast queues.
        Automatically generates embeddings for papers that don't have them.

        Args:
            feed_ids: List of paper IDs to process (can be a single ID in a list)
            model_dir: Directory containing model files
            force_rescore: Whether to force re-scoring of already scored papers
            batch_size: Size of batches for embedding generation
            refresh_embeddings: Regenerate embeddings even when they already exist
        """
        if not feed_ids:
            return

        if not isinstance(feed_ids, list):
            feed_ids = [feed_ids]

        self._service.predict_and_queue(
            feed_ids,
            model_dir,
            force_rescore=force_rescore,
            batch_size=batch_size,
            refresh_embeddings=refresh_embeddings,
        )

    def predict_for_external_ids(self, external_ids, model_dir, force_rescore=False):
        """
        Convenience method for predicting based on external IDs (used by update task).

        Args:
            external_ids: List of external IDs
            model_dir: Directory containing model files
            force_rescore: Whether to force re-scoring
        """
        if not external_ids:
            return

        # Convert external IDs to feed IDs
        feed_ids = []
        for ext_id in external_ids:
            self.feeddb.cursor.execute(
                "SELECT id FROM feeds WHERE external_id = %s", (ext_id,)
            )
            result = self.feeddb.cursor.fetchone()
            if result:
                feed_ids.append(result["id"])

        if feed_ids:
            self.predict_and_queue_feeds(
                feed_ids,
                model_dir,
                force_rescore=force_rescore,
            )


def refresh_embeddings_and_predictions(
    feed_ids: Sequence[int],
    db_manager: DatabaseManager,
    *,
    force_rescore: bool = False,
    refresh_embeddings: bool = False,
    batch_size: int = 100,
    model_dir: Optional[str] = None,
) -> None:
    """Run embedding generation and prediction for the provided feeds.

    Designed for callers that only have access to the shared DatabaseManager.
    Resources are opened and closed within this helper so it can be reused in
    web handlers and task code without leaking connections.
    """

    if not feed_ids:
        return

    feeds = list(feed_ids)
    feed_db: Optional[FeedDatabase] = None
    embedding_db: Optional[EmbeddingDatabase] = None

    try:
        feed_db = FeedDatabase(db_manager=db_manager)
        embedding_db = EmbeddingDatabase(db_manager=db_manager)
        predictor = FeedPredictor(feed_db, embedding_db)

        resolved_model_dir = model_dir
        if resolved_model_dir is None:
            resolved_model_dir = predictor.config.get("models", {}).get("path", ".")

        predictor.predict_and_queue_feeds(
            feeds,
            resolved_model_dir,
            force_rescore=force_rescore,
            batch_size=batch_size,
            refresh_embeddings=refresh_embeddings,
        )
    finally:
        # Ensure connections return to the pool regardless of success/failure
        if embedding_db is not None:
            try:
                embedding_db.close()
            except Exception as exc:  # pragma: no cover - defensive cleanup
                log.warning(f"Failed to close embedding database cleanly: {exc}")
        if feed_db is not None:
            try:
                feed_db.close()
            except Exception as exc:  # pragma: no cover - defensive cleanup
                log.warning(f"Failed to close feed database cleanly: {exc}")
