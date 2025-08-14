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

"""Base classes for notification providers."""

from abc import ABC, abstractmethod
import re


class NotificationError(Exception):
    """Base exception for notification errors."""

    pass


class NotificationProvider(ABC):
    """Abstract base class for notification providers."""

    @abstractmethod
    def send_notifications(self, items, message_options, base_url=None):
        """Send notifications for a batch of items.

        Args:
            items: List of dictionaries, each containing article information with keys:
                - id: Article ID
                - title: Article title
                - content: Article content/abstract
                - author: Article authors
                - origin: Source of the article
                - link: URL to the article
                - score: Prediction score (0.0 to 1.0)
            message_options: Additional options for the message
                - model_name: Name of the model used for scoring
                - channel_name: Name of the channel
            base_url: Base URL for web interface links

        Returns:
            List of (item_id, success) tuples indicating which items were sent successfully

        Raises:
            NotificationError: If sending fails completely
        """
        pass

    @staticmethod
    def normalize_text(text):
        """Normalize whitespace in text."""
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def limit_text_length(text, limit):
        """Truncate text to specified length."""
        if not text:
            return ""
        if len(text) > limit:
            return text[: limit - 3] + "…"
        return text
