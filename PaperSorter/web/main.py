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

"""Main routes for the web interface."""

import psycopg2
import psycopg2.extras
from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    current_app,
    redirect,
    url_for,
)
from flask_login import login_required
from .utils.database import get_unlabeled_item, update_label, get_labeling_stats

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def index():
    """Show list of all feeds with their labels."""
    return render_template("feeds_list.html")


@main_bp.route("/link/<short_name>")
@login_required
def shortened_link(short_name):
    """Redirect from shortened link to search query."""
    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        # Look up the query for this short_name
        cursor.execute(
            """
            SELECT query FROM saved_searches
            WHERE short_name = %s
            LIMIT 1
        """,
            (short_name,),
        )

        result = cursor.fetchone()
        if result:
            query = result[0]

            # Update last_access time
            cursor.execute(
                """
                UPDATE saved_searches
                SET last_access = NOW()
                WHERE short_name = %s
            """,
                (short_name,),
            )
            conn.commit()

            # Redirect to the main page with the search query
            return redirect(url_for("main.index", q=query))
        else:
            # Short name not found
            return "Link not found", 404

    finally:
        cursor.close()
        conn.close()


@main_bp.route("/label", methods=["POST"])
@login_required
def label_item():
    """Handle labeling requests."""
    data = request.get_json()
    session_id = data.get("id")
    label_value = data.get("label")

    if session_id and label_value is not None:
        conn = current_app.config["get_db_connection"]()
        update_label(conn, session_id, label_value)

        # Also update preferences table
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get feed_id and user_id from labeling_sessions
        cursor.execute(
            "SELECT feed_id, user_id FROM labeling_sessions WHERE id = %s",
            (session_id,),
        )
        result = cursor.fetchone()

        if result:
            feed_id = result["feed_id"]
            user_id = result["user_id"]

            # First check if a preference already exists
            cursor.execute(
                """
                SELECT id FROM preferences
                WHERE feed_id = %s AND user_id = %s AND source = 'interactive'
            """,
                (feed_id, user_id),
            )

            existing = cursor.fetchone()

            if existing:
                # Update existing preference
                cursor.execute(
                    """
                    UPDATE preferences
                    SET score = %s, time = CURRENT_TIMESTAMP
                    WHERE feed_id = %s AND user_id = %s AND source = 'interactive'
                """,
                    (float(label_value), feed_id, user_id),
                )
            else:
                # Insert new preference
                cursor.execute(
                    """
                    INSERT INTO preferences (feed_id, user_id, time, score, source)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, %s, 'interactive')
                """,
                    (feed_id, user_id, float(label_value)),
                )

            conn.commit()

        cursor.close()
        conn.close()

        return jsonify({"status": "success"})

    return jsonify({"status": "error", "message": "Invalid request"}), 400


@main_bp.route("/labeling")
@login_required
def labeling():
    """Labeling interface - hidden page."""
    conn = current_app.config["get_db_connection"]()
    item = get_unlabeled_item(conn)
    stats = get_labeling_stats(conn)
    conn.close()

    if not item:
        return render_template("complete.html", stats=stats)

    return render_template("labeling.html", item=item, stats=stats)
