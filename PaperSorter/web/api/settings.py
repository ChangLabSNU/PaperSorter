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

"""Settings API endpoints."""

import psycopg2
import psycopg2.extras
from flask import Blueprint, request, jsonify, render_template, current_app
from ..auth.decorators import admin_required

settings_bp = Blueprint("settings", __name__)


# Settings pages
@settings_bp.route("/settings")
@admin_required
def settings():
    """Settings main page."""
    return render_template("settings.html")


@settings_bp.route("/settings/channels")
@admin_required
def settings_channels():
    """Channels settings page."""
    return render_template("settings_channels.html")


@settings_bp.route("/settings/users")
@admin_required
def settings_users():
    """Users settings page."""
    return render_template("settings_users.html")


@settings_bp.route("/settings/models")
@admin_required
def settings_models():
    """Models settings page."""
    return render_template("settings_models.html")


@settings_bp.route("/settings/feed-sources")
@admin_required
def settings_feed_sources():
    """Feed sources management page."""
    return render_template("settings_feed_sources.html")


# Channels API endpoints
@settings_bp.route("/api/settings/channels")
@admin_required
def api_get_channels():
    """Get all channels."""
    from urllib.parse import urlparse
    from ...utils.broadcast_hours import hours_to_checkbox_array

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT id, name, endpoint_url, score_threshold, model_id, is_active,
               broadcast_limit, broadcast_hours
        FROM channels
        ORDER BY id
    """)

    channels = cursor.fetchall()

    # Add webhook type detection and broadcast hours array
    for channel in channels:
        # Convert broadcast_hours to checkbox array for UI
        channel["broadcast_hours_array"] = hours_to_checkbox_array(
            channel.get("broadcast_hours")
        )

        if channel["endpoint_url"]:
            try:
                # Check for email endpoints first
                if channel["endpoint_url"].startswith("mailto:"):
                    channel["webhook_type"] = "Email"
                else:
                    hostname = urlparse(channel["endpoint_url"]).hostname or ""
                    hostname_lower = hostname.lower()
                    if hostname_lower.endswith(
                        "discord.com"
                    ) or hostname_lower.endswith("discordapp.com"):
                        channel["webhook_type"] = "Discord"
                    elif hostname_lower.endswith("slack.com"):
                        channel["webhook_type"] = "Slack"
                    else:
                        channel["webhook_type"] = "Unknown"
            except Exception:
                channel["webhook_type"] = "Invalid"
        else:
            channel["webhook_type"] = "Not configured"

    cursor.close()
    conn.close()

    return jsonify({"channels": channels})


def validate_endpoint_url(url):
    """Validate if the endpoint URL is a supported type.

    Returns:
        tuple: (is_valid, error_message, is_warning)
    """
    import re
    from urllib.parse import urlparse

    if not url:
        return False, "Endpoint URL is required", False

    # Check for email format
    if url.startswith("mailto:"):
        email = url[7:]
        email_regex = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
        if not re.match(email_regex, email):
            return False, "Invalid email address format", False
        return True, None, False

    # Check for webhook URLs
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid URL format", False

        hostname_lower = hostname.lower()
        if "slack.com" in hostname_lower:
            return True, None, False
        elif "discord.com" in hostname_lower or "discordapp.com" in hostname_lower:
            return True, None, False
        else:
            # Warning: unsupported but allow to proceed
            return (
                True,
                "Warning: Unsupported webhook URL. This endpoint may not work correctly.",
                True,
            )
    except Exception:
        return (
            False,
            "Invalid URL format. Use https://... for webhooks or mailto:email@example.com for email.",
            False,
        )


@settings_bp.route("/api/settings/channels", methods=["POST"])
@admin_required
def api_create_channel():
    """Create a new channel."""
    from ...utils.broadcast_hours import checkbox_array_to_hours

    data = request.get_json()

    # Validate endpoint URL
    endpoint_url = data.get("endpoint_url", "")
    is_valid, error_msg, is_warning = validate_endpoint_url(endpoint_url)

    if not is_valid:
        return jsonify({"success": False, "error": error_msg}), 400

    if is_warning:
        # Log warning but allow to proceed
        current_app.logger.warning(
            f"Creating channel with unsupported URL: {endpoint_url}"
        )

    # Convert broadcast hours array to string format
    broadcast_hours = None
    if "broadcast_hours_array" in data:
        broadcast_hours = checkbox_array_to_hours(data["broadcast_hours_array"])

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO channels (name, endpoint_url, score_threshold, model_id, is_active,
                                broadcast_limit, broadcast_hours)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """,
            (
                data["name"],
                data["endpoint_url"],
                data.get("score_threshold", 0.7),
                data.get("model_id", 1),
                data.get("is_active", True),
                data.get("broadcast_limit", 20),
                broadcast_hours,
            ),
        )

        channel_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True, "id": channel_id})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


@settings_bp.route("/api/settings/channels/<int:channel_id>", methods=["PUT"])
@admin_required
def api_update_channel(channel_id):
    """Update a channel."""
    from ...utils.broadcast_hours import checkbox_array_to_hours

    data = request.get_json()

    # Validate endpoint URL
    endpoint_url = data.get("endpoint_url", "")
    is_valid, error_msg, is_warning = validate_endpoint_url(endpoint_url)

    if not is_valid:
        return jsonify({"success": False, "error": error_msg}), 400

    if is_warning:
        # Log warning but allow to proceed
        current_app.logger.warning(
            f"Updating channel {channel_id} with unsupported URL: {endpoint_url}"
        )

    # Convert broadcast hours array to string format
    broadcast_hours = None
    if "broadcast_hours_array" in data:
        broadcast_hours = checkbox_array_to_hours(data["broadcast_hours_array"])

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE channels
            SET name = %s, endpoint_url = %s, score_threshold = %s, model_id = %s, is_active = %s,
                broadcast_limit = %s, broadcast_hours = %s
            WHERE id = %s
        """,
            (
                data["name"],
                data["endpoint_url"],
                data.get("score_threshold", 0.7),
                data.get("model_id", 1),
                data.get("is_active", True),
                data.get("broadcast_limit", 20),
                broadcast_hours,
                channel_id,
            ),
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


@settings_bp.route("/api/settings/channels/<int:channel_id>", methods=["DELETE"])
@admin_required
def api_delete_channel(channel_id):
    """Delete a channel."""
    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM channels WHERE id = %s", (channel_id,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


@settings_bp.route("/api/settings/channels/<int:channel_id>/test", methods=["POST"])
@admin_required
def api_test_channel(channel_id):
    """Send a test notification to a channel."""
    from ...notification import create_notification_provider, NotificationError

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Get channel details
        cursor.execute(
            """
            SELECT c.id, c.name, c.endpoint_url, m.name as model_name
            FROM channels c
            LEFT JOIN models m ON c.model_id = m.id
            WHERE c.id = %s
        """,
            (channel_id,),
        )

        channel = cursor.fetchone()
        cursor.close()
        conn.close()

        if not channel:
            return jsonify({"success": False, "error": "Channel not found"}), 404

        if not channel["endpoint_url"]:
            return jsonify(
                {"success": False, "error": "Channel has no webhook URL configured"}
            ), 400

        # Create test article
        test_item = {
            "id": "test",
            "title": "Test Notification from PaperSorter",
            "content": "This is a test notification to verify that your webhook is properly configured. "
            "If you can see this message, your webhook is working correctly!",
            "author": "PaperSorter System",
            "origin": "Test",
            "link": "https://github.com/hyeshik/papersorter",
            "score": 0.75,
        }

        message_options = {
            "model_name": channel["model_name"] or "Default",
            "channel_name": channel["name"],
        }

        # Get base URL from config
        import yaml

        config_path = current_app.config.get("CONFIG_PATH", "./config.yml")
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        base_url = config.get("web", {}).get("base_url", None)

        # Create provider and send notification
        provider = create_notification_provider(channel["endpoint_url"], config_path)

        # Use batch interface - send as a list with one item
        results = provider.send_notifications([test_item], message_options, base_url)

        # Check if the test was successful
        if not results or not results[0][1]:
            raise NotificationError("Test notification failed")

        # Detect webhook type for response
        from urllib.parse import urlparse

        if channel["endpoint_url"].startswith("mailto:"):
            webhook_type = "Email"
        else:
            hostname = urlparse(channel["endpoint_url"]).hostname or ""
            hostname_lower = hostname.lower()
            if hostname_lower.endswith("discord.com") or hostname_lower.endswith(
                "discordapp.com"
            ):
                webhook_type = "Discord"
            elif hostname_lower.endswith("slack.com"):
                webhook_type = "Slack"
            else:
                webhook_type = "Unknown"

        return jsonify(
            {
                "success": True,
                "message": f"Test notification sent successfully to {webhook_type} webhook",
            }
        )

    except NotificationError as e:
        return jsonify(
            {"success": False, "error": f"Notification error: {str(e)}"}
        ), 500
    except Exception as e:
        if "cursor" in locals():
            cursor.close()
        if "conn" in locals():
            conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


# Users API endpoints
@settings_bp.route("/api/settings/users")
@admin_required
def api_get_users():
    """Get all users."""
    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT id, username, created, lastlogin, timezone, is_admin
        FROM users
        ORDER BY id
    """)

    users = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify({"users": users})


@settings_bp.route("/api/settings/users", methods=["POST"])
@admin_required
def api_create_user():
    """Create a new user."""
    data = request.get_json()

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO users (username, password, created, timezone, is_admin)
            VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s)
            RETURNING id
        """,
            (
                data["username"],
                data.get("password", "default"),
                data.get("timezone", "Asia/Seoul"),
                data.get("is_admin", False),
            ),
        )

        user_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True, "id": user_id})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


@settings_bp.route("/api/settings/users/<int:user_id>", methods=["PUT"])
@admin_required
def api_update_user(user_id):
    """Update a user."""
    data = request.get_json()

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        # Update query parts
        update_parts = ["username = %s"]
        update_values = [data["username"]]

        if "timezone" in data:
            update_parts.append("timezone = %s")
            update_values.append(data["timezone"])

        if "is_admin" in data:
            update_parts.append("is_admin = %s")
            update_values.append(data["is_admin"])

        # Add user_id at the end
        update_values.append(user_id)

        cursor.execute(
            f"""
            UPDATE users
            SET {", ".join(update_parts)}
            WHERE id = %s
        """,
            update_values,
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


@settings_bp.route("/api/settings/users/<int:user_id>", methods=["DELETE"])
@admin_required
def api_delete_user(user_id):
    """Delete a user."""
    if user_id == 1:
        return jsonify({"success": False, "error": "Cannot delete default user"}), 400

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


# Models API endpoints
@settings_bp.route("/api/settings/models")
@admin_required
def api_get_models():
    """Get all models."""
    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT id, name, notes, created, is_active
        FROM models
        ORDER BY id
    """)

    models = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify({"models": models})


@settings_bp.route("/api/settings/models", methods=["POST"])
@admin_required
def api_create_model():
    """Create a new model."""
    data = request.get_json()

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO models (name, notes, created, is_active)
            VALUES (%s, %s, CURRENT_TIMESTAMP, %s)
            RETURNING id
        """,
            (data["name"], data.get("notes", ""), data.get("is_active", True)),
        )

        model_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True, "id": model_id})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


@settings_bp.route("/api/settings/models/<int:model_id>", methods=["PUT"])
@admin_required
def api_update_model(model_id):
    """Update a model."""
    data = request.get_json()

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        # Update query parts
        update_parts = ["name = %s"]
        update_values = [data["name"]]

        if "notes" in data:
            update_parts.append("notes = %s")
            update_values.append(data["notes"])

        if "is_active" in data:
            update_parts.append("is_active = %s")
            update_values.append(data["is_active"])

        # Add model_id at the end
        update_values.append(model_id)

        cursor.execute(
            f"""
            UPDATE models
            SET {", ".join(update_parts)}
            WHERE id = %s
        """,
            update_values,
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


@settings_bp.route("/api/settings/models/<int:model_id>", methods=["DELETE"])
@admin_required
def api_delete_model(model_id):
    """Delete a model."""
    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Check if model is being used by any channels
        cursor.execute(
            "SELECT COUNT(*) as count FROM channels WHERE model_id = %s",
            (model_id,)
        )
        channel_count = cursor.fetchone()["count"]
        
        if channel_count > 0:
            cursor.close()
            conn.close()
            return jsonify({
                "success": False, 
                "error": f"Cannot delete model: used by {channel_count} channel(s)"
            }), 400

        cursor.execute("DELETE FROM models WHERE id = %s", (model_id,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


# Feed Sources API endpoints


@settings_bp.route("/api/settings/feed-sources")
@admin_required
def api_get_feed_sources():
    """Get all feed sources."""
    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Optimized query: count feeds per origin first, then join with feed_sources
        cursor.execute("""
            WITH feed_counts AS (
                SELECT origin, COUNT(*) as count
                FROM feeds
                GROUP BY origin
            )
            SELECT 
                fs.id, 
                fs.name, 
                fs.source_type, 
                fs.url, 
                fs.added, 
                fs.last_updated, 
                fs.last_checked,
                COALESCE(fc.count, 0) as feed_count
            FROM feed_sources fs
            LEFT JOIN feed_counts fc ON fs.name = fc.origin
            ORDER BY fs.id
        """)

        feed_sources = cursor.fetchall()
        cursor.close()
        conn.close()

        # Convert datetime to ISO format for JSON
        for source in feed_sources:
            if source["added"]:
                source["added"] = source["added"].isoformat()
            if source["last_updated"]:
                source["last_updated"] = source["last_updated"].isoformat()
            if source["last_checked"]:
                source["last_checked"] = source["last_checked"].isoformat()

        return jsonify({"feed_sources": feed_sources})
    except Exception as e:
        cursor.close()
        conn.close()
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/api/settings/feed-sources", methods=["POST"])
@admin_required
def api_create_feed_source():
    """Create a new feed source."""
    data = request.get_json()

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO feed_sources (name, source_type, url)
            VALUES (%s, %s, %s)
            RETURNING id
        """,
            (data["name"], data.get("source_type", "rss"), data.get("url")),
        )

        source_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True, "id": source_id})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


@settings_bp.route("/api/settings/feed-sources/<int:source_id>", methods=["PUT"])
@admin_required
def api_update_feed_source(source_id):
    """Update a feed source."""
    data = request.get_json()

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE feed_sources
            SET name = %s, source_type = %s, url = %s
            WHERE id = %s
        """,
            (data["name"], data.get("source_type", "rss"), data.get("url"), source_id),
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


@settings_bp.route("/api/settings/feed-sources/<int:source_id>", methods=["DELETE"])
@admin_required
def api_delete_feed_source(source_id):
    """Delete a feed source."""
    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM feed_sources WHERE id = %s", (source_id,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


# New API routes for broadcast queue and events (without /settings prefix)
@settings_bp.route("/api/broadcast-queue")
@admin_required
def api_broadcast_queue():
    """Get broadcast queue items across all channels (unbroadcasted only)."""
    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cursor.execute("""
            SELECT
                b.feed_id,
                b.channel_id,
                b.broadcasted_time,
                f.title,
                f.author,
                f.origin,
                f.published,
                f.link,
                c.name as channel_name,
                c.endpoint_url as channel_endpoint,
                pp.score
            FROM broadcasts b
            JOIN feeds f ON b.feed_id = f.id
            JOIN channels c ON b.channel_id = c.id
            LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = c.model_id
            WHERE b.broadcasted_time IS NULL
            ORDER BY c.name ASC, c.id ASC, f.id ASC
        """)

        queue_items = cursor.fetchall()
        cursor.close()
        conn.close()

        # Convert datetime to ISO format for JSON
        for item in queue_items:
            if item["published"]:
                item["published"] = item["published"].isoformat()

        return jsonify({"queue_items": queue_items})
    except Exception as e:
        cursor.close()
        conn.close()
        return jsonify({"error": str(e)}), 500


@settings_bp.route(
    "/api/broadcast-queue/<int:feed_id>/<int:channel_id>", methods=["DELETE"]
)
@admin_required
def api_broadcast_queue_remove(feed_id, channel_id):
    """Remove item from broadcast queue."""
    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM broadcasts
            WHERE feed_id = %s AND channel_id = %s AND broadcasted_time IS NULL
        """,
            (feed_id, channel_id),
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


@settings_bp.route("/api/events")
@admin_required
def api_events():
    """Get event logs with pagination."""
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    offset = (page - 1) * per_page

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Get total count
        cursor.execute("SELECT COUNT(*) as total FROM events")
        total = cursor.fetchone()["total"]

        # Get events with feed and user information
        cursor.execute(
            """
            SELECT e.*, f.title as feed_title, u.username
            FROM events e
            LEFT JOIN feeds f ON e.feed_id = f.id
            LEFT JOIN users u ON e.user_id = u.id
            ORDER BY e.occurred DESC
            LIMIT %s OFFSET %s
        """,
            (per_page, offset),
        )
        events = cursor.fetchall()

        cursor.close()
        conn.close()

        # Convert datetime to ISO format for JSON
        for event in events:
            if event["occurred"]:
                event["occurred"] = event["occurred"].isoformat()

        return jsonify(
            {
                "events": events,
                "total": total,
                "page": page,
                "per_page": per_page,
                "has_more": offset + per_page < total,
            }
        )
    except Exception as e:
        cursor.close()
        conn.close()
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/api/broadcast-queue/channel/<int:channel_id>", methods=["DELETE"])
@admin_required
def api_empty_channel_queue(channel_id):
    """Empty all items from a channel's broadcast queue."""
    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        # Delete all unbroadcasted items for this channel
        cursor.execute(
            """
            DELETE FROM broadcasts
            WHERE channel_id = %s AND broadcasted_time IS NULL
        """,
            (channel_id,),
        )

        affected_rows = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True, "deleted_count": affected_rows})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500
