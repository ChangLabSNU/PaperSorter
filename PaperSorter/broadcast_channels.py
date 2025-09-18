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

import psycopg2
import psycopg2.extras
import re
from typing import Mapping, Sequence

from .config import get_config
from .log import log


class BroadcastChannels:
    """Manages broadcast channel configurations."""

    MAX_CONTENT_LENGTH = 1000

    def __init__(self):
        self._config = get_config().raw

        db_config = self._config["db"]

        # Connect to PostgreSQL
        self.db = psycopg2.connect(
            host=db_config["host"],
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
        )
        self.db.autocommit = False
        self.cursor = self.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def __del__(self):
        if hasattr(self, "db"):
            self.db.close()

    def get_channel(self, channel_id):
        """Get a specific channel's configuration."""
        self.cursor.execute(
            """
            SELECT id, name, endpoint_url, score_threshold, model_id
            FROM channels
            WHERE id = %s
        """,
            (channel_id,),
        )
        return self.cursor.fetchone()

    def get_all_channels(self):
        """Get all channels with their settings."""
        self.cursor.execute("""
            SELECT id, name, endpoint_url, score_threshold, model_id
            FROM channels
            ORDER BY id
        """)
        return self.cursor.fetchall()

    def update_channel(self, channel_id, **kwargs):
        """Update channel settings."""
        allowed_fields = ["name", "endpoint_url", "score_threshold", "model_id"]
        updates = []
        values = []

        for field in allowed_fields:
            if field in kwargs:
                updates.append(f"{field} = %s")
                values.append(kwargs[field])

        if updates:
            values.append(channel_id)
            self.cursor.execute(
                f"""
                UPDATE channels
                SET {", ".join(updates)}
                WHERE id = %s
            """,
                values,
            )
            self.db.commit()

    def delete_channel(self, channel_id):
        """Delete a channel."""
        self.cursor.execute("DELETE FROM channels WHERE id = %s", (channel_id,))
        self.db.commit()

    def commit(self):
        """Commit any pending transactions."""
        self.db.commit()

    @staticmethod
    def _normalize_text(text):
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def _limit_text_length(cls, text):
        if not text:
            return ""
        if len(text) > cls.MAX_CONTENT_LENGTH:
            return text[: cls.MAX_CONTENT_LENGTH - 1] + "…"
        return text

    def _prepare_item(self, item: Mapping) -> Mapping:
        """Prepare a feed item for notification payloads."""

        prepared = dict(item)

        # Ensure the notification id matches the feed id
        feed_id = prepared.get("id") or prepared.get("feed_id")
        prepared["id"] = feed_id

        if prepared.get("journal"):
            prepared["origin"] = prepared["journal"]

        # Prefer TL;DR when present
        tldr = prepared.get("tldr")
        if tldr and isinstance(tldr, str) and len(tldr.strip()) >= 5:
            prepared["content"] = f"(tl;dr) {self._normalize_text(tldr)}"

        content = prepared.get("content")
        if content:
            prepared["content"] = self._limit_text_length(self._normalize_text(content))

        for field in ("title", "author", "origin"):
            if prepared.get(field):
                prepared[field] = self._normalize_text(prepared[field])

        predicted = prepared.get("predicted_score")
        if predicted is not None and prepared.get("score") is None:
            prepared["score"] = predicted

        return prepared

    def _build_message_options(self, channel: Mapping) -> Mapping:
        model_name = channel.get("model_name")
        score_name = channel.get("score_name")
        model_id = channel.get("model_id")

        if not model_name or not score_name:
            if model_id:
                self.cursor.execute(
                    "SELECT name, score_name FROM models WHERE id = %s",
                    (model_id,),
                )
                model_row = self.cursor.fetchone()
                if model_row:
                    model_name = model_name or model_row.get("name")
                    score_name = score_name or model_row.get("score_name")

        return {
            "model_name": model_name or "Default",
            "channel_name": channel.get("name", "Channel"),
            "score_name": score_name or "Score",
        }

    def send_to_channel(self, channel: Mapping, papers: Sequence[Mapping]) -> bool:
        """Send feed items to the configured notification channel."""

        from .notification import create_notification_provider, NotificationError

        if not papers:
            log.info(
                "No papers supplied for broadcast to channel %s", channel.get("name", "")
            )
            return True

        webhook_url = channel.get("endpoint_url") or channel.get("webhook_url")
        if not webhook_url:
            raise ValueError("Channel is missing endpoint URL for broadcasting")

        provider = create_notification_provider(webhook_url)
        message_options = self._build_message_options(channel)
        base_url = (
            self._config.get("web", {}).get("base_url")
            if isinstance(self._config.get("web"), dict)
            else None
        )

        prepared_items = [self._prepare_item(item) for item in papers]

        try:
            results = provider.send_notifications(prepared_items, message_options, base_url)
        except NotificationError as exc:
            log.error(
                "Notification provider failure for channel %s: %s",
                channel.get("name", ""),
                exc,
            )
            return False

        # Provider returns list of (item_id, success) tuples
        return all(success for _, success in results)
