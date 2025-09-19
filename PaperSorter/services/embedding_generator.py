#!/usr/bin/env python3
"""Embedding generation pipeline backed by OpenAI embeddings API."""

from __future__ import annotations

import random
import time
from typing import Iterable, List, Sequence

from ..log import log
from ..providers.openai_client import get_openai_client


class EmbeddingGenerator:
    """Generate and persist embeddings for feed items."""

    def __init__(self, config, feeddb, embeddingdb) -> None:
        self._config = config
        self._feeddb = feeddb
        self._embeddingdb = embeddingdb

        embedding_config = config.get("embedding_api", {})
        self._model = embedding_config.get("model", "text-embedding-3-large")
        self._dimensions = embedding_config.get("dimensions")
        self._client = get_openai_client("embedding_api", cfg=config, optional=True)

    @property
    def client_available(self) -> bool:
        return self._client is not None

    def generate(
        self,
        feed_ids: Sequence[int],
        batch_size: int = 100,
        *,
        force_refresh: bool = False,
    ) -> List[int]:
        """Ensure embeddings exist for provided feeds.

        Args:
            feed_ids: Sequence of paper IDs to process.
            batch_size: Maximum number of items sent per embedding request.
            force_refresh: When True, regenerate embeddings even if they already exist.

        Returns:
            List of feed IDs that have embeddings available after this call.
        """

        if not self._client:
            log.error("OpenAI client not configured")
            return []

        if not feed_ids:
            return []

        feeds = feed_ids if isinstance(feed_ids, list) else list(feed_ids)

        if force_refresh:
            feeds_needing_embeddings = feeds
        else:
            feeds_needing_embeddings = self._embeddingdb.filter_feeds_without_embeddings(feeds)

        if not feeds_needing_embeddings:
            if not force_refresh:
                log.info("All papers already have embeddings")
            return feeds

        successful: List[int] = []

        with self._embeddingdb.write_batch() as batch_writer:
            for start in range(0, len(feeds_needing_embeddings), batch_size):
                batch = feeds_needing_embeddings[start : start + batch_size]
                formatted_items, feed_index = self._prepare_batch(batch)
                if not formatted_items:
                    continue

                self._call_with_retries(batch_writer, feed_index, formatted_items, successful)

        if force_refresh:
            return feeds

        return successful

    def _prepare_batch(self, batch: Sequence[int]) -> tuple[List[str], dict[int, int]]:
        formatted_items: List[str] = []
        feed_index: dict[int, int] = {}
        for position, feed_id in enumerate(batch):
            formatted = self._feeddb.get_formatted_item(feed_id)
            if formatted:
                formatted_items.append(formatted)
                feed_index[position] = feed_id
            else:
                log.warning(f"Could not get formatted item for paper {feed_id}")
        return formatted_items, feed_index

    def _call_with_retries(self, batch_writer, feed_index: dict[int, int], formatted_items: List[str], successful: List[int]) -> None:
        max_retries = 5
        retry_count = 0

        while retry_count < max_retries:
            try:
                params = {"input": formatted_items, "model": self._model}
                if self._dimensions:
                    params["dimensions"] = self._dimensions

                response = self._client.embeddings.create(**params)

                for idx, embedding_data in enumerate(response.data):
                    if idx in feed_index:
                        feed_id = feed_index[idx]
                        if batch_writer.insert(feed_id, embedding_data.embedding):
                            successful.append(feed_id)
                        else:
                            log.error(f"Failed to store embedding for feed {feed_id}")
                return

            except Exception as exc:  # pragma: no cover - depends on network I/O
                error_str = str(exc)
                if "503" in error_str and "overloaded" in error_str.lower():
                    retry_count += 1
                    if retry_count < max_retries:
                        sleep_time = random.uniform(5, 20)
                        log.warning(
                            f"Model overloaded, retrying in {sleep_time:.1f} seconds (attempt {retry_count}/{max_retries})"
                        )
                        time.sleep(sleep_time)
                    else:
                        log.error(
                            f"Failed to generate embeddings for batch after {max_retries} retries: {exc}"
                        )
                else:
                    log.error(f"Failed to generate embeddings for batch: {exc}")
                    return
