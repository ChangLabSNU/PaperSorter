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

"""User API endpoints."""

import uuid
import time
import threading
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from ...log import log
from ..jobs.poster import process_poster_job

user_bp = Blueprint("user", __name__)


@user_bp.route("/api/user/preferences", methods=["PUT"])
@login_required
def api_update_user_preferences():
    """Update current user's preferences."""
    data = request.get_json()

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        # Handle feedlist_minscore update
        if "feedlist_minscore" in data:
            # Convert decimal to integer for storage (e.g., 0.25 -> 25)
            min_score_decimal = float(data["feedlist_minscore"])
            min_score_int = int(min_score_decimal * 100)

            cursor.execute(
                """
                UPDATE users
                SET feedlist_minscore = %s
                WHERE id = %s
            """,
                (min_score_int, current_user.id),
            )

            # Update the current user object
            current_user.feedlist_minscore_int = min_score_int
            current_user.feedlist_minscore = min_score_decimal

        # Handle primary_channel_id update
        if "primary_channel_id" in data:
            channel_id = data["primary_channel_id"]
            # Allow None to unset primary channel
            if channel_id == "":
                channel_id = None
            elif channel_id is not None:
                channel_id = int(channel_id)

            cursor.execute(
                """
                UPDATE users
                SET primary_channel_id = %s
                WHERE id = %s
            """,
                (channel_id, current_user.id),
            )

            # Update the current user object
            current_user.primary_channel_id = channel_id

        # Handle theme update
        if "theme" in data:
            theme = data["theme"]
            if theme not in ["light", "dark", "auto"]:
                theme = "light"
            
            cursor.execute(
                """
                UPDATE users
                SET theme = %s
                WHERE id = %s
                """,
                (theme, current_user.id),
            )
            
            # Update the current user object
            current_user.theme = theme

        # Handle timezone update
        if "timezone" in data:
            timezone = data["timezone"]
            
            cursor.execute(
                """
                UPDATE users
                SET timezone = %s
                WHERE id = %s
                """,
                (timezone, current_user.id),
            )
            
            # Update the current user object
            current_user.timezone = timezone

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


@user_bp.route("/api/user/bookmark", methods=["PUT"])
@login_required
def api_update_bookmark():
    """Update user's reading position bookmark."""
    data = request.get_json()
    feed_id = data.get("feed_id")

    if not feed_id:
        return jsonify({"success": False, "error": "feed_id is required"}), 400

    conn = current_app.config["get_db_connection"]()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE users
            SET bookmark = %s
            WHERE id = %s
        """,
            (feed_id, current_user.id),
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


@user_bp.route("/api/generate-poster", methods=["POST"])
@login_required
def api_generate_poster():
    """Queue a poster generation job and return job ID."""
    try:
        data = request.get_json()
        feed_ids = data.get("feed_ids", [])

        if not feed_ids:
            log.error("No feed IDs provided in request")
            return jsonify({"error": "No feed IDs provided"}), 400

        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Store job in queue
        app = current_app._get_current_object()
        with app.poster_jobs_lock:
            app.poster_jobs[job_id] = {
                "status": "pending",
                "created_at": time.time(),
                "user_id": current_user.id,
                "feed_ids": feed_ids,
                "result": None,
                "error": None,
            }

        # Start background thread to process the job
        thread = threading.Thread(
            target=process_poster_job,
            args=(app, job_id, feed_ids, app.config["CONFIG_PATH"]),
            daemon=True,
        )
        thread.start()

        # Return job ID immediately
        return jsonify({"success": True, "job_id": job_id})

    except Exception as e:
        log.error(f"Error creating poster job: {e}")
        return jsonify({"error": str(e)}), 500


@user_bp.route("/api/poster-status/<job_id>", methods=["GET"])
@login_required
def api_poster_status(job_id):
    """Check the status of a poster generation job."""
    with current_app.poster_jobs_lock:
        job = current_app.poster_jobs.get(job_id)

        if not job:
            return jsonify({"error": "Job not found"}), 404

        # Check if job belongs to current user
        if job["user_id"] != current_user.id and not current_user.is_admin:
            return jsonify({"error": "Unauthorized"}), 403

        # Return job status
        response = {
            "job_id": job_id,
            "status": job["status"],
            "created_at": job["created_at"],
        }

        if job["status"] == "completed":
            response["poster_html"] = job["result"]
            # Clear the job after returning it
            del current_app.poster_jobs[job_id]
        elif job["status"] == "error":
            response["error"] = job["error"]
            # Clear the job after returning the error
            del current_app.poster_jobs[job_id]

        return jsonify(response)
