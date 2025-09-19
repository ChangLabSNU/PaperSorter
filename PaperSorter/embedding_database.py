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
from pgvector.psycopg2 import register_vector
import numpy as np
from .config import get_config
from .db import DatabaseManager
import openai
from typing import Optional
from .log import log


class EmbeddingDatabase:
    dtype = np.float64

    def __init__(self, db_manager=None, connection: Optional[psycopg2.extensions.connection] = None):
        config = get_config().raw

        db_config = config["db"]
        self.config = config

        self._manager = db_manager
        self._owns_manager = False

        if connection is not None:
            self.db = connection
            self._owns_connection = False
        else:
            if self._manager is None:
                self._manager = DatabaseManager.from_config(
                    db_config,
                    application_name="papersorter-embedding-db",
                )
                self._owns_manager = True
            self.db = self._manager.connect()
            self._owns_connection = True

        self.cursor = self.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Register pgvector extension on the underlying psycopg2 connection
        register_vector(getattr(self.db, "_conn", self.db))

        # Set up OpenAI client for embeddings
        embedding_config = config.get("embedding_api", {})
        self.api_key = embedding_config.get("api_key")
        self.api_url = embedding_config.get("api_url", "https://api.openai.com/v1")
        self.embedding_model = embedding_config.get("model", "text-embedding-3-large")
        self.embedding_dimensions = embedding_config.get("dimensions")
        self.openai_client = (
            openai.OpenAI(api_key=self.api_key, base_url=self.api_url)
            if self.api_key
            else None
        )

        self._closed = False

    def close(self):
        if getattr(self, "_closed", False):
            return

        cursor = getattr(self, "cursor", None)
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
            finally:
                self.cursor = None

        connection = getattr(self, "db", None)
        if connection is not None and getattr(self, "_owns_connection", False):
            try:
                connection.close()
            except Exception:
                pass

        if getattr(self, "_owns_manager", False) and getattr(self, "_manager", None) is not None:
            try:
                self._manager.close()
            except Exception:
                pass

        self._closed = True

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def __len__(self):
        self.cursor.execute("SELECT COUNT(*) FROM embeddings")
        return self.cursor.fetchone()["count"]

    def __contains__(self, item):
        # Get feed_id from external_id
        self.cursor.execute("SELECT id FROM feeds WHERE external_id = %s", (item,))
        result = self.cursor.fetchone()
        if not result:
            return False

        feed_id = result["id"]
        self.cursor.execute(
            "SELECT COUNT(*) FROM embeddings WHERE feed_id = %s", (feed_id,)
        )
        return self.cursor.fetchone()["count"] > 0

    def keys(self):
        self.cursor.execute("""
            SELECT f.external_id
            FROM embeddings e
            JOIN feeds f ON e.feed_id = f.id
            WHERE f.external_id IS NOT NULL
        """)
        return set([row["external_id"] for row in self.cursor.fetchall()])

    def __getitem__(self, key):
        if isinstance(key, str):
            # Get feed_id from external_id
            self.cursor.execute("SELECT id FROM feeds WHERE external_id = %s", (key,))
            result = self.cursor.fetchone()
            if not result:
                raise KeyError(f"No paper found with external_id: {key}")

            feed_id = result["id"]
            self.cursor.execute(
                "SELECT embedding FROM embeddings WHERE feed_id = %s", (feed_id,)
            )
            result = self.cursor.fetchone()
            if not result:
                raise KeyError(f"No embedding found for external_id: {key}")

            # Convert pgvector to numpy array
            return np.array(result["embedding"], dtype=self.dtype)

        elif isinstance(key, list):
            embeddings = []
            for k in key:
                # Get feed_id from external_id
                self.cursor.execute("SELECT id FROM feeds WHERE external_id = %s", (k,))
                result = self.cursor.fetchone()
                if not result:
                    raise KeyError(f"No paper found with external_id: {k}")

                feed_id = result["id"]
                self.cursor.execute(
                    "SELECT embedding FROM embeddings WHERE feed_id = %s", (feed_id,)
                )
                result = self.cursor.fetchone()
                if not result:
                    raise KeyError(f"No embedding found for external_id: {k}")

                embeddings.append(np.array(result["embedding"], dtype=self.dtype))

            return np.array(embeddings)
        else:
            raise TypeError("Key should be str or list of str.")

    def __setitem__(self, key, value):
        if not isinstance(value, np.ndarray):
            value = np.array(value)

        assert value.dtype == self.dtype

        # Get feed_id from external_id
        self.cursor.execute("SELECT id FROM feeds WHERE external_id = %s", (key,))
        result = self.cursor.fetchone()
        if not result:
            raise KeyError(f"No paper found with external_id: {key}")

        feed_id = result["id"]

        # Convert numpy array to list for pgvector
        embedding_list = value.tolist()

        # Insert or update embedding
        self.cursor.execute(
            """
            INSERT INTO embeddings (feed_id, embedding)
            VALUES (%s, %s)
            ON CONFLICT (feed_id) DO UPDATE SET embedding = %s
        """,
            (feed_id, embedding_list, embedding_list),
        )

        self.db.commit()

    def write_batch(self):
        """Context manager for batch embedding insertions.

        Delays commits until the context exits for better performance.
        Usage:
            with embdb.write_batch() as batch:
                batch.insert(feed_id1, embedding1)
                batch.insert(feed_id2, embedding2)
        """
        return EmbeddingDatabaseWriteBatch(self)

    def insert_embedding(self, feed_id, embedding):
        """Insert or update an embedding for a feed.

        Args:
            feed_id: The feed ID to insert embedding for
            embedding: The embedding vector (numpy array or list)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Convert to numpy array if needed
            if not isinstance(embedding, np.ndarray):
                embedding = np.array(embedding)

            # Insert or update embedding
            self.cursor.execute(
                """
                INSERT INTO embeddings (feed_id, embedding)
                VALUES (%s, %s)
                ON CONFLICT (feed_id) DO UPDATE
                SET embedding = EXCLUDED.embedding
                """,
                (feed_id, embedding.tolist() if isinstance(embedding, np.ndarray) else embedding)
            )
            self.db.commit()
            return True
        except Exception as e:
            log.error(f"Failed to insert embedding for feed {feed_id}: {e}")
            self.db.rollback()
            return False

    def filter_feeds_without_embeddings(self, feed_ids):
        """Filter feed IDs to return only those without embeddings.

        Args:
            feed_ids: List of feed IDs to check

        Returns:
            List of feed IDs that don't have embeddings
        """
        if not feed_ids:
            return []

        # Ensure feed_ids is a list
        if not isinstance(feed_ids, list):
            feed_ids = [feed_ids]

        if len(feed_ids) == 1:
            # Single feed - use simple query
            self.cursor.execute(
                """
                SELECT %s AS feed_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM embeddings WHERE feed_id = %s
                )
                """, (feed_ids[0], feed_ids[0])
            )
        else:
            # Multiple feeds - use efficient EXCEPT query
            self.cursor.execute(
                """
                SELECT unnest(%s::bigint[]) AS feed_id
                EXCEPT
                SELECT feed_id FROM embeddings WHERE feed_id = ANY(%s::bigint[])
                """, (feed_ids, feed_ids)
            )

        return [row["feed_id"] for row in self.cursor.fetchall()]

    def find_similar(self, feed_id, limit, user_id, model_id, channel_id):
        """Find similar articles using pgvector similarity search"""

        # Build the SELECT fields based on include_content parameter
        select_fields = """
                    sf.feed_id,
                    f.external_id,
                    f.title,
                    f.author,
                    COALESCE(f.journal, f.origin) AS origin,
                    f.link,
                    EXTRACT(EPOCH FROM f.published)::integer as published,
                    sf.similarity,
                    pp.score as predicted_score,
                    CASE WHEN bl_share.feed_id IS NOT NULL AND bl_share.broadcasted_time IS NULL THEN true ELSE false END as shared,
                    CASE WHEN bl_share.feed_id IS NOT NULL AND bl_share.broadcasted_time IS NOT NULL THEN true ELSE false END as broadcasted,
                    pf.score as label,
                    COALESCE(vote_counts.positive_votes, 0) as positive_votes,
                    COALESCE(vote_counts.negative_votes, 0) as negative_votes"""

        self.cursor.execute(
            f"""
            WITH similar_feeds AS (
                SELECT
                    feed_id,
                    1 - (embedding <=> (SELECT embedding FROM embeddings WHERE feed_id = %s)) as similarity
                FROM embeddings
                WHERE feed_id != %s
                ORDER BY embedding <=> (SELECT embedding FROM embeddings WHERE feed_id = %s)
                LIMIT %s
            ),
            user_prefs AS (
                SELECT DISTINCT ON (feed_id)
                    feed_id,
                    score
                FROM preferences
                WHERE source IN ('interactive', 'alert-feedback')
                    AND user_id = %s
                    AND feed_id IN (SELECT feed_id FROM similar_feeds)
                ORDER BY feed_id, id DESC
            ),
            vote_counts AS (
                SELECT
                    feed_id,
                    SUM(CASE WHEN score = 1 THEN 1 ELSE 0 END) as positive_votes,
                    SUM(CASE WHEN score = 0 THEN 1 ELSE 0 END) as negative_votes
                FROM preferences
                WHERE source IN ('interactive', 'alert-feedback')
                    AND feed_id IN (SELECT feed_id FROM similar_feeds)
                GROUP BY feed_id
            )
            SELECT
                {select_fields}
            FROM similar_feeds sf
            JOIN feeds f ON sf.feed_id = f.id
            LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = %s
            LEFT JOIN broadcasts bl_share ON f.id = bl_share.feed_id AND bl_share.channel_id = %s
            LEFT JOIN user_prefs pf ON f.id = pf.feed_id
            LEFT JOIN vote_counts ON f.id = vote_counts.feed_id
            ORDER BY sf.similarity DESC, f.added DESC
        """,
            (feed_id, feed_id, feed_id, limit, user_id, model_id, channel_id),
        )
        results = self.cursor.fetchall()
        if not results:
            # Check if the source feed_id exists
            self.cursor.execute(
                "SELECT 1 FROM embeddings WHERE feed_id = %s", (feed_id,)
            )
            if not self.cursor.fetchone():
                raise KeyError(f"No embedding found for feed_id: {feed_id}")

        return results

    def search_by_text(self, query_text, limit, user_id, model_id, channel_id):
        """Search for articles by text query using embedding similarity"""
        if not self.openai_client:
            raise ValueError("OpenAI client not configured for embeddings")

        # Generate embedding for the query
        params = {"input": [query_text], "model": self.embedding_model}

        # Add dimensions if specified
        if self.embedding_dimensions:
            params["dimensions"] = self.embedding_dimensions

        response = self.openai_client.embeddings.create(**params)
        query_embedding = response.data[0].embedding

        # Build the SELECT fields
        select_fields = """
                    sf.feed_id,
                    f.external_id,
                    f.title,
                    f.author,
                    COALESCE(f.journal, f.origin) AS origin,
                    f.link,
                    EXTRACT(EPOCH FROM f.published)::integer as published,
                    EXTRACT(EPOCH FROM f.added)::integer as added,
                    sf.similarity,
                    pp.score as predicted_score,
                    CASE WHEN bl_share.feed_id IS NOT NULL AND bl_share.broadcasted_time IS NULL THEN true ELSE false END as shared,
                    CASE WHEN bl_share.feed_id IS NOT NULL AND bl_share.broadcasted_time IS NOT NULL THEN true ELSE false END as broadcasted,
                    pf.score as label,
                    COALESCE(vote_counts.positive_votes, 0) as positive_votes,
                    COALESCE(vote_counts.negative_votes, 0) as negative_votes"""

        # Perform similarity search using the query embedding
        self.cursor.execute(
            f"""
            WITH similar_feeds AS (
                SELECT
                    feed_id,
                    1 - (embedding <=> %s::vector) as similarity
                FROM embeddings
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            ),
            user_prefs AS (
                SELECT DISTINCT ON (feed_id)
                    feed_id,
                    score
                FROM preferences
                WHERE source IN ('interactive', 'alert-feedback')
                    AND user_id = %s
                    AND feed_id IN (SELECT feed_id FROM similar_feeds)
                ORDER BY feed_id, id DESC
            ),
            vote_counts AS (
                SELECT
                    feed_id,
                    SUM(CASE WHEN score = 1 THEN 1 ELSE 0 END) as positive_votes,
                    SUM(CASE WHEN score = 0 THEN 1 ELSE 0 END) as negative_votes
                FROM preferences
                WHERE source IN ('interactive', 'alert-feedback')
                    AND feed_id IN (SELECT feed_id FROM similar_feeds)
                GROUP BY feed_id
            )
            SELECT
                {select_fields}
            FROM similar_feeds sf
            JOIN feeds f ON sf.feed_id = f.id
            LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = %s
            LEFT JOIN broadcasts bl_share ON f.id = bl_share.feed_id AND bl_share.channel_id = %s
            LEFT JOIN user_prefs pf ON f.id = pf.feed_id
            LEFT JOIN vote_counts ON f.id = vote_counts.feed_id
            ORDER BY sf.similarity DESC, f.added DESC
        """,
            (query_embedding, query_embedding, limit, user_id, model_id, channel_id),
        )

        results = self.cursor.fetchall()
        return results


class EmbeddingDatabaseWriteBatch:
    """Context manager for batch embedding insertions with delayed commit."""

    def __init__(self, edb):
        self.edb = edb
        self.db = edb.db
        self.cursor = edb.cursor
        self.dtype = edb.dtype
        self.batch_items = []
        self.success_count = 0
        self.fail_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            try:
                # Commit all successful insertions
                self.db.commit()
                log.info(f"Batch insert completed: {self.success_count} successful, {self.fail_count} failed")
            except Exception as e:
                log.error(f"Failed to commit batch: {e}")
                self.db.rollback()
        else:
            # Rollback on error
            self.db.rollback()
            log.error(f"Batch insert failed, rolling back. {self.success_count} were attempted")
            self.batch_items.clear()

    def insert(self, feed_id, embedding):
        """Insert an embedding by feed_id without immediate commit.

        Args:
            feed_id: The feed ID to insert embedding for
            embedding: The embedding vector (numpy array or list)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Convert to numpy array if needed
            if not isinstance(embedding, np.ndarray):
                embedding = np.array(embedding)

            # Convert to list for pgvector
            embedding_list = embedding.tolist() if isinstance(embedding, np.ndarray) else embedding

            # Insert or update embedding (no commit)
            self.cursor.execute(
                """
                INSERT INTO embeddings (feed_id, embedding)
                VALUES (%s, %s)
                ON CONFLICT (feed_id) DO UPDATE
                SET embedding = EXCLUDED.embedding
                """,
                (feed_id, embedding_list)
            )
            self.success_count += 1
            self.batch_items.append((feed_id, embedding))  # Keep track for potential rollback
            return True
        except Exception as e:
            log.error(f"Failed to insert embedding for feed {feed_id}: {e}")
            self.fail_count += 1
            # Don't rollback here - let other inserts continue
            return False

    def __setitem__(self, key, value):
        """Legacy interface for backward compatibility with external_id."""
        if not isinstance(value, np.ndarray):
            value = np.array(value)

        assert value.dtype == self.dtype

        # Get feed_id from external_id
        self.cursor.execute("SELECT id FROM feeds WHERE external_id = %s", (key,))
        result = self.cursor.fetchone()
        if result:
            feed_id = result["id"]
            self.insert(feed_id, value)
        else:
            log.error(f"No feed found with external_id: {key}")
            self.fail_count += 1
