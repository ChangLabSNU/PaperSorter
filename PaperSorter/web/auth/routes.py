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

import yaml
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


def check_and_update_admin_status(username, user_id, conn):
    """Check if user should be promoted to admin based on config.

    Note: This function only promotes users to admin, never demotes.
    Users can only be demoted via the web interface or direct database updates.

    Args:
        username: User's email or ORCID identifier
        user_id: User's database ID
        conn: Database connection

    Returns:
        bool: True if user is admin, False otherwise
    """
    try:
        # Get current admin status from database
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "SELECT is_admin FROM users WHERE id = %s",
            (user_id,),
        )
        result = cursor.fetchone()
        current_is_admin = result["is_admin"] if result else False
        cursor.close()
        # If already admin, keep admin status
        if current_is_admin:
            return True

        # Load config to check if user should be promoted
        config_path = current_app.config.get("CONFIG_PATH", "./config.yml")
        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
        except (FileNotFoundError, IOError):
            # If config file doesn't exist or can't be read, return current status
            return current_is_admin

        # Get admin users from config
        admin_users = config.get("admin_users", [])
        if not admin_users:
            # No admin users defined, return current status
            return current_is_admin

        # Normalize username for comparison (lowercase)
        username_lower = username.lower()

        # Check if user should be promoted to admin
        should_be_promoted = any(
            admin.lower() == username_lower for admin in admin_users if admin
        )

        # Only promote (never demote)
        if should_be_promoted and not current_is_admin:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(
                "UPDATE users SET is_admin = %s WHERE id = %s",
                (True, user_id),
            )
            conn.commit()
            cursor.close()
            log.info(f"Promoted {username} to admin based on config.yml")
            return True

        return current_is_admin

    except Exception as e:
        log.error(f"Error checking admin status for {username}: {e}")
        # Return current status from database on error
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "SELECT is_admin FROM users WHERE id = %s",
            (user_id,),
        )
        result = cursor.fetchone()
        is_admin = result["is_admin"] if result else False
        cursor.close()
        return is_admin


@auth_bp.route("/login")
def login():
    """Login page."""
    # If user is already authenticated, redirect to the main page
    if current_user.is_authenticated:
        next_page = request.args.get("next")
        if next_page and next_page.startswith("/"):
            return redirect(next_page)
        return redirect(url_for("main.index"))

    # Check which OAuth providers are properly configured
    oauth_providers = current_app.extensions.get("authlib.integrations.flask_client")

    # Check if Google OAuth is configured and not using example values
    has_google = False
    if oauth_providers and hasattr(oauth_providers, "google"):
        google_client = oauth_providers.google
        if google_client and google_client.client_id:
            # Check if it's not an example value
            if not google_client.client_id.startswith(
                "your-"
            ) and not google_client.client_id.startswith("your_"):
                has_google = True

    # Check if GitHub OAuth is configured and not using example values
    has_github = False
    if oauth_providers and hasattr(oauth_providers, "github"):
        github_client = oauth_providers.github
        if github_client and github_client.client_id:
            # Check if it's not an example value
            if not github_client.client_id.startswith(
                "your-"
            ) and not github_client.client_id.startswith("your_"):
                has_github = True

    # Check if ORCID OAuth is configured and not using example values
    has_orcid = False
    if oauth_providers and hasattr(oauth_providers, "orcid"):
        orcid_client = oauth_providers.orcid
        if orcid_client and orcid_client.client_id:
            # Check if it's not an example value
            if not orcid_client.client_id.startswith(
                "your-"
            ) and not orcid_client.client_id.startswith("your_"):
                has_orcid = True

    # Get the next parameter from the request
    next_page = request.args.get("next")
    return render_template(
        "login.html",
        next=next_page,
        has_google=has_google,
        has_github=has_github,
        has_orcid=has_orcid,
    )


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


@auth_bp.route("/login/github")
def github_login():
    """Initiate GitHub OAuth login."""
    # Store the next parameter in session to preserve it through OAuth flow
    next_page = request.args.get("next")
    if next_page:
        session["next_page"] = next_page

    github = current_app.extensions.get("authlib.integrations.flask_client").github
    redirect_uri = url_for("auth.github_callback", _external=True)
    return github.authorize_redirect(redirect_uri)


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
                "SELECT id, username, is_admin, timezone, feedlist_minscore, primary_channel_id FROM users WHERE username = %s",
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

            # Check and update admin status based on config
            is_admin = check_and_update_admin_status(email, user_data["id"], conn)

            cursor.close()
            conn.close()

            # Log the user in
            user = User(
                user_data["id"],
                user_data["username"],
                email,
                is_admin=is_admin,
                timezone=user_data.get("timezone", "Asia/Seoul"),
                feedlist_minscore=user_data.get("feedlist_minscore"),
                primary_channel_id=user_data.get("primary_channel_id"),
                theme=user_data.get("theme", "light"),
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


@auth_bp.route("/callback/github")
def github_callback():
    """Handle GitHub OAuth callback."""
    try:
        github = current_app.extensions.get("authlib.integrations.flask_client").github
        token = github.authorize_access_token()

        # Get user info from GitHub
        resp = github.get("user", token=token)
        user_info = resp.json()

        # Get primary email if not public
        if not user_info.get("email"):
            emails_resp = github.get("user/emails", token=token)
            emails = emails_resp.json()
            # Find primary email
            for email_data in emails:
                if email_data.get("primary") and email_data.get("verified"):
                    user_info["email"] = email_data["email"]
                    break

        if user_info and user_info.get("email"):
            email = user_info["email"]

            conn = current_app.config["get_db_connection"]()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Check if user exists
            cursor.execute(
                "SELECT id, username, is_admin, timezone, feedlist_minscore, primary_channel_id FROM users WHERE username = %s",
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

            # Check and update admin status based on config
            is_admin = check_and_update_admin_status(email, user_data["id"], conn)

            cursor.close()
            conn.close()

            # Log the user in
            user = User(
                user_data["id"],
                user_data["username"],
                email,
                is_admin=is_admin,
                timezone=user_data.get("timezone", "Asia/Seoul"),
                feedlist_minscore=user_data.get("feedlist_minscore"),
                primary_channel_id=user_data.get("primary_channel_id"),
                theme=user_data.get("theme", "light"),
            )
            login_user(user)

            # Make the session permanent
            session.permanent = True

            # Redirect to the original requested page or home
            next_page = session.pop("next_page", None) or request.args.get("next")
            if next_page and next_page.startswith("/"):
                return redirect(next_page)
            else:
                return redirect(url_for("main.index"))
        else:
            log.error("No email found in GitHub account")
            return redirect(
                url_for("auth.login", error="No email associated with GitHub account")
            )

    except Exception as e:
        log.error(f"GitHub OAuth callback error: {e}")
        return redirect(url_for("auth.login", error="GitHub authentication failed"))


@auth_bp.route("/login/orcid")
def orcid_login():
    """Initiate ORCID OAuth login."""
    # Store the next parameter in session to preserve it through OAuth flow
    next_page = request.args.get("next")
    if next_page:
        session["next_page"] = next_page

    orcid = current_app.extensions.get("authlib.integrations.flask_client").orcid
    redirect_uri = url_for("auth.orcid_callback", _external=True)
    return orcid.authorize_redirect(redirect_uri)


@auth_bp.route("/callback/orcid")
def orcid_callback():
    """Handle ORCID OAuth callback."""
    try:
        orcid = current_app.extensions.get("authlib.integrations.flask_client").orcid
        token = orcid.authorize_access_token()

        # ORCID returns the ORCID iD in the token response
        orcid_id = token.get("orcid")

        if orcid_id:
            # For ORCID, we use the ORCID iD as the username
            # This ensures uniqueness and persistence
            username = f"{orcid_id}@orcid.org"

            conn = current_app.config["get_db_connection"]()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Check if user exists
            cursor.execute(
                "SELECT id, username, is_admin, timezone, feedlist_minscore, primary_channel_id FROM users WHERE username = %s",
                (username,),
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
                    (username, "oauth"),
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

            # Check and update admin status based on config
            is_admin = check_and_update_admin_status(username, user_data["id"], conn)

            cursor.close()
            conn.close()

            # Log the user in
            user = User(
                user_data["id"],
                user_data["username"],
                username,
                is_admin=is_admin,
                timezone=user_data.get("timezone", "Asia/Seoul"),
                feedlist_minscore=user_data.get("feedlist_minscore"),
                primary_channel_id=user_data.get("primary_channel_id"),
                theme=user_data.get("theme", "light"),
            )
            login_user(user)

            # Make the session permanent
            session.permanent = True

            # Redirect to the original requested page or home
            next_page = session.pop("next_page", None) or request.args.get("next")
            if next_page and next_page.startswith("/"):
                return redirect(next_page)
            else:
                return redirect(url_for("main.index"))
        else:
            log.error("No ORCID iD found in response")
            return redirect(url_for("auth.login", error="No ORCID iD found"))

    except Exception as e:
        log.error(f"ORCID OAuth callback error: {e}")
        return redirect(url_for("auth.login", error="ORCID authentication failed"))


@auth_bp.route("/logout")
@login_required
def logout():
    """Logout the user."""
    logout_user()
    return redirect(url_for("auth.login", message="You have been logged out"))
