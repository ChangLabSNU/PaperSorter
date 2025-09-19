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

"""RSS/Atom feed provider implementation."""

import feedparser
import psycopg2
import psycopg2.extras
import uuid
import ssl
import urllib.request
import urllib.error
import gzip
import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Iterator, Any
from ..db import DatabaseManager
from ..log import log
from .base import FeedProvider, FeedItem


class RSSProvider(FeedProvider):
    """Provider for RSS and Atom feeds."""

    def __init__(self, config: Dict[str, Any], db_manager: Optional[DatabaseManager] = None):
        """Initialize RSS provider with database configuration."""
        super().__init__(config)
        self.db_config = config["db"]
        self._conn = None
        self._manager = db_manager
        self._owns_manager = db_manager is None

        # Create an SSL context that doesn't verify certificates
        self._ssl_context = ssl.create_default_context()
        self._ssl_context.check_hostname = False
        self._ssl_context.verify_mode = ssl.CERT_NONE

    @property
    def conn(self):
        """Lazy database connection."""
        inner = getattr(self._conn, "_conn", self._conn)
        if self._conn is None or getattr(inner, "closed", True):
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
            if self._manager is None:
                self._manager = DatabaseManager.from_config(
                    self.db_config,
                    application_name="papersorter-provider-rss",
                )
                self._owns_manager = True
            self._conn = self._manager.connect()
        return self._conn

    def close(self) -> None:
        """Release any pooled connection and close owned manager."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            finally:
                self._conn = None

        if self._owns_manager and self._manager is not None:
            try:
                self._manager.close()
            except Exception:
                pass
            finally:
                self._manager = None

    def __del__(self):
        """Close database connection on cleanup."""
        try:
            self.close()
        except Exception:
            pass

    def get_sources(
        self, source_type: str = "rss", check_interval_hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get RSS sources that need updating."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=check_interval_hours)

        query = """
            SELECT id, name, source_type, url, added, last_updated, last_checked
            FROM papersorter.feed_sources
            WHERE source_type = %s
              AND (last_checked IS NULL OR last_checked < %s)
            ORDER BY last_checked ASC NULLS FIRST, id ASC
        """

        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (source_type, cutoff_time))
            return cur.fetchall()

    def get_items(
        self,
        source: Dict[str, Any],
        limit: Optional[int] = None,
        since: Optional[datetime] = None,
    ) -> Iterator[List[FeedItem]]:
        """Retrieve items from an RSS feed."""
        if not source.get("url"):
            log.error(
                f"No URL provided for RSS source: {source.get('name', 'Unknown')}"
            )
            return

        # Parse the feed with SSL verification disabled
        try:
            # Create a custom URL opener with our SSL context
            handlers = [urllib.request.HTTPSHandler(context=self._ssl_context)]
            opener = urllib.request.build_opener(*handlers)

            # Create a request with browser headers
            request = urllib.request.Request(source["url"])
            request.add_header(
                "User-Agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            )
            request.add_header(
                "Accept", "application/rss+xml, application/xml, text/xml, */*"
            )
            request.add_header("Accept-Language", "en-US,en;q=0.9")
            request.add_header("Accept-Encoding", "gzip, deflate")

            # Fetch and parse the feed
            with opener.open(request) as response:
                feed_content = response.read()

                # Handle gzip compression if present
                if response.headers.get("Content-Encoding") == "gzip":
                    feed_content = gzip.decompress(feed_content)

            # Try to decode content if it's bytes
            if isinstance(feed_content, bytes):
                try:
                    feed_content = feed_content.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        feed_content = feed_content.decode("latin-1")
                    except UnicodeDecodeError:
                        feed_content = feed_content.decode("utf-8", errors="ignore")

            # Clean up XML content
            feed_content = self._clean_xml_content(feed_content)

            # Check for common problem: invalid XML declaration
            if feed_content.startswith("<?xml") and "?>" in feed_content[:200]:
                xml_end = feed_content.find("?>")
                xml_declaration = feed_content[: xml_end + 2]
                # Check if there's content between XML declaration and root element
                next_tag_pos = feed_content.find("<", xml_end + 2)
                if next_tag_pos > xml_end + 2:
                    between_content = feed_content[xml_end + 2 : next_tag_pos].strip()
                    if between_content:
                        log.warning(
                            f"Found content between XML declaration and root element: {between_content[:50]}"
                        )
                        # Remove the problematic content
                        feed_content = xml_declaration + feed_content[next_tag_pos:]

            feed = feedparser.parse(feed_content)

            # Check for parsing errors
            if feed.bozo:
                log.warning(
                    f"Feed parsing error for {source['url']}: {feed.bozo_exception}"
                )

                # Debug: Save problematic feed for inspection
                if log.level <= 10:  # DEBUG level
                    debug_file = f"/tmp/feed_debug_{source['id']}.xml"
                    try:
                        with open(debug_file, "w") as f:
                            f.write(
                                feed_content
                                if isinstance(feed_content, str)
                                else str(feed_content)
                            )
                        log.debug(f"Saved problematic feed to {debug_file}")
                    except Exception:
                        pass

                # Try to continue anyway if we have entries
                if not feed.entries:
                    log.warning(
                        f"Standard parsing failed for {source['url']}, attempting manual extraction..."
                    )

                    # Last resort: try to extract entries manually with regex
                    entries = self._extract_entries_manually(feed_content)
                    if entries:
                        log.info(
                            f"✓ Manual extraction successful for {source['url']}: found {len(entries)} entries"
                        )
                        feed.entries = entries
                    else:
                        log.error(
                            f"✗ Failed to extract any entries from {source['url']} - skipping this feed"
                        )
                        return
                else:
                    log.info(
                        f"✓ Despite XML errors, successfully parsed {len(feed.entries)} entries from {source['url']}"
                    )
            else:
                # No parsing errors
                if feed.entries:
                    log.debug(
                        f"✓ Successfully parsed {len(feed.entries)} entries from {source['url']}"
                    )
        except urllib.error.HTTPError as e:
            if e.code == 403:
                log.error(
                    f"Access forbidden for {source['url']} - the site may be blocking automated requests"
                )
            elif e.code == 404:
                log.error(
                    f"Feed not found at {source['url']} - the URL may have changed"
                )
            else:
                log.error(
                    f"HTTP error {e.code} fetching feed from {source['url']}: {e}"
                )
            return
        except urllib.error.URLError as e:
            log.error(f"Network error fetching feed from {source['url']}: {e}")
            return
        except Exception as e:
            log.error(f"Unexpected error fetching feed from {source['url']}: {e}")
            return

        # Process entries
        items = []
        entries = feed.entries[:limit] if limit else feed.entries

        if not entries:
            log.info(f"No entries to process from {source['url']}")
            return

        for entry in entries:
            # Generate external ID
            external_id = self._generate_external_id(entry)

            # Parse published date
            published = self._parse_published_date(entry)

            # Skip old items if since is specified
            if since and published < since:
                log.debug(
                    f"Skipping old entry '{entry.get('title', 'Unknown')}' published at {published}"
                )
                continue

            # Create FeedItem
            item = FeedItem(
                external_id=external_id,
                title=entry.get("title", "Untitled"),
                content=entry.get("summary", entry.get("description", "")),
                author=entry.get("author", ""),
                origin=source["name"],
                journal=source["name"],
                link=entry.get("link", ""),
                published=published,
            )

            items.append(item)

            # Yield in batches
            if len(items) >= 50:
                yield items
                items = []

        # Yield remaining items
        if items:
            yield items

    def update_source_timestamp(self, source_id: int, has_new_items: bool = False):
        """Update the last_checked timestamp and optionally last_updated for a source."""
        if has_new_items:
            # Update both last_checked and last_updated
            query = """
                UPDATE papersorter.feed_sources
                SET last_checked = now(), last_updated = now()
                WHERE id = %s
            """
            with self.conn.cursor() as cur:
                cur.execute(query, (source_id,))
                self.conn.commit()
            log.debug(f"Updated last_checked and last_updated for source {source_id}")
        else:
            # Update only last_checked
            query = """
                UPDATE papersorter.feed_sources
                SET last_checked = now()
                WHERE id = %s
            """
            with self.conn.cursor() as cur:
                cur.execute(query, (source_id,))
                self.conn.commit()
            log.debug(f"Updated last_checked for source {source_id}")

    def validate_source(self, source: Dict[str, Any]) -> bool:
        """Validate that source has required URL field."""
        return bool(source.get("url"))

    def _clean_xml_content(self, content: str) -> str:
        """Clean up common XML issues in feed content."""
        # Remove any content before the first < character (BOM, etc.)
        first_tag = content.find("<")
        if first_tag > 0:
            content = content[first_tag:]

        # Remove control characters except newline, tab, and carriage return
        content = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", content)

        # Fix unescaped ampersands (but not in entities)
        content = re.sub(
            r"&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", content
        )

        # Fix common entity issues
        content = content.replace("&nbsp;", "&#160;")

        # Remove any content after the last closing tag
        last_close = content.rfind(">")
        if last_close > 0 and last_close < len(content) - 1:
            content = content[: last_close + 1]

        # Try to fix mismatched tags by removing incomplete ones at the end
        # This is a last resort for badly formed feeds
        if "<" in content[-10:] and ">" not in content[-10:]:
            last_complete = content.rfind(">")
            if last_complete > 0:
                content = content[: last_complete + 1]

        return content

    def _extract_entries_manually(self, content: str) -> List[Dict]:
        """Manually extract entries from XML when feedparser fails."""
        entries = []

        # Try to find item or entry tags
        item_pattern = re.compile(
            r"<(item|entry)[^>]*>(.*?)</\1>", re.DOTALL | re.IGNORECASE
        )

        for match in item_pattern.finditer(content):
            entry_content = match.group(2)
            entry = {}

            # Extract title
            title_match = re.search(
                r"<title[^>]*>(.*?)</title>", entry_content, re.DOTALL | re.IGNORECASE
            )
            if title_match:
                entry["title"] = self._clean_cdata(title_match.group(1))

            # Extract link
            link_match = re.search(
                r"<link[^>]*>(.*?)</link>", entry_content, re.DOTALL | re.IGNORECASE
            )
            if not link_match:
                # Try alternate link format
                link_match = re.search(
                    r'<link[^>]*href="([^"]+)"', entry_content, re.IGNORECASE
                )
            if link_match:
                entry["link"] = self._clean_cdata(link_match.group(1))

            # Extract description/summary
            desc_match = re.search(
                r"<(description|summary|content)[^>]*>(.*?)</\1>",
                entry_content,
                re.DOTALL | re.IGNORECASE,
            )
            if desc_match:
                entry["summary"] = self._clean_cdata(desc_match.group(2))

            # Extract published date
            date_match = re.search(
                r"<(pubDate|published|updated|dc:date)[^>]*>(.*?)</\1>",
                entry_content,
                re.DOTALL | re.IGNORECASE,
            )
            if date_match:
                entry["published"] = self._clean_cdata(date_match.group(2))

            # Extract author
            author_match = re.search(
                r"<(author|dc:creator)[^>]*>(.*?)</\1>",
                entry_content,
                re.DOTALL | re.IGNORECASE,
            )
            if author_match:
                entry["author"] = self._clean_cdata(author_match.group(2))

            # Extract guid/id
            guid_match = re.search(
                r"<(guid|id)[^>]*>(.*?)</\1>", entry_content, re.DOTALL | re.IGNORECASE
            )
            if guid_match:
                entry["id"] = self._clean_cdata(guid_match.group(2))

            if "title" in entry or "link" in entry:
                entries.append(entry)

        return entries

    def _clean_cdata(self, text: str) -> str:
        """Clean CDATA sections and HTML entities."""
        # Remove CDATA wrapper
        text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
        # Decode basic HTML entities
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#39;", "'")
        # Strip HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        return text.strip()

    def _generate_external_id(self, entry: dict) -> str:
        """Generate external ID for feed entry.

        Priority:
        1. Use guid if present (as-is, regardless of format)
        2. Use id if present (as-is, regardless of format)
        3. Generate UUID v5 from link URL
        4. Generate UUID v5 from title
        5. Fallback to random UUID v4
        """
        # Try to use guid first (most stable identifier in RSS/ATOM)
        if hasattr(entry, "guid") and entry.guid:
            return str(entry.guid)

        # Try to use id second
        if hasattr(entry, "id") and entry.id:
            return str(entry.id)

        # Generate UUID v5 from URL
        entry_url = entry.get("link", "")
        if entry_url:
            return str(uuid.uuid5(uuid.NAMESPACE_URL, entry_url))

        # Generate UUID v5 from title as last resort
        entry_title = entry.get("title", "")
        if entry_title:
            return str(uuid.uuid5(uuid.NAMESPACE_URL, entry_title))

        # Fallback to random UUID
        return str(uuid.uuid4())

    def _parse_published_date(self, entry: dict) -> datetime:
        """Parse published date from feed entry."""
        import time as time_module

        # Debug: log available fields in entry
        if log.level <= 10:  # DEBUG level
            available_attrs = [attr for attr in dir(entry) if not attr.startswith("_")]
            log.debug(
                f"Entry attributes for '{getattr(entry, 'title', 'Unknown')}': {available_attrs}"
            )

        # Try parsed date fields first (these are time.struct_time objects)
        date_fields = ["published_parsed", "updated_parsed", "created_parsed"]

        for field in date_fields:
            if hasattr(entry, field) and getattr(entry, field):
                try:
                    time_tuple = getattr(entry, field)
                    # Convert struct_time to timestamp (assuming UTC)
                    timestamp = time_module.mktime(time_tuple)
                    # Create datetime with UTC timezone (using non-deprecated method)
                    return datetime.fromtimestamp(timestamp, tz=timezone.utc)
                except Exception as e:
                    log.debug(f"Failed to parse {field}: {e}")

        # Try string date fields as fallback
        string_fields = ["published", "updated", "created", "pubDate"]

        # Also check for namespaced fields
        for field in string_fields:
            # Check direct field
            if hasattr(entry, field) and getattr(entry, field):
                try:
                    date_string = getattr(entry, field)
                    # Use feedparser's date parsing utility
                    parsed_time = feedparser._parse_date(date_string)
                    if parsed_time:
                        timestamp = time_module.mktime(parsed_time)
                        # Create datetime with UTC timezone (using non-deprecated method)
                        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
                except Exception as e:
                    log.debug(f"Failed to parse {field}: {e}")

            # Check in entry dict directly (for dict-like entries)
            if isinstance(entry, dict) and field in entry and entry[field]:
                try:
                    date_string = entry[field]
                    parsed_time = feedparser._parse_date(date_string)
                    if parsed_time:
                        timestamp = time_module.mktime(parsed_time)
                        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
                except Exception as e:
                    log.debug(f"Failed to parse dict field {field}: {e}")

        # Default to current time only if no date found
        return datetime.now(timezone.utc)
