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

"""Discord webhook notification provider."""

import requests
from ..log import log
from .base import NotificationProvider, NotificationError


class DiscordProvider(NotificationProvider):
    """Discord webhook notification provider using embeds."""

    # Discord embed limits
    EMBED_DESCRIPTION_MAX = 4096
    EMBED_TITLE_MAX = 256
    EMBED_FIELD_VALUE_MAX = 1024
    EMBED_AUTHOR_NAME_MAX = 256
    EMBED_FOOTER_TEXT_MAX = 2048
    EMBED_FIELDS_MAX = 25

    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def _get_score_color(self, score):
        """Get embed color based on score (0.0 to 1.0).

        Returns Discord color integer based on score:
        - High (≥0.7): Green
        - Medium (0.4-0.7): Yellow/Orange
        - Low (<0.4): Red
        - None: Discord blurple
        """
        if score is None:
            return 0x7289DA  # Discord blurple for neutral

        if score >= 0.7:
            return 0x43B581  # Green
        elif score >= 0.4:
            return 0xFAA61A  # Yellow/orange
        else:
            return 0xF04747  # Red

    def send_notifications(self, items, message_options, base_url=None):
        """Send Discord notifications for a batch of items.

        Discord sends individual notifications for each item.

        Args:
            items: List of paper dictionaries
            message_options: Additional options
            base_url: Base URL for web interface links

        Returns:
            List of (item_id, success) tuples
        """
        results = []
        for item in items:
            try:
                self._send_single_notification(item, message_options, base_url)
                results.append((item.get('id'), True))
            except NotificationError as e:
                log.error(f"Failed to send Discord notification for item {item.get('id')}: {e}")
                results.append((item.get('id'), False))
        return results

    def _send_single_notification(self, item, message_options, base_url=None):
        """Send a Discord notification using rich embeds."""

        # Create embed
        embed = {}

        # Title and URL
        title = self.normalize_text(item["title"])
        embed["title"] = self.limit_text_length(title, self.EMBED_TITLE_MAX)
        if item.get("link"):
            embed["url"] = item["link"]

        # Color based on score
        embed["color"] = self._get_score_color(item.get("score"))

        # Description (content/abstract)
        content = item.get("content", "").strip()
        if content:
            embed["description"] = self.limit_text_length(
                content, self.EMBED_DESCRIPTION_MAX
            )

        # Author field
        authors = self.normalize_text(item.get("author", ""))
        if authors:
            embed["author"] = {
                "name": self.limit_text_length(authors, self.EMBED_AUTHOR_NAME_MAX)
            }

        # Fields for metadata
        fields = []

        # Score field
        if item.get("score") is not None:
            score_percent = int(item["score"] * 100)
            # Add visual indicator based on score
            if score_percent >= 70:
                indicator = "🟢"
            elif score_percent >= 40:
                indicator = "🟡"
            else:
                indicator = "🔴"

            # Use score_name from model if available, default to "Score"
            score_name = message_options.get("score_name", "Score")

            # Build score value including other model scores if available
            score_value = f"{indicator} {score_percent}"

            # Add other model scores if available
            if item.get("other_scores"):
                other_scores_text = []
                for other_score in item["other_scores"]:
                    if other_score.get("score") is not None:
                        other_score_percent = int(other_score["score"] * 100)
                        other_scores_text.append(
                            f"• {other_score['score_name']}: {other_score_percent}"
                        )
                if other_scores_text:
                    score_value += "\n" + "\n".join(other_scores_text)

            fields.append(
                {
                    "name": f"📊 {score_name}",
                    "value": score_value,
                    "inline": True,
                }
            )

        # Source field
        origin = self.normalize_text(item.get("origin", ""))
        if origin:
            fields.append(
                {
                    "name": "📥 Source",
                    "value": self.limit_text_length(origin, self.EMBED_FIELD_VALUE_MAX),
                    "inline": True,
                }
            )

        # Add action links as a field (Discord webhooks don't support interactive buttons)
        if base_url and "id" in item:
            links = []

            # Article link
            if item.get("link"):
                links.append(f"[📖 Read Article]({item['link']})")

            # Details view link
            details_url = f"{base_url.rstrip('/')}/paper/{item['id']}"
            links.append(f"[🔍 Details]({details_url})")

            if links:
                # Split links into multiple lines for better readability
                fields.append(
                    {"name": "🔗 Actions", "value": "\n".join(links), "inline": False}
                )
        elif item.get("link"):
            # Just the article link if no base_url
            fields.append(
                {
                    "name": "🔗 Link",
                    "value": f"[Read Article]({item['link']})",
                    "inline": False,
                }
            )

        # Add fields to embed (Discord has a limit of 25 fields)
        if fields:
            embed["fields"] = fields[: self.EMBED_FIELDS_MAX]

        # Footer
        footer_parts = ["PaperSorter"]
        if message_options.get("channel_name"):
            footer_parts.append(message_options["channel_name"])

        embed["footer"] = {
            "text": self.limit_text_length(
                " • ".join(footer_parts), self.EMBED_FOOTER_TEXT_MAX
            )
        }

        # Timestamp (optional, using current time)
        from datetime import datetime, timezone

        embed["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Prepare webhook payload
        data = {
            "embeds": [embed],
            "username": "PaperSorter",
        }

        # Send the webhook
        header = {"Content-Type": "application/json"}
        response = requests.post(self.webhook_url, headers=header, json=data)

        if response.status_code == 204:
            # Discord returns 204 No Content on success
            pass
        elif response.status_code == 429:
            # Rate limited
            retry_after = response.json().get("retry_after", 60)
            log.error(f"Discord rate limit hit. Retry after {retry_after} seconds.")
            raise NotificationError(f"Discord rate limit: retry after {retry_after}s")
        elif response.status_code in (400, 401, 403, 404):
            log.error(
                f"Discord webhook error. Status: {response.status_code}, "
                f"Response: {response.text}"
            )
            raise NotificationError(f"Discord webhook error: {response.status_code}")
        else:
            log.error(
                f"Unexpected Discord webhook error. Status: {response.status_code}"
            )
            raise NotificationError(
                f"Discord webhook unexpected error: {response.status_code}"
            )
