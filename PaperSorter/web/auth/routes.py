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

"""Authentication routes."""

import psycopg2
import psycopg2.extras
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    current_app,
)
from flask_login import login_user, logout_user, login_required, current_user
from ...log import log
from .models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login")
def login():
    """Login page."""
    # If user is already authenticated, redirect to the main page
    if current_user.is_authenticated:
        next_page = request.args.get("next")
        if next_page and next_page.startswith("/"):
            return redirect(next_page)
        return redirect(url_for("main.index"))

    # Get the next parameter from the request
    next_page = request.args.get("next")
    return render_template("login.html", next=next_page)


@auth_bp.route("/login/google")
def google_login():
    """Initiate Google OAuth login."""
    # Store the next parameter in session to preserve it through OAuth flow
    next_page = request.args.get("next")
    if next_page:
        session["next_page"] = next_page

    google = current_app.extensions.get("authlib.integrations.flask_client").google
    redirect_uri = url_for("auth.google_callback", _external=True)
    return google.authorize_redirect(redirect_uri)


@auth_bp.route("/callback")
def google_callback():
    """Handle Google OAuth callback."""
    try:
        google = current_app.extensions.get("authlib.integrations.flask_client").google
        token = google.authorize_access_token()
        user_info = token.get("userinfo")

        if user_info:
            email = user_info.get("email")

            conn = current_app.config["get_db_connection"]()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Check if user exists
            cursor.execute(
                "SELECT id, username, is_admin, timezone, feedlist_minscore FROM users WHERE username = %s",
                (email,),
            )
            user_data = cursor.fetchone()

            if not user_data:
                # Create new user (non-admin by default)
                cursor.execute(
                    """
                    INSERT INTO users (username, password, created, is_admin, timezone)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, false, 'Asia/Seoul')
                    RETURNING id, username, is_admin, timezone
                """,
                    (email, "oauth"),
                )
                user_data = cursor.fetchone()
                conn.commit()

            # Update last login
            cursor.execute(
                """
                UPDATE users SET lastlogin = CURRENT_TIMESTAMP
                WHERE id = %s
            """,
                (user_data["id"],),
            )
            conn.commit()

            cursor.close()
            conn.close()

            # Log the user in
            user = User(
                user_data["id"],
                user_data["username"],
                email,
                is_admin=user_data.get("is_admin", False),
                timezone=user_data.get("timezone", "Asia/Seoul"),
                feedlist_minscore=user_data.get("feedlist_minscore"),
            )
            login_user(user)

            # Make the session permanent
            session.permanent = True

            # Redirect to the original requested page or home
            # First check session, then request args
            next_page = session.pop("next_page", None) or request.args.get("next")
            if next_page and next_page.startswith("/"):
                return redirect(next_page)
            else:
                return redirect(url_for("main.index"))

    except Exception as e:
        log.error(f"OAuth callback error: {e}")
        return redirect(url_for("auth.login", error="Authentication failed"))


@auth_bp.route("/logout")
@login_required
def logout():
    """Logout the user."""
    logout_user()
    return redirect(url_for("auth.login", message="You have been logged out"))
