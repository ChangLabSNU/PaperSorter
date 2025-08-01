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
    cursor.execute("""
        SELECT ls.id, ls.feed_id, f.title, f.author, f.origin, f.content, ls.score, f.link,
               pp.score as predicted_score
        FROM labeling_sessions ls
        JOIN feeds f ON ls.feed_id = f.id
        LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = %s
        WHERE ls.score IS NULL
        ORDER BY RANDOM()
        LIMIT 1
    """, (default_model_id,))

    item = cursor.fetchone()
    cursor.close()

    return item


def update_label(conn, session_id, label_value):
    """Update the label for a specific item."""
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE labeling_sessions SET score = %s, update_time = CURRENT_TIMESTAMP WHERE id = %s",
        (float(label_value), session_id)
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
        'unlabeled': unlabeled,
        'labeled': labeled,
        'total': total,
        'progress': (labeled / total * 100) if total > 0 else 0
    }