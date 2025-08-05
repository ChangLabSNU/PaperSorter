#!/usr/bin/env python3
#
# Copyright (c) 2024 Hyeshik Chang
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

"""Base interface for feed providers."""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Iterator, Any
from datetime import datetime
from dataclasses import dataclass


@dataclass
class FeedItem:
    """Represents a single feed item/article."""
    external_id: str
    title: str
    content: Optional[str] = None
    author: Optional[str] = None
    origin: str = ""
    link: Optional[str] = None
    published: datetime = None

    def __post_init__(self):
        if self.published is None:
            self.published = datetime.now()


class FeedProvider(ABC):
    """Abstract base class for feed providers."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the provider with configuration."""
        self.config = config

    @abstractmethod
    def get_items(self, source: Dict[str, Any], limit: Optional[int] = None,
                  since: Optional[datetime] = None) -> Iterator[List[FeedItem]]:
        """
        Retrieve feed items from a source.

        Args:
            source: Source configuration (from feed_sources table)
            limit: Maximum number of items to retrieve
            since: Only get items published after this date

        Yields:
            Lists of FeedItem objects (batched for efficiency)
        """
        pass

    @abstractmethod
    def update_source_timestamp(self, source_id: int, has_new_items: bool = False):
        """
        Update the last_checked timestamp and optionally last_updated for a source.

        Args:
            source_id: ID of the source in feed_sources table
            has_new_items: Whether new items were found from this source
        """
        pass

    @abstractmethod
    def get_sources(self, source_type: str) -> List[Dict[str, Any]]:
        """
        Get all sources of a specific type that need updating.

        Args:
            source_type: Type of sources to retrieve (e.g., 'rss')

        Returns:
            List of source dictionaries from feed_sources table
        """
        pass

    def validate_source(self, source: Dict[str, Any]) -> bool:
        """
        Validate that a source has required fields for this provider.

        Args:
            source: Source configuration to validate

        Returns:
            True if valid, False otherwise
        """
        return True