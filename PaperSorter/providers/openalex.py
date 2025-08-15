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

"""OpenAlex database provider implementation."""

import requests
import time
import re
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from .scholarly_database import ScholarlyDatabaseProvider, ScholarlyArticle
from ..log import log


class OpenAlexProvider(ScholarlyDatabaseProvider):
    """OpenAlex API provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # OpenAlex requires a valid email address for polite access
        self.email = config.get("email")
        if not self.email:
            raise ValueError("OpenAlex requires an email address for API access. Please configure 'email' in the OpenAlex settings.")
        self.api_base_url = config.get("api_url", "https://api.openalex.org")
        self.throttle_seconds = config.get("throttle", 0.1)  # OpenAlex allows 10 req/s
        self.last_request_time = 0

    @property
    def name(self) -> str:
        return "OpenAlex"

    @property
    def requires_api_key(self) -> bool:
        return False  # OpenAlex only requires email

    def is_configured(self) -> bool:
        """Check if the provider is properly configured."""
        # OpenAlex requires email instead of API key
        return bool(self.config.get("email"))

    def _escape_query(self, query: str) -> str:
        """Escape special characters in OpenAlex search queries.

        OpenAlex search doesn't support certain operators like |, &, etc.
        These need to be removed or escaped from the query string.
        """
        # Remove or escape problematic characters
        # The pipe character and other special operators are not supported
        escaped = re.sub(r'[|&()<>!{}[\]^"~*?:\\]', ' ', query)
        # Clean up multiple spaces
        escaped = re.sub(r'\s+', ' ', escaped)
        return escaped.strip()

    def _make_request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make a rate-limited request to the API."""
        # Rate limiting
        elapsed = time.time() - self.last_request_time
        if elapsed < self.throttle_seconds:
            time.sleep(self.throttle_seconds - elapsed)

        # Add email to params for polite requests
        if params is None:
            params = {}
        params["mailto"] = self.email

        try:
            response = requests.get(url, params=params)
            self.last_request_time = time.time()

            if response.status_code == 200:
                return response.json()
            else:
                log.error(f"OpenAlex API error: {response.status_code} - {response.text}")
                return None
        except requests.RequestException as e:
            log.error(f"Request failed: {e}")
            return None

    def _reconstruct_abstract(self, inverted_index: Dict) -> Optional[str]:
        """Reconstruct abstract from OpenAlex inverted index format."""
        if not inverted_index:
            return None

        try:
            # Find the maximum position
            max_pos = max(max(positions) for positions in inverted_index.values())

            # Create array to hold words
            words = [''] * (max_pos + 1)

            # Place each word at its positions
            for word, positions in inverted_index.items():
                for pos in positions:
                    words[pos] = word

            # Join and clean up
            abstract = ' '.join(words).strip()

            # Basic cleanup
            abstract = abstract.replace('  ', ' ')
            return abstract if abstract else None
        except Exception as e:
            log.error(f"Failed to reconstruct abstract: {e}")
            return None

    def _parse_article(self, data: Dict) -> ScholarlyArticle:
        """Parse OpenAlex response into ScholarlyArticle."""
        # Extract authors
        authors = []
        if data.get("authorships"):
            for authorship in data["authorships"]:
                author = authorship.get("author", {})
                if author.get("display_name"):
                    authors.append(author["display_name"])

        # Extract publication date
        pub_date = None
        if data.get("publication_date"):
            try:
                pub_date = datetime.fromisoformat(data["publication_date"])
            except (ValueError, TypeError):
                pass

        # Extract abstract
        abstract = self._reconstruct_abstract(data.get("abstract_inverted_index", {}))

        # Extract venue
        venue = None
        primary_location = data.get("primary_location", {})
        if primary_location:
            source = primary_location.get("source", {})
            if source:
                venue = source.get("display_name")

        # Get best URL (prefer DOI URL, then OpenAlex URL)
        url = data.get("doi")
        if url:
            url = f"https://doi.org/{url.replace('https://doi.org/', '')}"
        else:
            url = data.get("id")  # OpenAlex ID URL

        # External IDs
        ids = data.get("ids", {})
        external_ids = {}
        if ids.get("doi"):
            external_ids["DOI"] = ids["doi"].replace("https://doi.org/", "")
        if ids.get("pmid"):
            external_ids["PMID"] = ids["pmid"]
        if ids.get("arxiv"):
            external_ids["ArXiv"] = ids["arxiv"]

        return ScholarlyArticle(
            title=data.get("title", ""),
            authors=authors,
            abstract=abstract,
            tldr=None,  # OpenAlex doesn't provide TL;DR
            venue=venue,
            publication_date=pub_date,
            url=url,
            doi=external_ids.get("DOI"),
            external_ids=external_ids,
            raw_data=data
        )

    def search(
        self,
        query: str,
        limit: int = 20,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        **kwargs
    ) -> List[ScholarlyArticle]:
        """Search for articles using OpenAlex."""
        url = f"{self.api_base_url}/works"

        # Escape special characters in the query
        escaped_query = self._escape_query(query)

        params = {
            "search": escaped_query,
            "per_page": limit
        }

        # Build filter string
        filters = []
        if year_from and year_to:
            # OpenAlex uses range syntax: from_publication_date:YYYY-MM-DD
            filters.append(f"from_publication_date:{year_from}-01-01,to_publication_date:{year_to}-12-31")
        elif year_from:
            filters.append(f"from_publication_date:{year_from}-01-01")
        elif year_to:
            filters.append(f"to_publication_date:{year_to}-12-31")

        if filters:
            params["filter"] = ",".join(filters)

        result = self._make_request(url, params)
        if not result or "results" not in result:
            return []

        articles = []
        for item in result["results"]:
            try:
                articles.append(self._parse_article(item))
            except Exception as e:
                log.error(f"Failed to parse article: {e}")
                continue

        return articles

    def match_by_title(
        self,
        title: str,
        publication_date: Optional[datetime] = None,
        date_tolerance_days: int = 60
    ) -> Optional[ScholarlyArticle]:
        """Match an article by title and approximate date."""
        url = f"{self.api_base_url}/works"

        # Escape special characters in the title
        escaped_title = self._escape_query(title)

        # Build filter for title search and date range
        params = {
            "search": escaped_title,  # Use escaped title for search
            "per_page": 1
        }

        if publication_date:
            date_from = publication_date - timedelta(days=date_tolerance_days)
            date_to = publication_date + timedelta(days=date_tolerance_days)
            # Add date filter
            params["filter"] = (
                f"from_publication_date:{date_from.strftime('%Y-%m-%d')},"
                f"to_publication_date:{date_to.strftime('%Y-%m-%d')}"
            )

        result = self._make_request(url, params)
        if not result or "results" not in result or not result["results"]:
            return None

        # Return the first (best) match
        try:
            return self._parse_article(result["results"][0])
        except Exception as e:
            log.error(f"Failed to parse article: {e}")
            return None

    def get_by_id(self, article_id: str) -> Optional[ScholarlyArticle]:
        """Get an article by OpenAlex ID or DOI."""
        # Handle different ID formats
        if article_id.startswith("10."):  # DOI
            url = f"{self.api_base_url}/works/https://doi.org/{article_id}"
        elif article_id.startswith("W"):  # OpenAlex Work ID
            url = f"{self.api_base_url}/works/{article_id}"
        elif article_id.startswith("https://"):  # Full URL
            url = f"{self.api_base_url}/works/{article_id}"
        else:
            # Try as DOI
            url = f"{self.api_base_url}/works/https://doi.org/{article_id}"

        result = self._make_request(url)
        if not result:
            return None

        try:
            return self._parse_article(result)
        except Exception as e:
            log.error(f"Failed to parse article: {e}")
            return None

