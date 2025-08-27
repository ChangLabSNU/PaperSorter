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

"""Scholarly article item model for web interface."""

from datetime import datetime
from ...providers import FeedItem
from ...providers.scholarly_database import ScholarlyArticle


class ScholarlyArticleItem(FeedItem):
    """Item model for scholarly articles from any database provider."""

    def __init__(self, article: ScholarlyArticle):
        """Initialize from a ScholarlyArticle object."""
        self.article = article

        # Extract content with tldr fallback
        content = article.abstract
        if not content and article.tldr:
            content = f"(tl;dr) {article.tldr}"
        elif article.tldr:
            # Prepend tldr if available
            content = f"(tl;dr) {article.tldr}\n\n{content}"

        # Use publication date or current date
        published_datetime = article.publication_date or datetime.now()

        # Initialize parent FeedItem
        super().__init__(
            external_id=article.unique_id,
            title=article.title,
            content=content or "",
            author=article.format_authors(),
            origin=article.venue or "Unknown",
            link=article.url or "",
            published=published_datetime,
        )

        # Store raw article for access to all fields
        self.raw_article = article

