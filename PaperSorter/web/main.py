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

from datetime import datetime
from decimal import Decimal

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


def _serialize_labeling_item(item):
    """Convert a labeling session row to a JSON-serialisable dict."""
    if not item:
        return None

    predicted_score = item.get("predicted_score")
    if isinstance(predicted_score, Decimal):
        predicted_score = float(predicted_score)

    score = item.get("score")
    if isinstance(score, Decimal):
        score = float(score)

    published = item.get("published")
    if isinstance(published, datetime):
        published_iso = published.isoformat()
        published_ts = published.timestamp()
    else:
        published_iso = None
        published_ts = None

    return {
        "id": item.get("id"),
        "feed_id": item.get("feed_id"),
        "title": item.get("title"),
        "author": item.get("author"),
        "origin": item.get("origin"),
        "content": item.get("content"),
        "link": item.get("link"),
        "score": score,
        "predicted_score": predicted_score,
        "published": published_iso,
        "published_timestamp": published_ts,
    }


def _next_item_payload(conn):
    """Fetch the next item and stats and convert them for JSON responses."""
    item = get_unlabeled_item(conn, current_user)
    stats = get_labeling_stats(conn, current_user)

    if not item:
        return {"status": "complete", "stats": stats}

    return {
        "status": "success",
        "item": _serialize_labeling_item(item),
        "stats": stats,
    }


@main_bp.route("/")
@login_required
def index():
    """Show list of all feeds with their labels."""

    db_manager = current_app.config["db_manager"]

    with db_manager.session() as session:
        cursor = session.cursor(dict_cursor=True)
        cursor.execute(
            """
            SELECT id, name
            FROM channels
            WHERE is_active = TRUE
            ORDER BY id
            """
        )
        channels = cursor.fetchall()
        cursor.close()

        primary_channel_id = current_user.primary_channel_id
        if primary_channel_id is None and channels:
            primary_channel_id = channels[0]["id"]
            update_cursor = session.cursor()
            update_cursor.execute(
                """
                UPDATE users
                SET primary_channel_id = %s
                WHERE id = %s
                """,
                (primary_channel_id, current_user.id),
            )
            update_cursor.close()
            current_user.primary_channel_id = primary_channel_id

        cursor = session.cursor(dict_cursor=True)
        cursor.execute(
            """
            SELECT MAX(COALESCE(published, added)) as last_updated
            FROM feeds
            """
        )
        result = cursor.fetchone()
        cursor.close()

    last_updated = (
        result["last_updated"].strftime("%Y-%m-%d %H:%M")
        if result and result["last_updated"]
        else "Never"
    )

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
    db_manager = current_app.config["db_manager"]

    with db_manager.session() as session:
        cursor = session.cursor()
        cursor.execute(
            """
            SELECT query, assisted_query FROM saved_searches
            WHERE short_name = %s
            LIMIT 1
            """,
            (short_name,),
        )

        result = cursor.fetchone()
        if not result:
            cursor.close()
            return "Link not found", 404

        query = result[0]
        assisted_query = result[1]

        cursor.execute(
            """
            UPDATE saved_searches
            SET last_access = NOW()
            WHERE short_name = %s
            """,
            (short_name,),
        )
        cursor.close()

    if assisted_query:
        return redirect(
            url_for(
                "main.index",
                q=query,
                ai_assist="true",
                saved_search=short_name,
            )
        )
    return redirect(url_for("main.index", q=query))


@main_bp.route("/label", methods=["POST"])
@login_required
def label_item():
    """Handle labeling requests."""
    data = request.get_json()
    session_id = data.get("id")
    label_value = data.get("label")

    if session_id and label_value is not None:
        db_manager = current_app.config["db_manager"]

        try:
            with db_manager.session() as session:
                cursor = session.cursor(dict_cursor=True)
                cursor.execute(
                    "SELECT feed_id, user_id FROM labeling_sessions WHERE id = %s AND user_id = %s",
                    (session_id, current_user.id),
                )
                result = cursor.fetchone()
                cursor.close()

                if not result:
                    return jsonify({"status": "error", "message": "Labeling session not found"}), 404

                feed_id = result["feed_id"]
                user_id = result["user_id"]

                cursor = session.cursor()
                cursor.execute(
                    """
                    SELECT id FROM preferences
                    WHERE feed_id = %s AND user_id = %s AND source = 'interactive'
                    """,
                    (feed_id, user_id),
                )
                existing = cursor.fetchone()

                if existing:
                    cursor.execute(
                        """
                        UPDATE preferences
                        SET score = %s, time = CURRENT_TIMESTAMP
                        WHERE feed_id = %s AND user_id = %s AND source = 'interactive'
                        """,
                        (float(label_value), feed_id, user_id),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO preferences (feed_id, user_id, time, score, source)
                        VALUES (%s, %s, CURRENT_TIMESTAMP, %s, 'interactive')
                        """,
                        (feed_id, user_id, float(label_value)),
                    )

                cursor.execute(
                    """
                    UPDATE labeling_sessions
                    SET score = %s, update_time = CURRENT_TIMESTAMP
                    WHERE id = %s AND user_id = %s
                    """,
                    (float(label_value), session_id, current_user.id),
                )
                cursor.close()

                payload = _next_item_payload(session.connection)
                return jsonify(payload)
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

    return jsonify({"status": "error", "message": "Invalid request"}), 400


@main_bp.route("/label/next", methods=["GET"])
@login_required
def next_label_item():
    """Return the next unlabeled item and updated stats."""
    db_manager = current_app.config["db_manager"]

    with db_manager.session() as session:
        payload = _next_item_payload(session.connection)

    return jsonify(payload)


@main_bp.route("/labeling")
@login_required
def labeling():
    """Labeling interface - hidden page."""
    db_manager = current_app.config["db_manager"]

    with db_manager.session() as session:
        conn = session.connection
        item = get_unlabeled_item(conn, current_user)
        stats = get_labeling_stats(conn, current_user)

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
    db_manager = current_app.config["db_manager"]

    with db_manager.session() as session:
        cursor = session.cursor(dict_cursor=True)
        cursor.execute(
            """
            SELECT id, username, theme, primary_channel_id, timezone, date_format
            FROM users
            WHERE id = %s
            """,
            (current_user.id,),
        )
        user_data = cursor.fetchone()

        cursor.execute(
            """
            SELECT id, name
            FROM channels
            WHERE is_active = TRUE
            ORDER BY id
            """
        )
        channels = cursor.fetchall()
        cursor.close()

    return render_template("user_settings.html", user_data=user_data, channels=channels)


@main_bp.route("/paper/<int:paper_id>")
@login_required
def paper_detail(paper_id):
    """Paper detail page with rich operations."""
    db_manager = current_app.config["db_manager"]

    with db_manager.session() as session:
        cursor = session.cursor(dict_cursor=True)
        cursor.execute(
            """
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
            LEFT JOIN preferences p ON f.id = p.feed_id AND p.user_id = %s
            WHERE f.id = %s
            """,
            (current_user.id, paper_id),
        )
        paper = cursor.fetchone()

        if not paper:
            cursor.close()
            return render_template("error.html", error="Paper not found"), 404

        cursor.execute(
            """
            SELECT
                pp.score,
                COALESCE(m.score_name, m.name) as model_name,
                m.id as model_id
            FROM predicted_preferences pp
            JOIN models m ON pp.model_id = m.id
            WHERE pp.feed_id = %s AND m.is_active = TRUE
            ORDER BY pp.score DESC
            """,
            (paper_id,),
        )
        predicted_scores = cursor.fetchall()

        cursor.execute(
            """
            SELECT id, name
            FROM channels
            WHERE is_active = TRUE
            ORDER BY id
            """
        )
        channels = cursor.fetchall()

        cursor.execute(
            """
            SELECT channel_id
            FROM broadcasts
            WHERE feed_id = %s AND broadcasted_time IS NULL
            """,
            (paper_id,),
        )
        queued_channels = {row["channel_id"] for row in cursor.fetchall()}
        cursor.close()

    return render_template(
        "paper_detail.html",
        paper=paper,
        predicted_scores=predicted_scores,
        similar_papers=None,
        channels=channels,
        queued_channels=queued_channels,
    )


@main_bp.route("/health")
def health_check():
    """Health check endpoint for Docker/monitoring."""
    try:
        db_manager = current_app.config["db_manager"]
        with db_manager.session() as session:
            cursor = session.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
        return jsonify({"status": "healthy", "service": "papersorter"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 503
