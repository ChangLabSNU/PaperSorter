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
import yaml
import openai


class EmbeddingDatabase:
    dtype = np.float64

    def __init__(self, config_path="./config.yml"):
        # Load database configuration
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        db_config = config["db"]
        self.config = config

        # Connect to PostgreSQL
        self.db = psycopg2.connect(
            host=db_config["host"],
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
        )
        self.db.autocommit = False
        self.cursor = self.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Register pgvector extension
        register_vector(self.db)

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

    def __del__(self):
        if hasattr(self, "db"):
            self.db.close()

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
                raise KeyError(f"No feed found with external_id: {key}")

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
                    raise KeyError(f"No feed found with external_id: {k}")

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
            raise KeyError(f"No feed found with external_id: {key}")

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
        return EmbeddingDatabaseWriteBatch(self)

    def find_similar(
        self, feed_id, limit=30, user_id=None, model_id=None, include_content=False
    ):
        """Find similar articles using pgvector similarity search"""
        # Use provided model_id or default to 1
        if model_id is None:
            model_id = 1
        # Use WITH statement to avoid transferring embedding vectors
        # Build the SELECT fields based on include_content parameter
        select_fields = """
                    e.feed_id,
                    f.external_id,
                    f.title,
                    f.author,
                    f.origin,
                    f.link,
                    EXTRACT(EPOCH FROM f.published)::integer as published,
                    1 - (e.embedding <=> se.embedding) as similarity,
                    pp.score as predicted_score,
                    CASE WHEN p.score > 0 THEN true ELSE false END as starred,
                    CASE WHEN bl.broadcasted_time IS NOT NULL THEN true ELSE false END as broadcasted,
                    pf.score as label,
                    COALESCE(vote_counts.positive_votes, 0) as positive_votes,
                    COALESCE(vote_counts.negative_votes, 0) as negative_votes"""

        if include_content:
            select_fields += (
                ",\n                    f.content,\n                    f.tldr"
            )

        if user_id is None:
            # If no user_id provided, don't filter preferences
            self.cursor.execute(
                f"""
                WITH source_embedding AS (
                    SELECT embedding
                    FROM embeddings
                    WHERE feed_id = %s
                ),
                all_prefs AS (
                    SELECT DISTINCT ON (feed_id)
                        feed_id,
                        score
                    FROM preferences
                    WHERE source IN ('interactive', 'alert-feedback')
                    ORDER BY feed_id, id DESC
                )
                SELECT
                    {select_fields}
                FROM embeddings e
                CROSS JOIN source_embedding se
                JOIN feeds f ON e.feed_id = f.id
                LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = %s
                LEFT JOIN preferences p ON f.id = p.feed_id AND p.source = 'feed-star'
                LEFT JOIN broadcasts bl ON f.id = bl.feed_id
                LEFT JOIN all_prefs pf ON f.id = pf.feed_id
                LEFT JOIN (
                    SELECT
                        feed_id,
                        SUM(CASE WHEN score = 1 THEN 1 ELSE 0 END) as positive_votes,
                        SUM(CASE WHEN score = 0 THEN 1 ELSE 0 END) as negative_votes
                    FROM preferences
                    WHERE source IN ('interactive', 'alert-feedback')
                    GROUP BY feed_id
                ) vote_counts ON f.id = vote_counts.feed_id
                WHERE e.feed_id != %s
                ORDER BY e.embedding <=> se.embedding
                LIMIT %s
            """,
                (feed_id, model_id, feed_id, limit),
            )
        else:
            # Filter preferences by user_id
            self.cursor.execute(
                f"""
                WITH source_embedding AS (
                    SELECT embedding
                    FROM embeddings
                    WHERE feed_id = %s
                ),
                user_prefs AS (
                    SELECT DISTINCT ON (feed_id)
                        feed_id,
                        score
                    FROM preferences
                    WHERE source IN ('interactive', 'alert-feedback') AND user_id = %s
                    ORDER BY feed_id, id DESC
                )
                SELECT
                    {select_fields}
                FROM embeddings e
                CROSS JOIN source_embedding se
                JOIN feeds f ON e.feed_id = f.id
                LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = %s
                LEFT JOIN preferences p ON f.id = p.feed_id AND p.source = 'feed-star' AND p.user_id = %s
                LEFT JOIN broadcasts bl ON f.id = bl.feed_id
                LEFT JOIN user_prefs pf ON f.id = pf.feed_id
                LEFT JOIN (
                    SELECT
                        feed_id,
                        SUM(CASE WHEN score = 1 THEN 1 ELSE 0 END) as positive_votes,
                        SUM(CASE WHEN score = 0 THEN 1 ELSE 0 END) as negative_votes
                    FROM preferences
                    WHERE source IN ('interactive', 'alert-feedback')
                    GROUP BY feed_id
                ) vote_counts ON f.id = vote_counts.feed_id
                WHERE e.feed_id != %s
                ORDER BY e.embedding <=> se.embedding
                LIMIT %s
            """,
                (feed_id, user_id, model_id, user_id, feed_id, limit),
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

    def search_by_text(
        self, query_text, limit=50, user_id=None, model_id=None, include_content=False
    ):
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

        # Use provided model_id or default to 1
        if model_id is None:
            model_id = 1

        # Build the SELECT fields based on include_content parameter
        select_fields = """
                    e.feed_id,
                    f.external_id,
                    f.title,
                    f.author,
                    f.origin,
                    f.link,
                    EXTRACT(EPOCH FROM f.published)::integer as published,
                    EXTRACT(EPOCH FROM f.added)::integer as added,
                    1 - (e.embedding <=> %s::vector) as similarity,
                    pp.score as predicted_score,
                    CASE WHEN p.score > 0 THEN true ELSE false END as starred,
                    CASE WHEN bl.broadcasted_time IS NOT NULL THEN true ELSE false END as broadcasted,
                    pf.score as label,
                    COALESCE(vote_counts.positive_votes, 0) as positive_votes,
                    COALESCE(vote_counts.negative_votes, 0) as negative_votes"""

        if include_content:
            select_fields += (
                ",\n                    f.content,\n                    f.tldr"
            )

        # Perform similarity search using the query embedding
        if user_id is None:
            # If no user_id provided, don't filter preferences
            self.cursor.execute(
                f"""
                WITH all_prefs AS (
                    SELECT DISTINCT ON (feed_id)
                        feed_id,
                        score
                    FROM preferences
                    WHERE source IN ('interactive', 'alert-feedback')
                    ORDER BY feed_id, id DESC
                )
                SELECT
                    {select_fields}
                FROM embeddings e
                JOIN feeds f ON e.feed_id = f.id
                LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = %s
                LEFT JOIN preferences p ON f.id = p.feed_id AND p.source = 'feed-star'
                LEFT JOIN broadcasts bl ON f.id = bl.feed_id
                LEFT JOIN all_prefs pf ON f.id = pf.feed_id
                LEFT JOIN (
                    SELECT
                        feed_id,
                        SUM(CASE WHEN score = 1 THEN 1 ELSE 0 END) as positive_votes,
                        SUM(CASE WHEN score = 0 THEN 1 ELSE 0 END) as negative_votes
                    FROM preferences
                    WHERE source IN ('interactive', 'alert-feedback')
                    GROUP BY feed_id
                ) vote_counts ON f.id = vote_counts.feed_id
                ORDER BY e.embedding <=> %s::vector
                LIMIT %s
            """,
                (query_embedding, model_id, query_embedding, limit),
            )
        else:
            # Filter preferences by user_id
            self.cursor.execute(
                f"""
                WITH user_prefs AS (
                    SELECT DISTINCT ON (feed_id)
                        feed_id,
                        score
                    FROM preferences
                    WHERE source IN ('interactive', 'alert-feedback') AND user_id = %s
                    ORDER BY feed_id, id DESC
                )
                SELECT
                    {select_fields}
                FROM embeddings e
                JOIN feeds f ON e.feed_id = f.id
                LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = %s
                LEFT JOIN preferences p ON f.id = p.feed_id AND p.source = 'feed-star' AND p.user_id = %s
                LEFT JOIN broadcasts bl ON f.id = bl.feed_id
                LEFT JOIN user_prefs pf ON f.id = pf.feed_id
                LEFT JOIN (
                    SELECT
                        feed_id,
                        SUM(CASE WHEN score = 1 THEN 1 ELSE 0 END) as positive_votes,
                        SUM(CASE WHEN score = 0 THEN 1 ELSE 0 END) as negative_votes
                    FROM preferences
                    WHERE source IN ('interactive', 'alert-feedback')
                    GROUP BY feed_id
                ) vote_counts ON f.id = vote_counts.feed_id
                ORDER BY e.embedding <=> %s::vector
                LIMIT %s
            """,
                (user_id, query_embedding, model_id, user_id, query_embedding, limit),
            )

        results = self.cursor.fetchall()
        return results


class EmbeddingDatabaseWriteBatch:
    def __init__(self, edb):
        self.edb = edb
        self.db = edb.db
        self.cursor = edb.cursor
        self.dtype = edb.dtype
        self.batch_items = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            # Execute all batch items
            for key, value in self.batch_items:
                # Get feed_id from external_id
                self.cursor.execute(
                    "SELECT id FROM feeds WHERE external_id = %s", (key,)
                )
                result = self.cursor.fetchone()
                if result:
                    feed_id = result["id"]
                    embedding_list = value.tolist()

                    self.cursor.execute(
                        """
                        INSERT INTO embeddings (feed_id, embedding)
                        VALUES (%s, %s)
                        ON CONFLICT (feed_id) DO UPDATE SET embedding = %s
                    """,
                        (feed_id, embedding_list, embedding_list),
                    )

            self.db.commit()
        else:
            # Rollback on error
            self.db.rollback()
            self.batch_items.clear()

    def __setitem__(self, key, value):
        if not isinstance(value, np.ndarray):
            value = np.array(value)

        assert value.dtype == self.dtype

        self.batch_items.append((key, value))
