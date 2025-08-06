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

"""Database utility functions."""

import random
import string
import psycopg2
import psycopg2.extras


def get_default_model_id(conn):
    """Get the most recent active model ID."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM models
        WHERE is_active = TRUE
        ORDER BY id DESC
        LIMIT 1
    """)
    result = cursor.fetchone()
    cursor.close()
    return result[0] if result else 1  # Fallback to 1 if no active models


def get_unlabeled_item(conn):
    """Get a random unlabeled item from the database."""
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get all unlabeled items and pick one randomly, joining with feeds for the URL and predicted score
    default_model_id = get_default_model_id(conn)
    cursor.execute(
        """
        SELECT ls.id, ls.feed_id, f.title, f.author, f.origin, f.content, ls.score, f.link,
               pp.score as predicted_score
        FROM labeling_sessions ls
        JOIN feeds f ON ls.feed_id = f.id
        LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = %s
        WHERE ls.score IS NULL
        ORDER BY RANDOM()
        LIMIT 1
    """,
        (default_model_id,),
    )

    item = cursor.fetchone()
    cursor.close()

    return item


def update_label(conn, session_id, label_value):
    """Update the label for a specific item."""
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE labeling_sessions SET score = %s, update_time = CURRENT_TIMESTAMP WHERE id = %s",
        (float(label_value), session_id),
    )

    conn.commit()
    cursor.close()


def get_labeling_stats(conn):
    """Get statistics about labeling progress."""
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM labeling_sessions WHERE score IS NULL")
    unlabeled = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM labeling_sessions WHERE score IS NOT NULL")
    labeled = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM labeling_sessions")
    total = cursor.fetchone()[0]

    cursor.close()

    return {
        "unlabeled": unlabeled,
        "labeled": labeled,
        "total": total,
        "progress": (labeled / total * 100) if total > 0 else 0,
    }


def generate_short_name(length=8):
    """Generate a random short name with uppercase, lowercase letters and numbers."""
    characters = string.ascii_letters + string.digits
    return "".join(random.choice(characters) for _ in range(length))


def save_search_query(conn, query, user_id=None):
    """Save a search query to the saved_searches table.

    If the query already exists, return the existing short_name.
    Otherwise, create a new entry with a unique short_name.

    Args:
        conn: Database connection
        query: The search query to save
        user_id: Optional user ID who performed the search

    Returns:
        The short_name for this search query
    """
    cursor = conn.cursor()

    try:
        # First check if this query already exists
        cursor.execute(
            """
            SELECT short_name FROM saved_searches
            WHERE query = %s
            LIMIT 1
        """,
            (query,),
        )

        existing = cursor.fetchone()
        if existing:
            # Query already exists, update last_access and return the existing short_name
            short_name = existing[0]
            cursor.execute(
                """
                UPDATE saved_searches
                SET last_access = NOW()
                WHERE short_name = %s
            """,
                (short_name,),
            )
            conn.commit()
            return short_name

        # Generate a unique short_name
        max_attempts = 100
        for _ in range(max_attempts):
            short_name = generate_short_name()

            # Check if this short_name already exists
            cursor.execute(
                """
                SELECT 1 FROM saved_searches
                WHERE short_name = %s
                LIMIT 1
            """,
                (short_name,),
            )

            if not cursor.fetchone():
                # This short_name is unique, insert the new record
                cursor.execute(
                    """
                    INSERT INTO saved_searches (short_name, query, user_id)
                    VALUES (%s, %s, %s)
                    RETURNING short_name
                """,
                    (short_name, query, user_id),
                )

                conn.commit()
                return cursor.fetchone()[0]

        # If we couldn't generate a unique short_name after max_attempts
        raise Exception("Failed to generate unique short_name")

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
