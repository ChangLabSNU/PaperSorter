"""Feed providers for PaperSorter."""

from .base import FeedProvider, FeedItem
from .rss import RSSProvider

__all__ = ["FeedProvider", "FeedItem", "RSSProvider"]
