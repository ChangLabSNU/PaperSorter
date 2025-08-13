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

"""Abstract base class for scholarly database providers."""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from datetime import datetime
import uuid


class ScholarlyArticle:
    """Standardized representation of a scholarly article."""

    def __init__(
        self,
        title: str,
        authors: List[str],
        abstract: Optional[str] = None,
        tldr: Optional[str] = None,
        venue: Optional[str] = None,
        publication_date: Optional[datetime] = None,
        url: Optional[str] = None,
        doi: Optional[str] = None,
        external_ids: Optional[Dict[str, str]] = None,
        raw_data: Optional[Dict] = None
    ):
        self.title = title
        self.authors = authors
        self.abstract = abstract
        self.tldr = tldr
        self.venue = venue
        self.publication_date = publication_date
        self.url = url
        self.doi = doi
        self.external_ids = external_ids or {}
        self.raw_data = raw_data or {}

        # Generate a unique ID based on URL or DOI
        if url:
            self.unique_id = str(uuid.uuid3(uuid.NAMESPACE_URL, url))
        elif doi:
            self.unique_id = str(uuid.uuid3(uuid.NAMESPACE_URL, f"doi:{doi}"))
        else:
            self.unique_id = str(uuid.uuid3(uuid.NAMESPACE_URL, title))

    def format_authors(self, max_authors: int = 4) -> str:
        """Format authors list as a string."""
        if not self.authors:
            return ""

        if len(self.authors) <= max_authors:
            return ", ".join(self.authors)
        else:
            first_authors = ", ".join(self.authors[:max_authors - 2])
            last_authors = ", ".join(self.authors[-2:])
            return f"{first_authors}, ..., {last_authors}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation compatible with frontend."""
        # Format authors as expected by frontend (array of objects with 'name' field)
        authors_formatted = [{"name": author} for author in self.authors] if self.authors else []

        # Format year from publication date
        year = None
        if self.publication_date:
            year = self.publication_date.year

        # Format tldr as expected by frontend (object with 'text' field)
        tldr_formatted = {"text": self.tldr} if self.tldr else None

        # Format journal as expected by frontend (object with 'name' field)
        journal_formatted = {"name": self.venue} if self.venue else None

        return {
            "title": self.title,
            "authors": authors_formatted,  # Frontend expects array of {name: ...}
            "authors_formatted": self.format_authors(),  # Keep this for other uses
            "abstract": self.abstract,
            "tldr": tldr_formatted,  # Frontend expects {text: ...}
            "venue": self.venue,
            "journal": journal_formatted,  # Frontend expects {name: ...}
            "year": year,  # Frontend expects year as a number
            "publicationDate": self.publication_date.isoformat() if self.publication_date else None,
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
            "url": self.url,
            "doi": self.doi,
            "external_ids": self.external_ids,
            "externalIds": self.external_ids,  # Alias for compatibility
            "unique_id": self.unique_id,
            "article_id": self.unique_id,  # Alias for compatibility
            "already_added": False  # Will be updated by the API
        }


class ScholarlyDatabaseProvider(ABC):
    """Abstract base class for scholarly database providers."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the provider with configuration."""
        self.config = config

    @abstractmethod
    def search(
        self,
        query: str,
        limit: int = 20,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        **kwargs
    ) -> List[ScholarlyArticle]:
        """
        Search for articles matching the query.

        Args:
            query: Search query string
            limit: Maximum number of results to return
            year_from: Minimum publication year (optional)
            year_to: Maximum publication year (optional)
            **kwargs: Additional provider-specific parameters

        Returns:
            List of ScholarlyArticle objects
        """
        pass

    @abstractmethod
    def match_by_title(
        self,
        title: str,
        publication_date: Optional[datetime] = None,
        date_tolerance_days: int = 60
    ) -> Optional[ScholarlyArticle]:
        """
        Find an article by matching its title and approximate publication date.

        Args:
            title: Article title to match
            publication_date: Approximate publication date
            date_tolerance_days: Number of days before/after publication_date to search

        Returns:
            ScholarlyArticle object if found, None otherwise
        """
        pass

    @abstractmethod
    def get_by_id(self, article_id: str) -> Optional[ScholarlyArticle]:
        """
        Get an article by its provider-specific ID.

        Args:
            article_id: Provider-specific article ID (DOI, S2 ID, OpenAlex ID, etc.)

        Returns:
            ScholarlyArticle object if found, None otherwise
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this provider."""
        pass

    @property
    @abstractmethod
    def requires_api_key(self) -> bool:
        """Return whether this provider requires an API key."""
        pass

    def is_configured(self) -> bool:
        """Check if the provider is properly configured."""
        if self.requires_api_key:
            return bool(self.config.get("api_key"))
        return True

