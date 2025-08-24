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

"""Feeds API endpoints."""

import json
import psycopg2
import psycopg2.extras
from flask import Blueprint, request, jsonify, current_app, render_template
from flask_login import login_required, current_user
from ...log import log
from ..utils.database import get_user_model_id

feeds_bp = Blueprint("feeds", __name__)


@feeds_bp.route("/api/feeds")
@login_required
def api_feeds():
    """API endpoint to get feeds with pagination."""
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 20))
    min_score = float(request.args.get("min_score", 0))
    channel_id = request.args.get("channel_id")  # Get channel_id from request
    offset = (page - 1) * limit

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get feeds with all the necessary information
    # Filter preferences by current user
    user_id = current_user.id
    
    # Get user's bookmark and use channel_id from request or fall back to primary channel
    cursor.execute("SELECT bookmark, primary_channel_id FROM users WHERE id = %s", (user_id,))
    user_result = cursor.fetchone()
    bookmark_id = user_result["bookmark"] if user_result else None
    # Use channel_id from request parameter, or fall back to user's primary channel
    channel_id = channel_id if channel_id else (user_result["primary_channel_id"] if user_result else None)
    
    # Get the model_id from the selected channel, or fall back to user's default
    if channel_id:
        cursor.execute("SELECT model_id FROM channels WHERE id = %s", (channel_id,))
        channel_result = cursor.fetchone()
        model_id = channel_result["model_id"] if channel_result and channel_result["model_id"] else get_user_model_id(conn, current_user)
    else:
        model_id = get_user_model_id(conn, current_user)

    # Build WHERE clause based on min_score
    if min_score <= 0:
        where_clause = "1=1"  # Show all feeds
        query_params = (user_id, model_id, channel_id, limit + 1, offset)
    else:
        where_clause = "pp.score >= %s"  # Only show feeds with scores above threshold
        query_params = (user_id, model_id, channel_id, min_score, limit + 1, offset)

    cursor.execute(
        f"""
        WITH latest_prefs AS (
            SELECT DISTINCT ON (feed_id, user_id, source)
                feed_id, user_id, source, score, time
            FROM preferences
            WHERE user_id = %s
            ORDER BY feed_id, user_id, source, time DESC NULLS LAST
        ),
        vote_counts AS (
            SELECT
                feed_id,
                SUM(CASE WHEN score = 1 THEN 1 ELSE 0 END) as positive_votes,
                SUM(CASE WHEN score = 0 THEN 1 ELSE 0 END) as negative_votes
            FROM preferences
            WHERE source IN ('interactive', 'alert-feedback')
            GROUP BY feed_id
        )
        SELECT
            f.id as rowid,
            f.external_id,
            f.title,
            f.author,
            f.origin,
            f.link,
            EXTRACT(EPOCH FROM f.published)::integer as published,
            EXTRACT(EPOCH FROM f.added)::integer as added,
            pp.score as score,
            COALESCE(user_b.feed_id IS NOT NULL AND user_b.broadcasted_time IS NULL, FALSE) as shared,
            COALESCE(user_b.feed_id IS NOT NULL AND user_b.broadcasted_time IS NOT NULL, FALSE) as broadcasted,
            inter_p.score as label,
            COALESCE(vc.positive_votes, 0) as positive_votes,
            COALESCE(vc.negative_votes, 0) as negative_votes
        FROM feeds f
        LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = %s
        LEFT JOIN broadcasts user_b ON f.id = user_b.feed_id AND user_b.channel_id = %s
        LEFT JOIN latest_prefs inter_p ON f.id = inter_p.feed_id AND inter_p.source IN ('interactive', 'alert-feedback')
        LEFT JOIN vote_counts vc ON f.id = vc.feed_id
        WHERE {where_clause}
        ORDER BY f.added DESC
        LIMIT %s OFFSET %s
    """,
        query_params,
    )

    results = cursor.fetchall()
    cursor.close()
    conn.close()

    # Check if there are more results
    has_more = len(results) > limit
    feeds = results[:limit] if has_more else results

    # Include bookmark ID in response
    response_data = {
        "feeds": feeds,
        "has_more": has_more,
        "bookmark_id": bookmark_id
    }

    return jsonify(response_data)


@feeds_bp.route("/api/feeds/<int:feed_id>/content")
@login_required
def api_feed_content(feed_id):
    """API endpoint to get feed content."""
    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute(
        """
        SELECT content, tldr
        FROM feeds
        WHERE id = %s
    """,
        (feed_id,),
    )

    result = cursor.fetchone()
    cursor.close()
    conn.close()

    if result:
        return jsonify(result)
    else:
        return jsonify({"error": "Feed not found"}), 404


@feeds_bp.route("/api/feeds/<int:feed_id>/share", methods=["POST"])
@login_required
def api_share_feed(feed_id):
    """API endpoint to share/unshare a feed (add/remove from broadcast queue)."""
    user_id = current_user.id
    data = request.get_json() or {}
    action = data.get("action", "toggle")  # 'share', 'unshare', or 'toggle'
    
    # Get channel_id from request or fall back to user's primary channel
    channel_id = data.get("channel_id")
    if not channel_id:
        channel_id = current_user.primary_channel_id

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Validate channel
        if not channel_id:
            return jsonify({"success": False, "error": "No channel specified or configured"}), 400
            
        # Check if the channel exists
        cursor.execute(
            "SELECT id FROM channels WHERE id = %s",
            (channel_id,)
        )
        if not cursor.fetchone():
            return jsonify({"success": False, "error": "Channel not found"}), 404
            
        # Check if already shared (exists in broadcasts table for this channel)
        cursor.execute(
            """
            SELECT feed_id FROM broadcasts
            WHERE feed_id = %s AND channel_id = %s
        """,
            (feed_id, channel_id),
        )
        
        is_shared = cursor.fetchone() is not None
        
        if action == "toggle":
            action = "unshare" if is_shared else "share"
        
        if action == "unshare":
            # Remove from broadcasts table
            cursor.execute(
                """
                DELETE FROM broadcasts
                WHERE feed_id = %s AND channel_id = %s
            """,
                (feed_id, channel_id),
            )
        else:  # action == 'share'
            # Add to broadcasts table (will be processed by broadcast task)
            cursor.execute(
                """
                INSERT INTO broadcasts (feed_id, channel_id, broadcasted_time)
                VALUES (%s, %s, NULL)
                ON CONFLICT (feed_id, channel_id) DO NOTHING
            """,
                (feed_id, channel_id),
            )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True, "action": action})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


@feeds_bp.route("/api/feeds/<int:feed_id>/feedback", methods=["POST"])
@login_required
def api_feedback_feed(feed_id):
    """API endpoint to set feedback (like/dislike) for a feed."""
    user_id = current_user.id
    data = request.get_json()
    score = data.get("score")

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        if score is None:
            # Remove feedback from both sources
            cursor.execute(
                """
                DELETE FROM preferences
                WHERE feed_id = %s AND user_id = %s AND source IN ('interactive', 'alert-feedback')
            """,
                (feed_id, user_id),
            )
        else:
            # Check if preference already exists from either source
            cursor.execute(
                """
                SELECT id, source FROM preferences
                WHERE feed_id = %s AND user_id = %s AND source IN ('interactive', 'alert-feedback')
                ORDER BY time DESC
                LIMIT 1
            """,
                (feed_id, user_id),
            )

            existing = cursor.fetchone()

            if existing:
                # Update existing preference (keep the original source)
                cursor.execute(
                    """
                    UPDATE preferences
                    SET score = %s, time = CURRENT_TIMESTAMP
                    WHERE id = %s
                """,
                    (float(score), existing["id"]),
                )
            else:
                # Insert new preference with 'interactive' source
                cursor.execute(
                    """
                    INSERT INTO preferences (feed_id, user_id, time, score, source)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, %s, 'interactive')
                """,
                    (feed_id, user_id, float(score)),
                )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


@feeds_bp.route("/similar/<int:feed_id>")
@login_required
def similar_articles(feed_id):
    """Show articles similar to the given feed."""
    return render_template("similar_articles.html", source_feed_id=feed_id)


@feeds_bp.route("/api/feeds/<int:feed_id>/similar")
@login_required
def api_similar_feeds(feed_id):
    """API endpoint to get similar feeds."""
    try:
        from ...embedding_database import EmbeddingDatabase

        # Load embedding database with config
        config_path = current_app.config["CONFIG_PATH"]
        edb = EmbeddingDatabase(config_path)

        # Get similar articles filtered by current user with default model
        conn = current_app.config["get_db_connection"]()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get model_id from primary channel if it exists
        if current_user.primary_channel_id:
            cursor.execute("SELECT model_id FROM channels WHERE id = %s", (current_user.primary_channel_id,))
            channel_result = cursor.fetchone()
            model_id = channel_result["model_id"] if channel_result and channel_result["model_id"] else get_user_model_id(conn, current_user)
        else:
            model_id = get_user_model_id(conn, current_user)
        
        # Use primary_channel_id for similar articles view
        similar_feeds = edb.find_similar(
            feed_id, limit=30, user_id=current_user.id, model_id=model_id,
            channel_id=current_user.primary_channel_id
        )

        # Convert to format compatible with feeds list
        feeds = []
        for feed in similar_feeds:
            feeds.append(
                {
                    "rowid": feed["feed_id"],
                    "external_id": feed["external_id"],
                    "title": feed["title"],
                    "author": feed["author"],
                    "origin": feed["origin"],
                    "link": feed["link"],
                    "published": feed["published"],
                    "score": feed["predicted_score"],
                    "shared": feed["shared"],
                    "broadcasted": feed["broadcasted"],
                    "label": feed["label"],
                    "similarity": float(feed["similarity"]),
                    "positive_votes": feed["positive_votes"],
                    "negative_votes": feed["negative_votes"],
                }
            )

        # Also get the source article info
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """
            SELECT title, author, origin
            FROM feeds
            WHERE id = %s
        """,
            (feed_id,),
        )
        source_article = cursor.fetchone()
        cursor.close()
        conn.close()

        response_data = {"source_article": source_article, "similar_feeds": feeds}

        return jsonify(response_data)

    except Exception as e:
        log.error(f"Error finding similar articles: {e}")
        return jsonify({"error": str(e)}), 500


@feeds_bp.route("/feedback/<int:feed_id>/interested")
def webhook_feedback_interested(feed_id):
    """Handle webhook feedback for interested (Slack/Discord)."""
    return handle_webhook_feedback(feed_id, 1)


@feeds_bp.route("/feedback/<int:feed_id>/not-interested")
def webhook_feedback_not_interested(feed_id):
    """Handle webhook feedback for not interested (Slack/Discord)."""
    return handle_webhook_feedback(feed_id, 0)


def handle_webhook_feedback(feed_id, score):
    """Common handler for webhook feedback routes (Slack/Discord)."""
    from flask import redirect, url_for

    # Check if user is logged in, if not, redirect to login
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.path))

    user_id = current_user.id

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # First, check if the feed exists
        cursor.execute("SELECT id, title FROM feeds WHERE id = %s", (feed_id,))
        feed = cursor.fetchone()

        if not feed:
            cursor.close()
            conn.close()
            return render_template(
                "feedback_error.html", message="Article not found"
            ), 404

        # Check if any recent preference exists (within 1 month)
        cursor.execute(
            """
            SELECT id, source FROM preferences
            WHERE feed_id = %s AND user_id = %s
            AND time > CURRENT_TIMESTAMP - INTERVAL '1 month'
            ORDER BY time DESC
            LIMIT 1
        """,
            (feed_id, user_id),
        )

        existing = cursor.fetchone()

        if existing:
            # Update the existing recent preference (override regardless of source)
            cursor.execute(
                """
                UPDATE preferences
                SET score = %s, time = CURRENT_TIMESTAMP, source = 'alert-feedback'
                WHERE id = %s
            """,
                (float(score), existing["id"]),
            )
        else:
            # No recent preference exists, insert new one
            cursor.execute(
                """
                INSERT INTO preferences (feed_id, user_id, time, score, source)
                VALUES (%s, %s, CURRENT_TIMESTAMP, %s, 'alert-feedback')
            """,
                (feed_id, user_id, float(score)),
            )

        conn.commit()
        cursor.close()
        conn.close()

        # Render feedback confirmation page with similar articles link
        feedback_type = "interested" if score == 1 else "not interested"
        return render_template(
            "feedback_success.html",
            feed_title=feed["title"],
            feedback_type=feedback_type,
            feed_id=feed_id,
        )

    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        log.error(f"Error recording webhook feedback: {e}")
        return render_template(
            "feedback_error.html", message="Error recording feedback. Please try again."
        ), 500


@feeds_bp.route(
    "/slack-interactivity", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
def slack_interactivity():
    """Handle Slack interactivity requests."""
    payload = json.loads(dict(request.form)["payload"])
    if "user" in payload and "actions" in payload:
        external_id = payload["user"]["id"]
        content = payload["user"]["name"]
        # Split from the right to handle actions like "not_interested_12345"
        value_parts = payload["actions"][0]["value"].rsplit("_", 1)
        if len(value_parts) == 2:
            action, related_feed_id = value_parts
            try:
                related_feed_id = int(related_feed_id)
            except ValueError:
                log.error(
                    f"Invalid feed ID in Slack action: {payload['actions'][0]['value']}"
                )
                return jsonify(
                    {"response_type": "ephemeral", "text": "Invalid feed ID"}
                ), 400
        else:
            log.error(f"Invalid action format: {payload['actions'][0]['value']}")
            return jsonify(
                {"response_type": "ephemeral", "text": "Invalid action format"}
            ), 400

        # Insert event into database
        conn = current_app.config["get_db_connection"]()
        cursor = conn.cursor()
        try:
            # Check if feed exists
            cursor.execute("SELECT id FROM feeds WHERE id = %s", (related_feed_id,))
            if cursor.fetchone():
                cursor.execute(
                    """
                    INSERT INTO events (event_type, external_id, content, feed_id)
                    VALUES (%s, %s, %s, %s)
                """,
                    ("slack:" + action, external_id, content, related_feed_id),
                )
                conn.commit()
            else:
                log.warning(
                    f"Feed ID {related_feed_id} not found, skipping event logging"
                )
        except Exception as e:
            log.error(f"Failed to log event to database: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

    return "", 200
