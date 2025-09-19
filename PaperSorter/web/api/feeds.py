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
import requests
from flask import Blueprint, request, jsonify, current_app, render_template
from flask_login import login_required, current_user
from ..auth.decorators import admin_required
from ...feed_predictor import refresh_embeddings_and_predictions
from ...log import log
from ..utils.database import get_user_model_id
from ...utils import pubmed_lookup

feeds_bp = Blueprint("feeds", __name__)


def _pubmed_config():
    config = current_app.config
    return {
        "api_key": config.get("PUBMED_API_KEY"),
        "tool": config.get("PUBMED_TOOL"),
        "email": config.get("PUBMED_EMAIL"),
        "max_results": config.get("PUBMED_MAX_RESULTS", pubmed_lookup.DEFAULT_MAX_RESULTS),
    }


def _author_display_list(authors):
    display_names = []
    for author in authors or ():
        name = author.display_name() if hasattr(author, "display_name") else None
        if name:
            display_names.append(name)
    return display_names


def _serialize_pubmed_article(article):
    return {
        "pmid": article.pmid,
        "title": article.title,
        "journal": article.journal,
        "publication_date": article.publication_date,
        "published": article.published.isoformat() if article.published else None,
        "doi": article.doi,
        "url": article.url,
        "abstract": article.abstract,
        "authors": [
            {
                "name": author.name,
                "last_name": author.last_name,
                "fore_name": author.fore_name,
                "initials": author.initials,
                "affiliation": author.affiliation,
                "display": author.display_name(),
            }
            for author in article.authors
        ],
        "authors_display": _author_display_list(article.authors),
    }


@feeds_bp.route("/api/feeds")
@login_required
def api_feeds():
    """API endpoint to get feeds with pagination."""
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 20))
    min_score = float(request.args.get("min_score", 0))
    channel_id = request.args.get("channel_id")  # Get channel_id from request
    offset = (page - 1) * limit

    db_manager = current_app.config["db_manager"]

    with db_manager.session() as session:
        cursor = session.cursor(dict_cursor=True)

        # Get feeds with all the necessary information
        # Filter preferences by current user
        user_id = current_user.id

        cursor.execute(
            "SELECT bookmark, primary_channel_id FROM users WHERE id = %s",
            (user_id,),
        )
        user_result = cursor.fetchone()
        bookmark_id = user_result["bookmark"] if user_result else None
        # Use channel_id from request parameter, or fall back to user's primary channel
        channel_id = channel_id if channel_id else (user_result["primary_channel_id"] if user_result else None)

        if channel_id:
            cursor.execute("SELECT model_id FROM channels WHERE id = %s", (channel_id,))
            channel_result = cursor.fetchone()
            if channel_result and channel_result["model_id"]:
                model_id = channel_result["model_id"]
            else:
                model_id = get_user_model_id(session.connection, current_user)
        else:
            model_id = get_user_model_id(session.connection, current_user)

        if min_score <= 0:
            where_clause = "1=1"
            query_params = (user_id, model_id, channel_id, limit + 1, offset)
        else:
            where_clause = "pp.score >= %s"
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
                COALESCE(f.journal, f.origin) AS origin,
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
    db_manager = current_app.config["db_manager"]

    with db_manager.session() as session:
        cursor = session.cursor(dict_cursor=True)
        cursor.execute(
            """
            SELECT content, tldr
            FROM feeds
            WHERE id = %s
        """,
            (feed_id,),
        )
        result = cursor.fetchone()

    if result:
        return jsonify(result)
    else:
        return jsonify({"error": "Paper not found"}), 404


@feeds_bp.route("/api/feeds/<int:feed_id>/share", methods=["POST"])
@login_required
def api_share_feed(feed_id):
    """API endpoint to share/unshare a paper (add/remove from broadcast queue)."""
    data = request.get_json() or {}
    action = data.get("action", "toggle")  # 'share', 'unshare', or 'toggle'

    # Get channel_id from request or fall back to user's primary channel
    channel_id = data.get("channel_id")
    if not channel_id:
        channel_id = current_user.primary_channel_id

    if not channel_id:
        return jsonify({"success": False, "error": "No channel specified or configured"}), 400

    db_manager = current_app.config["db_manager"]

    try:
        with db_manager.session() as session:
            cursor = session.cursor(dict_cursor=True)

            cursor.execute("SELECT id FROM channels WHERE id = %s", (channel_id,))
            if not cursor.fetchone():
                cursor.close()
                return jsonify({"success": False, "error": "Channel not found"}), 404

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
                cursor.execute(
                    """
                    DELETE FROM broadcasts
                    WHERE feed_id = %s AND channel_id = %s
                """,
                    (feed_id, channel_id),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO broadcasts (feed_id, channel_id, broadcasted_time)
                    VALUES (%s, %s, NULL)
                    ON CONFLICT (feed_id, channel_id) DO NOTHING
                """,
                    (feed_id, channel_id),
                )

            event_type = "web:shared" if action == "share" else "web:unshared"
            cursor.execute(
                """
                INSERT INTO events (event_type, user_id, feed_id, content)
                VALUES (%s, %s, %s, %s)
            """,
                (event_type, current_user.id, feed_id, json.dumps({"channel_id": channel_id})),
            )

            return jsonify({"success": True, "action": action})
    except Exception as exc:
        log.error("Failed to update feed sharing state", exc_info=exc)
        return jsonify({"success": False, "error": str(exc)}), 500


@feeds_bp.route("/api/feeds/feedback", methods=["POST"])
@login_required
def api_feedback():
    """API endpoint to set feedback for a paper."""
    data = request.get_json()
    feed_id = data.get("feed_id")
    feedback = data.get("feedback")

    if not feed_id or not feedback:
        return jsonify({"status": "error", "message": "Missing parameters"}), 400

    user_id = current_user.id
    score = 1 if feedback == "interesting" else 0

    db_manager = current_app.config["db_manager"]

    try:
        with db_manager.session() as session:
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
                    WHERE id = %s
                    """,
                    (float(score), existing[0]),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO preferences (feed_id, user_id, time, score, source)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, %s, 'interactive')
                    """,
                    (feed_id, user_id, float(score)),
                )

            return jsonify({"status": "success"})
    except Exception as exc:
        log.error("Failed to record feedback", exc_info=exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


@feeds_bp.route("/api/feeds/remove-label", methods=["POST"])
@login_required
def api_remove_label():
    """API endpoint to remove a label from a paper."""
    data = request.get_json()
    feed_id = data.get("feed_id")

    if not feed_id:
        return jsonify({"status": "error", "message": "Missing feed_id"}), 400

    user_id = current_user.id

    db_manager = current_app.config["db_manager"]

    try:
        with db_manager.session() as session:
            cursor = session.cursor()
            cursor.execute(
                """
                DELETE FROM preferences
                WHERE feed_id = %s AND user_id = %s AND source IN ('interactive', 'alert-feedback')
                """,
                (feed_id, user_id),
            )
            return jsonify({"status": "success"})
    except Exception as exc:
        log.error("Failed to remove label", exc_info=exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


@feeds_bp.route("/api/feeds/<int:feed_id>/feedback", methods=["POST"])
@login_required
def api_feedback_feed(feed_id):
    """API endpoint to set feedback (like/dislike) for a paper."""
    user_id = current_user.id
    data = request.get_json()
    score = data.get("score")

    db_manager = current_app.config["db_manager"]

    try:
        with db_manager.session() as session:
            cursor = session.cursor(dict_cursor=True)

            if score is None:
                cursor.execute(
                    """
                    DELETE FROM preferences
                    WHERE feed_id = %s AND user_id = %s AND source IN ('interactive', 'alert-feedback')
                    """,
                    (feed_id, user_id),
                )
            else:
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
                    cursor.execute(
                        """
                        UPDATE preferences
                        SET score = %s, time = CURRENT_TIMESTAMP
                        WHERE id = %s
                        """,
                        (float(score), existing["id"]),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO preferences (feed_id, user_id, time, score, source)
                        VALUES (%s, %s, CURRENT_TIMESTAMP, %s, 'interactive')
                        """,
                        (feed_id, user_id, float(score)),
                    )

            if score is None:
                event_type = "web:feedback-removed"
                event_content = "Feedback removed"
            elif float(score) == 1:
                event_type = "web:interested"
                event_content = "From web interface"
            else:
                event_type = "web:not-interested"
                event_content = "From web interface"

            cursor.execute(
                """
                INSERT INTO events (event_type, user_id, feed_id, content)
                VALUES (%s, %s, %s, %s)
                """,
                (event_type, user_id, feed_id, event_content),
            )

            return jsonify({"success": True})
    except Exception as exc:
        log.error("Failed to update feedback", exc_info=exc)
        return jsonify({"success": False, "error": str(exc)}), 500


@feeds_bp.route("/api/feeds/<int:feed_id>/pubmed-match", methods=["GET", "POST"])
@login_required
@admin_required
def api_pubmed_match(feed_id):
    """Find and apply perfect PubMed matches for a paper's metadata."""

    db_manager = current_app.config["db_manager"]

    try:
        with db_manager.session() as session:
            cursor = session.cursor(dict_cursor=True)

            cursor.execute("SELECT id, title FROM feeds WHERE id = %s", (feed_id,))
            paper = cursor.fetchone()
            if not paper:
                cursor.close()
                return jsonify({"error": "Paper not found"}), 404

            metadata_updated = False
            updated_fields = []

            cfg = _pubmed_config()
            max_results = cfg["max_results"]
            api_key = cfg["api_key"]
            tool = cfg["tool"]
            email = cfg["email"]

            if request.method == "GET":
                http_session = requests.Session()
                try:
                    matches = pubmed_lookup.find_perfect_title_matches(
                        paper["title"],
                        max_results=max_results,
                        api_key=api_key,
                        session=http_session,
                        tool=tool,
                        email=email,
                    )
                    matches = pubmed_lookup.attach_article_details(
                        matches,
                        api_key=api_key,
                        session=http_session,
                        tool=tool,
                        email=email,
                    )
                finally:
                    http_session.close()

                cursor.close()
                return jsonify(
                    {"matches": [_serialize_pubmed_article(article) for article in matches]}
                )

            payload = request.get_json() or {}
            pmid = str(payload.get("pmid", "")).strip()
            if not pmid:
                cursor.close()
                return jsonify({"error": "pmid is required"}), 400

            http_session = requests.Session()
            try:
                matches = pubmed_lookup.find_perfect_title_matches(
                    paper["title"],
                    max_results=max_results,
                    api_key=api_key,
                    session=http_session,
                    tool=tool,
                    email=email,
                )
            finally:
                http_session.close()

            if not any(article.pmid == pmid for article in matches):
                cursor.close()
                return jsonify({"error": "No perfect PubMed match for the given title"}), 404

            details = pubmed_lookup.fetch_pubmed_articles(
                [pmid],
                api_key=api_key,
                tool=tool,
                email=email,
            )

            article = details.get(pmid)
            if not article:
                cursor.close()
                return jsonify({"error": "PubMed article details unavailable"}), 502

            updates = []
            params = []
            updated_fields = []

            if article.title:
                updates.append("title = %s")
                params.append(article.title)
                updated_fields.append("title")

            author_string = ", ".join(_author_display_list(article.authors))
            if author_string:
                updates.append("author = %s")
                params.append(author_string)
                updated_fields.append("author")

            if article.journal:
                updates.append("journal = %s")
                params.append(article.journal)
                updated_fields.append("journal")

            if article.abstract:
                updates.append("content = %s")
                params.append(article.abstract)
                updated_fields.append("content")

            if article.published:
                updates.append("published = %s")
                params.append(article.published)
                updated_fields.append("published")

            if not updates:
                cursor.close()
                return jsonify({"success": True, "updated_fields": []})

            params.append(feed_id)
            cursor.execute(
                f"UPDATE feeds SET {', '.join(updates)} WHERE id = %s",
                params,
            )
            metadata_updated = True

            cursor.close()

        if metadata_updated:
            try:
                refresh_embeddings_and_predictions(
                    [feed_id],
                    db_manager,
                    force_rescore=True,
                    refresh_embeddings=True,
                )
            except Exception as exc:  # pragma: no cover - depends on external services
                log.error(
                    "Failed to refresh embeddings for feed %s after metadata update: %s",
                    feed_id,
                    exc,
                )

        return jsonify({"success": True, "pmid": pmid, "updated_fields": updated_fields})

    except pubmed_lookup.PubMedLookupError as exc:
        log.warning("PubMed lookup failed", exc_info=exc)
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:  # pragma: no cover - defensive guard
        log.exception("Unexpected error during PubMed metadata sync")
        return jsonify({"error": "Unexpected error while updating metadata"}), 500


@feeds_bp.route("/similar/<int:feed_id>")
@login_required
def similar_articles(feed_id):
    """Back-compat: redirect to paper details with similar section anchor."""
    from flask import redirect, url_for
    return redirect(url_for("main.paper_detail", paper_id=feed_id) + "#similar")


@feeds_bp.route("/api/feeds/<int:feed_id>/similar")
@login_required
def api_similar_feeds(feed_id):
    """API endpoint to get similar papers."""
    edb = None
    try:
        from ...embedding_database import EmbeddingDatabase

        db_manager = current_app.config["db_manager"]
        edb = EmbeddingDatabase(db_manager=db_manager)
        source_article = None

        with db_manager.session() as session:
            cursor = session.cursor(dict_cursor=True)

            if current_user.primary_channel_id:
                cursor.execute(
                    "SELECT model_id FROM channels WHERE id = %s",
                    (current_user.primary_channel_id,),
                )
                channel_result = cursor.fetchone()
                if channel_result and channel_result["model_id"]:
                    model_id = channel_result["model_id"]
                else:
                    model_id = get_user_model_id(session.connection, current_user)
            else:
                model_id = get_user_model_id(session.connection, current_user)

            similar_feeds = edb.find_similar(
                feed_id,
                limit=30,
                user_id=current_user.id,
                model_id=model_id,
                channel_id=current_user.primary_channel_id,
            )

            feeds = [
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
                for feed in similar_feeds
            ]

            cursor.execute(
                """
                SELECT title, author, COALESCE(journal, origin) AS origin
                FROM feeds
                WHERE id = %s
                """,
                (feed_id,),
            )
            source_article = cursor.fetchone()
            cursor.close()

        response_data = {"source_article": source_article, "similar_feeds": feeds}

        return jsonify(response_data)
    except Exception as e:
        log.error(f"Error finding similar articles: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if edb is not None:
            edb.close()


@feeds_bp.route("/api/feeds/<int:feed_id>/delete", methods=["POST"])
@admin_required
def api_delete_feed(feed_id):
    """Delete a paper (admin only)."""
    db_manager = current_app.config["db_manager"]

    try:
        with db_manager.session() as session:
            cursor = session.cursor()
            cursor.execute(
                "INSERT INTO events (event_type, user_id, feed_id, content) VALUES (%s, %s, %s, %s)",
                ("web:delete", current_user.id, feed_id, "Deleted from paper details page"),
            )
            cursor.execute("DELETE FROM feeds WHERE id = %s", (feed_id,))
            return jsonify({"success": True})
    except Exception as exc:
        log.error("Failed to delete feed", exc_info=exc)
        return jsonify({"success": False, "error": str(exc)}), 500


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

    db_manager = current_app.config["db_manager"]

    try:
        with db_manager.session() as session:
            cursor = session.cursor(dict_cursor=True)

            cursor.execute("SELECT id, title FROM feeds WHERE id = %s", (feed_id,))
            feed = cursor.fetchone()

            if not feed:
                cursor.close()
                return render_template(
                    "feedback_error.html", message="Paper not found"
                ), 404

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
                cursor.execute(
                    """
                    UPDATE preferences
                    SET score = %s, time = CURRENT_TIMESTAMP, source = 'alert-feedback'
                    WHERE id = %s
                    """,
                    (float(score), existing["id"]),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO preferences (feed_id, user_id, time, score, source)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, %s, 'alert-feedback')
                    """,
                    (feed_id, user_id, float(score)),
                )

            event_type = "web:interested" if score == 1 else "web:not-interested"
            cursor.execute(
                """
                INSERT INTO events (event_type, user_id, feed_id, content)
                VALUES (%s, %s, %s, %s)
                """,
                (event_type, user_id, feed_id, "From Slack feedback link"),
            )

            feed_title = feed["title"]
            cursor.close()

        feedback_type = "interested" if score == 1 else "not interested"
        return render_template(
            "feedback_success.html",
            feed_title=feed_title,
            feedback_type=feedback_type,
            feed_id=feed_id,
        )

    except Exception as exc:
        log.error("Error recording webhook feedback", exc_info=exc)
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
        # Split from the right to handle actions like "not_interested_12345" or "details_12345"
        value_parts = payload["actions"][0]["value"].rsplit("_", 1)
        if len(value_parts) == 2:
            action, related_feed_id = value_parts
            try:
                related_feed_id = int(related_feed_id)
            except ValueError:
                log.error(
                    f"Invalid paper ID in Slack action: {payload['actions'][0]['value']}"
                )
                return jsonify(
                    {"response_type": "ephemeral", "text": "Invalid paper ID"}
                ), 400
        else:
            log.error(f"Invalid action format: {payload['actions'][0]['value']}")
            return jsonify(
                {"response_type": "ephemeral", "text": "Invalid action format"}
            ), 400

        db_manager = current_app.config["db_manager"]
        try:
            with db_manager.session() as session:
                cursor = session.cursor()
                cursor.execute("SELECT id FROM feeds WHERE id = %s", (related_feed_id,))
                if cursor.fetchone():
                    cursor.execute(
                        """
                        INSERT INTO events (event_type, external_id, content, feed_id)
                        VALUES (%s, %s, %s, %s)
                        """,
                        ("slack:" + action, external_id, content, related_feed_id),
                    )
                else:
                    log.warning(
                        f"Feed ID {related_feed_id} not found, skipping event logging"
                    )
        except Exception as exc:
            log.error(f"Failed to log event to database: {exc}")

    return "", 200
