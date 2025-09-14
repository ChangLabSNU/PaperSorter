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
from flask_login import login_required, current_user
from .utils.database import get_unlabeled_item, get_labeling_stats

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def index():
    """Show list of all feeds with their labels."""

    # Get list of active channels for primary channel selector
    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT id, name
        FROM channels
        WHERE is_active = TRUE
        ORDER BY id
    """)
    channels = cursor.fetchall()

    # If user's primary_channel_id is NULL and channels exist, auto-set to the first one
    primary_channel_id = current_user.primary_channel_id
    if primary_channel_id is None and channels:
        primary_channel_id = channels[0]["id"]
        # Update the user's primary_channel_id
        cursor.execute(
            """
            UPDATE users
            SET primary_channel_id = %s
            WHERE id = %s
        """,
            (primary_channel_id, current_user.id),
        )
        conn.commit()

        # Update the current user object
        current_user.primary_channel_id = primary_channel_id

    # Get last update time
    cursor.execute("""
        SELECT MAX(COALESCE(published, added)) as last_updated
        FROM feeds
    """)
    result = cursor.fetchone()
    last_updated = result['last_updated'].strftime('%Y-%m-%d %H:%M') if result and result['last_updated'] else 'Never'

    cursor.close()
    conn.close()

    # Get user's minimum score preference
    current_min_score = getattr(current_user, 'feedlist_minscore', 0.0)

    return render_template(
        "feeds_list.html",
        channels=channels,
        primary_channel_id=primary_channel_id,
        current_min_score=current_min_score,
        last_updated=last_updated
    )


@main_bp.route("/link/<short_name>")
@login_required
def shortened_link(short_name):
    """Redirect from shortened link to search query."""
    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        # Look up the query and assisted_query for this short_name
        cursor.execute(
            """
            SELECT query, assisted_query FROM saved_searches
            WHERE short_name = %s
            LIMIT 1
        """,
            (short_name,),
        )

        result = cursor.fetchone()
        if result:
            query = result[0]
            assisted_query = result[1]

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
            # Include ai_assist parameter if there was an assisted query
            if assisted_query:
                return redirect(url_for("main.index", q=query, ai_assist="true", saved_search=short_name))
            else:
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

        # Also update preferences table
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get feed_id and user_id from labeling_sessions
        # IMPORTANT: Verify the session belongs to the current user
        cursor.execute(
            "SELECT feed_id, user_id FROM labeling_sessions WHERE id = %s AND user_id = %s",
            (session_id, current_user.id),
        )
        result = cursor.fetchone()

        if result:
            feed_id = result["feed_id"]
            user_id = result["user_id"]  # This will be current_user.id

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

            # Update the labeling_sessions table with score and update_time
            # Also verify ownership for the UPDATE to prevent any race conditions
            cursor.execute(
                """
                UPDATE labeling_sessions
                SET score = %s, update_time = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s
            """,
                (float(label_value), session_id, current_user.id),
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
    item = get_unlabeled_item(conn, current_user)
    stats = get_labeling_stats(conn, current_user)
    conn.close()

    if not item:
        return render_template("complete.html", stats=stats, show_back_to_feeds=True)

    return render_template("labeling.html", item=item, stats=stats, show_back_to_feeds=True)


@main_bp.route("/broadcast-queue")
@login_required
def broadcast_queue():
    """Broadcast queue management page."""
    # Check if user is admin
    if not current_user.is_admin:
        return render_template("error.html", error="Admin access required"), 403
    return render_template("broadcast_queue.html")


@main_bp.route("/events")
@login_required
def events():
    """Event logs viewer page."""
    # Check if user is admin
    if not current_user.is_admin:
        return render_template("error.html", error="Admin access required"), 403
    return render_template("events.html")


@main_bp.route("/pdf-search")
@login_required
def pdf_search():
    """PDF search page for selecting text from PDFs to search for similar papers."""
    return render_template("pdf_search.html")


@main_bp.route("/user-settings")
@login_required
def user_settings():
    """Personal settings page for users to manage their preferences."""
    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get user's current settings
    cursor.execute("""
        SELECT id, username, theme, primary_channel_id, timezone, date_format
        FROM users
        WHERE id = %s
    """, (current_user.id,))
    user_data = cursor.fetchone()

    # Get available channels for primary channel selection
    cursor.execute("""
        SELECT id, name
        FROM channels
        WHERE is_active = TRUE
        ORDER BY id
    """)
    channels = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("user_settings.html", user_data=user_data, channels=channels)


@main_bp.route("/paper/<int:paper_id>")
@login_required
def paper_detail(paper_id):
    """Paper detail page with rich operations."""
    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # Get paper details without predicted scores (we'll get all scores separately)
        cursor.execute("""
            SELECT 
                f.id,
                f.external_id,
                f.title,
                f.content,
                f.author,
                f.origin,
                f.journal,
                f.link,
                f.published,
                f.added,
                f.tldr,
                p.score as user_score,
                p.source as label_source
            FROM feeds f
            LEFT JOIN preferences p ON f.id = p.feed_id 
                AND p.user_id = %s
            WHERE f.id = %s
        """, (current_user.id, paper_id))
        
        paper = cursor.fetchone()
        
        if not paper:
            return render_template("error.html", error="Paper not found"), 404
        
        # Get all predicted scores from active models
        cursor.execute("""
            SELECT 
                pp.score,
                COALESCE(m.score_name, m.name) as model_name,
                m.id as model_id
            FROM predicted_preferences pp
            JOIN models m ON pp.model_id = m.id
            WHERE pp.feed_id = %s AND m.is_active = TRUE
            ORDER BY pp.score DESC
        """, (paper_id,))
        
        predicted_scores = cursor.fetchall()
        
        # Get available channels for broadcast operations
        cursor.execute("""
            SELECT id, name
            FROM channels
            WHERE is_active = TRUE
            ORDER BY id
        """)
        channels = cursor.fetchall()
        
        # Check if paper is in any broadcast queues
        cursor.execute("""
            SELECT channel_id
            FROM broadcasts
            WHERE feed_id = %s AND broadcasted_time IS NULL
        """, (paper_id,))
        
        queued_channels = [row['channel_id'] for row in cursor.fetchall()]
        
        return render_template(
            "paper_detail.html",
            paper=paper,
            predicted_scores=predicted_scores,
            similar_papers=None,  # Will be loaded asynchronously
            channels=channels,
            queued_channels=queued_channels
        )
        
    finally:
        cursor.close()
        conn.close()


@main_bp.route("/health")
def health_check():
    """Health check endpoint for Docker/monitoring."""
    try:
        # Check database connection
        conn = current_app.config["get_db_connection"]()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return jsonify({"status": "healthy", "service": "papersorter"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 503
