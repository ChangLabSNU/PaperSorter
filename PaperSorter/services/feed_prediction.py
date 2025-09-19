#!/usr/bin/env python3
"""Prediction and queueing helpers for feed ranking models."""

from __future__ import annotations

import os
import pickle
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import xgboost as xgb

from ..config import get_config
from ..db import DatabaseManager
from ..embedding_database import EmbeddingDatabase
from ..feed_database import FeedDatabase
from ..log import log
from .embedding_generator import EmbeddingGenerator


class FeedPredictionService:
    """Orchestrate embedding generation, model inference, and queue updates."""

    def __init__(self, config, feeddb, embeddingdb) -> None:
        self._config = config
        self._feeddb = feeddb
        self._embeddingdb = embeddingdb
        self._embedding_generator = EmbeddingGenerator(config, feeddb, embeddingdb)

    @property
    def embedding_generator(self) -> EmbeddingGenerator:
        return self._embedding_generator

    def predict_and_queue(
        self,
        feed_ids: Sequence[int],
        model_dir: str,
        *,
        force_rescore: bool = False,
        batch_size: int = 100,
        refresh_embeddings: bool = False,
    ) -> None:
        if not feed_ids:
            return

        feed_list = list(feed_ids)
        feeds_with_embeddings = self._embedding_generator.generate(
            feed_list,
            batch_size,
            force_refresh=refresh_embeddings,
        )
        channels_by_model, channels_without_model = self._load_active_channels()

        if channels_without_model and not channels_by_model:
            log.error("No channels have valid models assigned. Cannot generate predictions.")
            return

        embeddings_map = self._load_embeddings(feeds_with_embeddings)
        if not embeddings_map:
            log.warning("No embeddings found for any of the provided papers")
            return

        for model_id, channels in channels_by_model.items():
            try:
                model, scaler = self._load_model(model_dir, model_id)
            except FileNotFoundError:
                log.warning(f"Model file not found: {os.path.join(model_dir, f'model-{model_id}.pkl')}")
                continue
            except Exception as exc:
                log.error(f"Failed to load model {model_id}: {exc}")
                continue

            feeds_to_predict = self._feeds_requiring_prediction(model_id, embeddings_map, force_rescore)
            if not feeds_to_predict:
                log.info(f"All papers already have predictions for model {model_id}")
                continue

            predictions = self._score_feeds(model, scaler, feeds_to_predict, embeddings_map)
            self._store_predictions(model_id, feeds_to_predict, predictions)
            self._enqueue_broadcasts(channels, feeds_to_predict, predictions)

        self._feeddb.commit()


class FeedPredictor:
    """Generate embeddings, run predictions, and queue broadcasts."""

    def __init__(self, feeddb, embeddingdb):
        self.feeddb = feeddb
        self.embeddingdb = embeddingdb
        self.config = get_config().raw
        self._service = FeedPredictionService(self.config, feeddb, embeddingdb)

    def generate_embeddings_batch(self, feed_ids, batch_size: int = 100):
        """Generate embeddings for feeds that do not yet have one."""

        return self._service.embedding_generator.generate(feed_ids, batch_size)

    def predict_and_queue_feeds(
        self,
        feed_ids,
        model_dir,
        force_rescore: bool = False,
        batch_size: int = 100,
        refresh_embeddings: bool = False,
    ):
        """Score feeds with available models and queue high-scoring items."""

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

    def predict_for_external_ids(self, external_ids, model_dir, force_rescore: bool = False):
        """Convenience method mapping external IDs to feed IDs before scoring."""

        if not external_ids:
            return

        feed_ids = []
        for ext_id in external_ids:
            self.feeddb.cursor.execute(
                "SELECT id FROM feeds WHERE external_id = %s",
                (ext_id,),
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
    """Run embedding generation and prediction for a collection of feeds."""

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
        if embedding_db is not None:
            try:
                embedding_db.close()
            except Exception as exc:  # pragma: no cover
                log.warning(f"Failed to close embedding database cleanly: {exc}")
        if feed_db is not None:
            try:
                feed_db.close()
            except Exception as exc:  # pragma: no cover
                log.warning(f"Failed to close feed database cleanly: {exc}")

    def _load_active_channels(self) -> Tuple[Dict[int, List[dict]], List[dict]]:
        self._feeddb.cursor.execute(
            """
            SELECT c.*, m.id as model_id, m.name as model_name
            FROM channels c
            LEFT JOIN models m ON c.model_id = m.id
            WHERE c.is_active = true
            """
        )
        active_channels = self._feeddb.cursor.fetchall()
        if not active_channels:
            log.warning("No active channels found")
            return {}, []

        channels_by_model: Dict[int, List[dict]] = {}
        channels_without_model: List[dict] = []
        for channel in active_channels:
            model_id = channel.get("model_id")
            if model_id is None:
                log.warning(
                    "Channel '%s' (ID: %s) has no model assigned, skipping predictions",
                    channel.get("name"),
                    channel.get("id"),
                )
                channels_without_model.append(channel)
                continue
            channels_by_model.setdefault(model_id, []).append(channel)

        return channels_by_model, channels_without_model

    def _load_embeddings(self, feed_ids: Iterable[int]) -> Dict[int, np.ndarray]:
        embeddings_map: Dict[int, np.ndarray] = {}
        for feed_id in feed_ids:
            self._embeddingdb.cursor.execute(
                "SELECT embedding FROM embeddings WHERE feed_id = %s",
                (feed_id,),
            )
            result = self._embeddingdb.cursor.fetchone()
            if result:
                embeddings_map[feed_id] = np.array(result["embedding"])
            else:
                log.warning(f"No embedding found for paper {feed_id} even after generation")
        return embeddings_map

    def _load_model(self, model_dir: str, model_id: int):
        model_file = os.path.join(model_dir, f"model-{model_id}.pkl")
        with open(model_file, "rb") as handle:
            model_data = pickle.load(handle)
        return model_data["model"], model_data["scaler"]

    def _feeds_requiring_prediction(
        self,
        model_id: int,
        embeddings_map: Dict[int, np.ndarray],
        force_rescore: bool,
    ) -> List[int]:
        if force_rescore:
            return list(embeddings_map.keys())

        self._feeddb.cursor.execute(
            """
            SELECT feed_id
            FROM predicted_preferences
            WHERE model_id = %s AND feed_id = ANY(%s)
            """,
            (model_id, list(embeddings_map.keys())),
        )
        already_predicted = {row["feed_id"] for row in self._feeddb.cursor.fetchall()}
        return [fid for fid in embeddings_map.keys() if fid not in already_predicted]

    def _score_feeds(self, model, scaler, feed_ids: Sequence[int], embeddings_map: Dict[int, np.ndarray]) -> np.ndarray:
        embeddings_array = np.array([embeddings_map[fid] for fid in feed_ids])
        embeddings_scaled = scaler.transform(embeddings_array)
        dmatrix = xgb.DMatrix(embeddings_scaled)
        return model.predict(dmatrix)

    def _store_predictions(self, model_id: int, feed_ids: Sequence[int], predictions: Sequence[float]) -> None:
        for feed_id, score in zip(feed_ids, predictions):
            self._feeddb.cursor.execute(
                """
                INSERT INTO predicted_preferences (feed_id, model_id, score)
                VALUES (%s, %s, %s)
                ON CONFLICT (feed_id, model_id) DO UPDATE
                SET score = EXCLUDED.score
                """,
                (feed_id, model_id, float(score)),
            )

    def _enqueue_broadcasts(
        self,
        channels: Sequence[dict],
        feed_ids: Sequence[int],
        predictions: Sequence[float],
    ) -> None:
        for channel in channels:
            score_threshold = channel.get("score_threshold") or 0.7
            channel_id = channel.get("id")
            for feed_id, score in zip(feed_ids, predictions):
                if score < score_threshold:
                    continue
                self._feeddb.cursor.execute(
                    """
                    SELECT 1 FROM broadcasts
                    WHERE feed_id = %s AND channel_id = %s
                    """,
                    (feed_id, channel_id),
                )
                if self._feeddb.cursor.fetchone():
                    continue

                self._feeddb.add_to_broadcast_queue(feed_id, channel_id)

                self._feeddb.cursor.execute(
                    """
                    SELECT title FROM feeds WHERE id = %s
                    """,
                    (feed_id,),
                )
                feed_info = self._feeddb.cursor.fetchone()
                if feed_info:
                    log.info(
                        "Added to channel %s queue: %s",
                        channel.get("name"),
                        feed_info.get("title"),
                    )
