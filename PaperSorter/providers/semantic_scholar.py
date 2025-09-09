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

"""Semantic Scholar database provider implementation."""

import requests
import time
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from .scholarly_database import ScholarlyDatabaseProvider, ScholarlyArticle
from ..log import log


class SemanticScholarProvider(ScholarlyDatabaseProvider):
    """Semantic Scholar API provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.api_base_url = config.get(
            "api_url", "https://api.semanticscholar.org/graph/v1/paper"
        )
        self.throttle_seconds = config.get("throttle", 1)
        self.last_request_time = 0
        self.max_retries = config.get("max_retries", 5)
        self.retry_backoff_base = config.get("retry_backoff_base", 2)

    @property
    def name(self) -> str:
        return "Semantic Scholar"

    @property
    def requires_api_key(self) -> bool:
        return True

    def _make_request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make a rate-limited request to the API with retry logic for rate limit errors."""
        headers = {"X-API-KEY": self.api_key} if self.api_key else {}

        for attempt in range(self.max_retries):
            # Apply throttling between all requests
            elapsed = time.time() - self.last_request_time
            if elapsed < self.throttle_seconds:
                time.sleep(self.throttle_seconds - elapsed)

            try:
                response = requests.get(url, headers=headers, params=params)
                self.last_request_time = time.time()

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404 and "Title match not found" in response.text:
                    # 404 "Title match not found" errors are expected - don't log as error
                    return None
                elif response.status_code == 429:
                    # Rate limited - handle with retry
                    if attempt < self.max_retries - 1:
                        # Extract retry-after header if available
                        retry_after = response.headers.get('retry-after')
                        if retry_after:
                            wait_time = float(retry_after)
                        else:
                            # Exponential backoff: 2, 4, 8, 16, etc. seconds
                            wait_time = self.retry_backoff_base ** (attempt + 1)

                        log.debug(
                            f"Rate limited by Semantic Scholar (429), "
                            f"retrying in {wait_time:.1f}s (attempt {attempt + 1}/{self.max_retries})"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        # Only log as error if all retries exhausted
                        log.error(
                            f"Semantic Scholar API error after {self.max_retries} retries: "
                            f"{response.status_code} - {response.text}"
                        )
                        return None
                else:
                    # Other errors - log immediately and don't retry
                    log.error(f"Semantic Scholar API error: {response.status_code} - {response.text}")
                    return None

            except requests.RequestException as e:
                log.error(f"Request failed: {e}")
                return None

        # Should not reach here unless max_retries is 0
        return None

    def _parse_article(self, data: Dict) -> ScholarlyArticle:
        """Parse Semantic Scholar response into ScholarlyArticle."""
        # Extract authors
        authors = []
        if data.get("authors"):
            authors = [author["name"] for author in data["authors"]]

        # Extract publication date
        pub_date = None
        if data.get("publicationDate"):
            try:
                parts = data["publicationDate"].split("-")
                pub_date = datetime(int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                pass

        # Extract abstract and tldr
        abstract = data.get("abstract")
        tldr = None
        if data.get("tldr") and data["tldr"].get("text"):
            tldr = data["tldr"]["text"]

        # Extract venue
        venue = data.get("venue") or data.get("journal", {}).get("name")

        # External IDs
        external_ids = data.get("externalIds", {})

        return ScholarlyArticle(
            title=data.get("title", ""),
            authors=authors,
            abstract=abstract,
            tldr=tldr,
            venue=venue,
            publication_date=pub_date,
            url=data.get("url"),
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
        """Search for articles using Semantic Scholar."""
        url = f"{self.api_base_url}/search"

        fields = "title,year,url,authors,abstract,venue,journal,publicationDate,externalIds,tldr"
        params = {
            "query": query,
            "fields": fields,
            "limit": limit
        }

        # Add year filter if specified
        if year_from and year_to:
            params["year"] = f"{year_from}-{year_to}"
        elif year_from:
            params["year"] = f"{year_from}-"
        elif year_to:
            params["year"] = f"-{year_to}"

        result = self._make_request(url, params)
        if not result or "data" not in result:
            return []

        articles = []
        for item in result["data"]:
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
        url = f"{self.api_base_url}/search/match"

        params = {
            "query": title,
            "fields": "title,url,authors,venue,journal,publicationDate,tldr,abstract,externalIds"
        }

        # Add date range if specified
        if publication_date:
            date_from = publication_date - timedelta(days=date_tolerance_days)
            date_to = publication_date + timedelta(days=date_tolerance_days)
            date_range = (
                f"{date_from.year}-{date_from.month:02d}-{date_from.day:02d}:"
                f"{date_to.year}-{date_to.month:02d}-{date_to.day:02d}"
            )
            params["publicationDateOrYear"] = date_range

        result = self._make_request(url, params)
        if not result or "data" not in result or not result["data"]:
            return None

        # Return the first (best) match
        try:
            return self._parse_article(result["data"][0])
        except Exception as e:
            log.error(f"Failed to parse article: {e}")
            return None

    def get_by_id(self, article_id: str) -> Optional[ScholarlyArticle]:
        """Get an article by Semantic Scholar ID or DOI."""
        # Handle DOI format
        if article_id.startswith("10."):
            article_id = f"DOI:{article_id}"

        url = f"{self.api_base_url}/{article_id}"
        params = {
            "fields": "title,url,authors,venue,journal,publicationDate,tldr,abstract,externalIds"
        }

        result = self._make_request(url, params)
        if not result:
            return None

        try:
            return self._parse_article(result)
        except Exception as e:
            log.error(f"Failed to parse article: {e}")
            return None

