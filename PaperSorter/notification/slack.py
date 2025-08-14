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

"""Slack webhook notification provider."""

import requests
from ..log import log
from .base import NotificationProvider, NotificationError


class SlackProvider(NotificationProvider):
    """Slack webhook notification provider."""

    HEADER_MAX_LENGTH = 150

    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def send_notifications(self, items, message_options, base_url=None):
        """Send Slack notifications for a batch of items.

        Slack sends individual notifications for each item.

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
                log.error(f"Failed to send Slack notification for item {item.get('id')}: {e}")
                results.append((item.get('id'), False))
        return results

    def _send_single_notification(self, item, message_options, base_url=None):
        """Send a Slack notification using Block Kit."""
        header = {"Content-type": "application/json"}

        # Add title block
        title = self.normalize_text(item["title"])
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": self.limit_text_length(title, self.HEADER_MAX_LENGTH),
                },
            },
        ]

        # Add predicted score block if score is available
        if item.get("score") is not None:
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f":heart_decoration: QBio "
                            f"Score: *{int(item['score'] * 100)}*",
                        }
                    ],
                }
            )

        # Add source block
        origin = self.normalize_text(item.get("origin", ""))
        if origin:
            if item.get("link"):
                origin = f"<{item['link']}|{origin}>"

            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f":inbox_tray: Source: *{origin}*"}
                    ],
                }
            )

        # Add authors block
        authors = self.normalize_text(item.get("author", ""))
        if authors:
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f":black_nib: *{authors}*"}
                    ],
                }
            )

        # Add content
        content = item.get("content", "").strip()
        if content:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": content},
                }
            )

        # Add buttons block
        button_elements = []

        # Read button
        if item.get("link"):
            button_elements.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Read", "emoji": True},
                    "value": f"read_{item['id']}",
                    "url": item["link"],
                    "action_id": "read-action",
                }
            )

        # More Like This button
        if base_url and "id" in item:
            similar_url = f"{base_url.rstrip('/')}/similar/{item['id']}"
            button_elements.append(
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "More Like This",
                        "emoji": True,
                    },
                    "value": f"similar_{item['id']}",
                    "url": similar_url,
                    "action_id": "similar-action",
                }
            )

            # Interested button
            interested_url = f"{base_url.rstrip('/')}/feedback/{item['id']}/interested"
            button_elements.append(
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Interested", "emoji": True},
                    "value": f"interested_{item['id']}",
                    "url": interested_url,
                    "action_id": "interested-action",
                }
            )

            # Not Interested button
            not_interested_url = (
                f"{base_url.rstrip('/')}/feedback/{item['id']}/not-interested"
            )
            button_elements.append(
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Not Interested",
                        "emoji": True,
                    },
                    "value": f"not_interested_{item['id']}",
                    "url": not_interested_url,
                    "action_id": "not-interested-action",
                }
            )

        if button_elements:
            blocks.append({"type": "actions", "elements": button_elements})

        data = {
            "blocks": blocks,
            "unfurl_links": False,
            "unfurl_media": False,
        }

        response = requests.post(self.webhook_url, headers=header, json=data)

        if response.status_code == 200:
            pass
        elif response.status_code in (400, 500):
            import pprint

            log.error(
                "There was an error in Slack webhook. "
                f"status:{response.status_code} reason:{response.text}\n"
                + pprint.pformat(data)
            )
            raise NotificationError(f"Slack webhook error: {response.status_code}")
        else:
            log.error(
                "There was an unexpected error in the Slack webhook. Status code: "
                f"{response.status_code}"
            )
            raise NotificationError(
                f"Slack webhook unexpected error: {response.status_code}"
            )
