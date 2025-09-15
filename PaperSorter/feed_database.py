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

import psycopg2
import psycopg2.extras
import pandas as pd
import re
import yaml
import unicodedata
from difflib import SequenceMatcher
from typing import List, Callable
from .log import log


class TitleNormalizer:
    """Framework for normalizing paper titles with configurable rules."""

    # Blacklist of bracket categories to remove (case-insensitive)
    # Based on survey of actual bracket-enclosed text in the database
    BRACKET_BLACKLIST = {
        'method', 'research', 'article', 'research papers', 'resources',
        'perspective', 'reviews', 'report', 'corrected', 'outlook',
        'errata', 'special section: symposium outlook', 'review',
        'methods', 'bioinformatics', 'research communications',
        'resource/methodology', 'mini-review', 'letter to the editor',
        'perspectives', 'interview', 'book review', 'editorial',
        'corrigendum', 'meeting review', 'hypothesis', 'commentary'
    }

    def __init__(self):
        """Initialize the normalizer with a list of rules."""
        self.rules: List[Callable[[str], str]] = [
            self.remove_trailing_period,  # Remove period first
            self.remove_blacklisted_brackets,  # Then remove brackets
            # Additional rules can be added here
        ]

    def normalize(self, title: str) -> str:
        """Apply all normalization rules to a title."""
        if not title:
            return title

        normalized = title
        for rule in self.rules:
            normalized = rule(normalized)

        return normalized

    def remove_blacklisted_brackets(self, title: str) -> str:
        """Remove bracket-enclosed text if it matches the blacklist (case-insensitive)."""
        # Match text in square brackets at the end of the title
        match = re.search(r'\[([^\]]+)\]\s*$', title)

        if match:
            bracket_content = match.group(1).strip()

            # Check if content matches any blacklisted item (case-insensitive)
            if bracket_content.lower() in self.BRACKET_BLACKLIST:
                # Remove the brackets and their content
                title_without_brackets = title[:match.start()]
                # Remove trailing whitespace
                return title_without_brackets.rstrip()

        return title

    def remove_trailing_period(self, title: str) -> str:
        """Remove a period at the end of the title."""
        if title and title.endswith('.'):
            return title[:-1].rstrip()
        return title


class FeedDatabase:
    dbfields = [
        "id",
        "shared",
        "title",
        "content",
        "author",
        "origin",
        "journal",
        "published",
        "link",
        "mediaUrl",
        "label",
        "score",
        "broadcasted",
        "tldr",
    ]

    def __init__(self, config_path="./config.yml"):
        # Load database configuration
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        db_config = config["db"]

        # Connect to PostgreSQL
        self.db = psycopg2.connect(
            host=db_config["host"],
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
        )
        self.db.autocommit = False
        self.cursor = self.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        self.update_idcache()

        # Initialize title normalizer
        self.title_normalizer = TitleNormalizer()

    def __del__(self):
        if hasattr(self, "db"):
            self.db.close()

    def __contains__(self, item):
        # Handle both string IDs and objects with item_id attribute
        if isinstance(item, str):
            return item in self.idcache
        elif hasattr(item, "item_id"):
            return item.item_id in self.idcache
        elif hasattr(item, "external_id"):
            return item.external_id in self.idcache
        else:
            return False

    def __len__(self):
        self.cursor.execute("SELECT COUNT(*) FROM feeds")
        return self.cursor.fetchone()["count"]

    def __getitem__(self, item_id):
        if isinstance(item_id, str):
            self.cursor.execute(
                "SELECT * FROM feeds WHERE external_id = %s", (item_id,)
            )
        else:
            self.cursor.execute("SELECT * FROM feeds WHERE id = %s", (item_id,))
        result = self.cursor.fetchone()
        if result:
            # Map to old field names for compatibility
            return {
                "id": result["external_id"],
                "shared": result.get("shared", 0),
                "title": result["title"],
                "content": result["content"],
                "author": result["author"],
                "origin": result["origin"],
                "published": int(result["published"].timestamp())
                if result["published"]
                else None,
                "link": result["link"],
                "mediaUrl": result["mediaurl"],
                "label": result.get("label"),
                "score": result.get("score"),
                "broadcasted": result.get("broadcasted"),
                "tldr": result["tldr"],
            }
        return None

    def keys(self):
        return self.idcache

    def update_idcache(self):
        self.cursor.execute(
            "SELECT external_id FROM feeds WHERE external_id IS NOT NULL"
        )
        self.idcache = set([row["external_id"] for row in self.cursor.fetchall()])

    def commit(self):
        self.db.commit()

    def insert_feed_item(
        self,
        external_id,
        title,
        content=None,
        author=None,
        origin=None,
        journal=None,
        link=None,
        published=None,
        tldr=None,
    ):
        """Insert a paper item directly with explicit fields."""
        # Normalize title
        if title:
            title = self.title_normalizer.normalize(title)

        # Clean content
        if content:
            content = remove_html_tags(content)

        # Insert into feeds table
        self.cursor.execute(
            """
            INSERT INTO feeds (external_id, title, content, author, origin, journal, published, link, tldr)
            VALUES (%s, %s, %s, %s, %s, %s, to_timestamp(%s), %s, %s)
            ON CONFLICT (external_id) DO NOTHING
            RETURNING id
        """,
            (external_id, title, content, author, origin, journal, published, link, tldr),
        )

        result = self.cursor.fetchone()
        if result:
            feed_id = result["id"]
            self.idcache.add(external_id)
            return feed_id

    def get_formatted_item(self, item_id):
        if isinstance(item_id, str):
            self.cursor.execute(
                "SELECT * FROM feeds WHERE external_id = %s", (item_id,)
            )
        else:
            self.cursor.execute("SELECT * FROM feeds WHERE id = %s", (item_id,))
        item = self.cursor.fetchone()
        if item:
            parts = []

            if item["title"]:
                parts.append(f"Title: {item['title']}")

            if item["author"]:
                parts.append(f"Authors: {item['author']}")

            if item.get("journal"):
                parts.append(f"Journal: {item['journal']}")
            elif item.get("origin"):
                parts.append(f"Journal: {item['origin']}")

            if item["content"]:
                parts.append(f"Abstract: {item['content']}")

            return "\n\n".join(parts)
        return None

    def build_dataframe_from_results(self, results):
        if not results:
            return pd.DataFrame(columns=self.dbfields).set_index("id")

        # Convert results to DataFrame with old field names for compatibility
        data = []
        for row in results:
            data.append(
                {
                    "id": row["external_id"],
                    "shared": row.get("shared", 0),
                    "title": row["title"],
                    "content": row["content"],
                    "author": row["author"],
                    "origin": row["origin"],
                    "published": int(row["published"].timestamp())
                    if row["published"]
                    else None,
                    "link": row["link"],
                    "mediaUrl": row["mediaurl"],
                    "label": row.get("label"),
                    "score": row.get("score"),
                    "broadcasted": row.get("broadcasted"),
                    "tldr": row["tldr"],
                }
            )

        return pd.DataFrame(data).set_index("id")

    def update_score(self, item_id, score, model_id):
        # Get feed_id based on item_id type
        if isinstance(item_id, str):
            self.cursor.execute(
                "SELECT id FROM feeds WHERE external_id = %s", (item_id,)
            )
        else:
            self.cursor.execute("SELECT id FROM feeds WHERE id = %s", (item_id,))
        result = self.cursor.fetchone()
        if result:
            feed_id = result["id"]
            self.cursor.execute(
                """
                INSERT INTO predicted_preferences (feed_id, model_id, score)
                VALUES (%s, %s, %s)
                ON CONFLICT (feed_id, model_id) DO UPDATE SET score = %s
            """,
                (feed_id, model_id, float(score), float(score)),
            )

    def update_tldr(self, item_id, tldr):
        if isinstance(item_id, str):
            self.cursor.execute(
                "UPDATE feeds SET tldr = %s WHERE external_id = %s", (tldr, item_id)
            )
        else:
            self.cursor.execute(
                "UPDATE feeds SET tldr = %s WHERE id = %s", (tldr, item_id)
            )

    def update_author(self, item_id, author):
        if isinstance(item_id, str):
            self.cursor.execute(
                "UPDATE feeds SET author = %s WHERE external_id = %s", (author, item_id)
            )
        else:
            self.cursor.execute(
                "UPDATE feeds SET author = %s WHERE id = %s", (author, item_id)
            )

    def update_origin(self, item_id, origin):
        if isinstance(item_id, str):
            self.cursor.execute(
                "UPDATE feeds SET origin = %s WHERE external_id = %s", (origin, item_id)
            )
        else:
            self.cursor.execute(
                "UPDATE feeds SET origin = %s WHERE id = %s", (origin, item_id)
            )

    def update_journal(self, item_id, journal):
        if isinstance(item_id, str):
            self.cursor.execute(
                "UPDATE feeds SET journal = %s WHERE external_id = %s", (journal, item_id)
            )
        else:
            self.cursor.execute(
                "UPDATE feeds SET journal = %s WHERE id = %s", (journal, item_id)
            )

    def update_content(self, item_id, content):
        """Update the content (abstract) field of a paper item."""
        if isinstance(item_id, str):
            self.cursor.execute(
                "UPDATE feeds SET content = %s WHERE external_id = %s", (content, item_id)
            )
        else:
            self.cursor.execute(
                "UPDATE feeds SET content = %s WHERE id = %s", (content, item_id)
            )

    def get_unscored_items(self, model_id=None, lookback_hours=None):
        """Get items that lack scores from specified model(s).

        Args:
            model_id: If provided, returns items missing scores for this specific model.
                     If None, returns items missing scores from ANY active model.
            lookback_hours: If provided, only return items added/published within this many hours.
        """
        if model_id is not None:
            # Get unscored items for a specific model
            query = """
                SELECT DISTINCT f.external_id
                FROM feeds f
                LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = %s
                WHERE f.external_id IS NOT NULL
                  AND pp.score IS NULL
            """
            params = [model_id]

            if lookback_hours is not None:
                query += " AND f.added >= NOW() - INTERVAL '%s hours'"
                params.append(lookback_hours)

            self.cursor.execute(query, params)
            return [row["external_id"] for row in self.cursor.fetchall()]

        # Original behavior: get items missing scores from any active model
        # Get active model IDs
        self.cursor.execute("SELECT id FROM models WHERE is_active = TRUE")
        active_model_ids = [row["id"] for row in self.cursor.fetchall()]
        active_model_count = len(active_model_ids)

        if active_model_count == 0:
            return []

        placeholders = ",".join(["%s"] * active_model_count)
        query = f"""
            SELECT f.external_id
            FROM feeds f
            LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id
                AND pp.model_id IN ({placeholders})
            WHERE f.external_id IS NOT NULL
        """
        params = list(active_model_ids)

        if lookback_hours is not None:
            query += " AND f.added >= NOW() - INTERVAL '%s hours'"
            params.append(lookback_hours)

        query += """
            GROUP BY f.id, f.external_id
            HAVING COUNT(pp.score) < %s
        """
        params.append(active_model_count)

        self.cursor.execute(query, params)
        return [row["external_id"] for row in self.cursor.fetchall()]

    def add_to_broadcast_queue(self, feed_id, channel_id):
        """Add an item to the broadcast queue (using merged broadcasts table)."""
        self.cursor.execute(
            """
            INSERT INTO broadcasts (feed_id, channel_id, broadcasted_time)
            VALUES (%s, %s, NULL)
            ON CONFLICT (feed_id, channel_id) DO NOTHING
        """,
            (feed_id, channel_id),
        )

    def normalize_title_for_duplicate_detection(self, title):
        """Normalize title for fuzzy duplicate detection.

        Removes common prefixes, suffixes, and normalizes the text to detect duplicates
        even when journals add headers like "[ARTICLE]" or suffixes.
        """
        if not title:
            return ""

        # Convert to lowercase
        title = title.lower()

        # Remove common academic prefixes in brackets or parentheses
        title = re.sub(
            r"^\s*\[[^\]]+\]\s*", "", title
        )  # Remove [ARTICLE], [PREPRINT], etc.
        title = re.sub(
            r"^\s*\([^\)]+\)\s*", "", title
        )  # Remove (Article), (Letter), etc.

        # Remove common suffixes
        title = re.sub(
            r"\s*[\(\[]?(preprint|published|article|letter|review|research|paper)[\)\]]?\s*$",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Normalize unicode characters (e.g., different types of dashes, quotes)
        title = unicodedata.normalize("NFKD", title)

        # Replace multiple spaces with single space
        title = re.sub(r"\s+", " ", title)

        # Remove special characters but keep alphanumeric and basic punctuation
        title = re.sub(r"[^\w\s\-\:\.\,]", " ", title)

        # Remove extra whitespace
        title = title.strip()

        return title

    def titles_are_similar(self, title1, title2, threshold=0.85):
        """Check if two titles are similar enough to be considered duplicates.

        Uses normalized titles and sequence matching to detect duplicates.
        """
        norm1 = self.normalize_title_for_duplicate_detection(title1)
        norm2 = self.normalize_title_for_duplicate_detection(title2)

        if not norm1 or not norm2:
            return False

        # Quick exact match check
        if norm1 == norm2:
            return True

        # Use sequence matcher for fuzzy matching
        similarity = SequenceMatcher(None, norm1, norm2).ratio()
        return similarity >= threshold

    def get_broadcast_queue_items(self, channel_id, limit=None, model_id=None):
        """Get unprocessed items from the broadcast queue (using merged broadcasts table)."""
        # If no model_id provided, get the most recent active model
        if model_id is None:
            self.cursor.execute("""
                SELECT id FROM models
                WHERE is_active = TRUE
                ORDER BY id DESC
                LIMIT 1
            """)
            result = self.cursor.fetchone()
            if not result:
                from .log import log
                log.warning(f"No active models found for channel {channel_id}, cannot retrieve broadcast queue items")
                return pd.DataFrame()
            model_id = result["id"]

        # Get unprocessed items from the queue (FIFO - oldest added first)
        query = """
            SELECT f.*, pp.score, bl.feed_id as queue_feed_id
            FROM broadcasts bl
            JOIN feeds f ON bl.feed_id = f.id
            LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = %s
            WHERE bl.channel_id = %s AND bl.broadcasted_time IS NULL
            ORDER BY f.added ASC
        """
        if limit:
            query += f" LIMIT {limit}"

        self.cursor.execute(query, (model_id, channel_id))
        items = []
        for row in self.cursor.fetchall():
            item = dict(row)
            # Keep source feed name in origin_source, display journal in origin
            item["origin_source"] = item.get("origin")
            # Prefer journal for display where origin was used previously
            if item.get("journal"):
                item["origin"] = item["journal"]
            items.append(item)

        # Convert to DataFrame to match the existing broadcast.py interface
        if items:
            df = pd.DataFrame(items)
            df.set_index("queue_feed_id", inplace=True)
            return df
        else:
            return pd.DataFrame()

    def mark_broadcast_queue_processed(self, feed_id, channel_id):
        """Mark an item in the broadcast queue as processed (using merged broadcasts table)."""
        self.cursor.execute(
            """
            UPDATE broadcasts
            SET broadcasted_time = CURRENT_TIMESTAMP
            WHERE feed_id = %s AND channel_id = %s
        """,
            (feed_id, channel_id),
        )

    def clear_old_broadcast_queue(self, days=30):
        """Clear old processed items from the broadcast queue (using merged broadcasts table)."""
        self.cursor.execute(
            """
            DELETE FROM broadcasts
            WHERE broadcasted_time < CURRENT_TIMESTAMP - INTERVAL '%s days'
        """,
            (days,),
        )

    def remove_duplicate_from_queue(self, feed_id, channel_id):
        """Remove an item from the broadcast queue without marking it as broadcasted."""
        self.cursor.execute(
            """
            DELETE FROM broadcasts
            WHERE feed_id = %s AND channel_id = %s AND broadcasted_time IS NULL
        """,
            (feed_id, channel_id),
        )

    def check_and_remove_duplicate_broadcasts(self, channel_id, lookback_months=3):
        """Check for duplicate items in the broadcast queue and remove them.

        Returns the number of duplicates removed.
        """
        # First, get recently broadcasted items for duplicate detection
        self.cursor.execute(
            """
            SELECT f.id as feed_id, f.title
            FROM broadcasts bl
            JOIN feeds f ON bl.feed_id = f.id
            WHERE bl.channel_id = %s
                AND bl.broadcasted_time IS NOT NULL
                AND bl.broadcasted_time >= CURRENT_TIMESTAMP - INTERVAL '%s months'
        """,
            (channel_id, lookback_months),
        )

        recent_broadcasts = []
        for row in self.cursor.fetchall():
            recent_broadcasts.append({"feed_id": row["feed_id"], "title": row["title"]})

        # Get unprocessed items from the queue
        self.cursor.execute(
            """
            SELECT f.id as feed_id, f.title
            FROM broadcasts bl
            JOIN feeds f ON bl.feed_id = f.id
            WHERE bl.channel_id = %s AND bl.broadcasted_time IS NULL
        """,
            (channel_id,),
        )

        queue_items = []
        for row in self.cursor.fetchall():
            queue_items.append({"feed_id": row["feed_id"], "title": row["title"]})

        # Check each queue item for duplicates
        removed_count = 0
        for queue_item in queue_items:
            is_duplicate = False

            # Check against recently broadcasted items
            for recent in recent_broadcasts:
                if self.titles_are_similar(queue_item["title"], recent["title"]):
                    is_duplicate = True
                    log.info(
                        f"Removing duplicate from queue - Paper ID: {queue_item['feed_id']}, "
                        f"Title: '{queue_item['title'][:80]}...' "
                        f"(similar to previously broadcasted paper {recent['feed_id']})"
                    )
                    break

            if is_duplicate:
                self.remove_duplicate_from_queue(queue_item["feed_id"], channel_id)
                removed_count += 1

        if removed_count > 0:
            log.info(
                f"Removed {removed_count} duplicate items from broadcast queue for channel {channel_id}"
            )

        return removed_count


def remove_html_tags(text, pattern=re.compile("<.*?>")):
    return pattern.sub(" ", text)
