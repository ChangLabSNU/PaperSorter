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

"""Flask application factory for PaperSorter web interface."""

import yaml
import secrets
import psycopg2
import psycopg2.extras
import threading
import time
from datetime import timedelta
from flask import Flask, render_template
from flask_login import LoginManager, login_user
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix
from ..log import log
from .auth import User, auth_bp
from .main import main_bp
from .api import feeds_bp, settings_bp, search_bp, user_bp


def create_app(config_path, skip_authentication=None):
    """Create and configure the Flask application."""
    app = Flask(__name__,
                template_folder="../templates",
                static_folder="../static",
                static_url_path="/static")

    # Configure for reverse proxy (fixes HTTPS redirect URIs)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Load database configuration
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    db_config = config["db"]

    # Get OAuth config with backward compatibility for google_oauth only
    oauth_config = config.get("oauth", {})
    google_config = oauth_config.get("google", config.get("google_oauth", {}))
    github_config = oauth_config.get("github", {})
    orcid_config = oauth_config.get("orcid", {})

    # Get web config
    web_config = config.get("web", {})

    # Get site name with default fallback
    site_name = web_config.get("site_name", "PaperSorter")

    # Get default timezone and date format
    default_timezone = web_config.get("default_timezone", "UTC")
    default_date_format = web_config.get("default_date_format", "MMM D, YYYY")

    # Store configurations in app
    app.db_config = db_config
    app.config["CONFIG_PATH"] = config_path
    app.config["SKIP_AUTHENTICATION"] = skip_authentication
    app.config["SITE_NAME"] = site_name
    app.config["DEFAULT_TIMEZONE"] = default_timezone
    app.config["DEFAULT_DATE_FORMAT"] = default_date_format

    # Set up Flask secret key
    # Check web.flask_secret_key first, then fall back to google_oauth for backward compatibility
    app.secret_key = (
        web_config.get("flask_secret_key")
        or config.get("google_oauth", {}).get("flask_secret_key")
        or secrets.token_hex(32)
    )

    # Set session lifetime to 30 days
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

    # Initialize job queue for poster generation
    app.poster_jobs = {}
    app.poster_jobs_lock = threading.Lock()

    # Database connection function
    def get_db_connection():
        return psycopg2.connect(
            host=db_config["host"],
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
        )

    app.config["get_db_connection"] = get_db_connection

    # Handle skip-authentication mode
    if skip_authentication:
        # Create or update the admin user in the database
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Check if user exists
        cursor.execute(
            "SELECT id, username, is_admin FROM users WHERE username = %s",
            (skip_authentication,)
        )
        user_data = cursor.fetchone()

        if user_data:
            # User exists - upgrade to admin if needed
            if not user_data["is_admin"]:
                cursor.execute(
                    "UPDATE users SET is_admin = TRUE WHERE username = %s",
                    (skip_authentication,)
                )
                conn.commit()
                log.info(f"Upgraded user '{skip_authentication}' to admin status")
            else:
                log.info(f"Using existing admin user '{skip_authentication}'")
            skip_auth_user_id = user_data["id"]
        else:
            # Create new admin user with 'oauth' as password placeholder
            cursor.execute(
                """INSERT INTO users (username, password, is_admin, timezone, date_format, feedlist_minscore)
                   VALUES (%s, 'oauth', TRUE, %s, %s, 25) RETURNING id""",
                (skip_authentication, default_timezone, default_date_format)
            )
            skip_auth_user_id = cursor.fetchone()["id"]
            conn.commit()
            log.info(f"Created new admin user '{skip_authentication}'")

        cursor.close()
        conn.close()

        # Store the user ID for auto-login
        app.config["SKIP_AUTH_USER_ID"] = skip_auth_user_id

    # Cleanup old jobs every 5 minutes
    def cleanup_old_jobs():
        while True:
            time.sleep(300)  # 5 minutes
            with app.poster_jobs_lock:
                current_time = time.time()
                # Remove jobs older than 10 minutes
                jobs_to_remove = [
                    job_id
                    for job_id, job_data in app.poster_jobs.items()
                    if current_time - job_data.get("created_at", 0) > 600
                ]
                for job_id in jobs_to_remove:
                    log.info(f"Cleaning up old poster job: {job_id}")
                    del app.poster_jobs[job_id]

    cleanup_thread = threading.Thread(target=cleanup_old_jobs, daemon=True)
    cleanup_thread.start()

    # Set up Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """SELECT id, username, is_admin, timezone, date_format, feedlist_minscore, primary_channel_id,
                      theme, lastlogin,
                      EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - COALESCE(lastlogin, TIMESTAMP '1970-01-01'))) as seconds_since_login
               FROM users WHERE id = %s""",
            (int(user_id),),
        )
        user_data = cursor.fetchone()

        if user_data:
            # Update last login timestamp only if it's stale (>10 minutes old)
            seconds_since_login = user_data.get("seconds_since_login", float("inf"))
            if seconds_since_login > 600:  # 600 seconds = 10 minutes
                cursor.execute(
                    "UPDATE users SET lastlogin = CURRENT_TIMESTAMP WHERE id = %s",
                    (int(user_id),),
                )
                conn.commit()

        cursor.close()
        conn.close()

        if user_data:
            return User(
                user_data["id"],
                user_data["username"],
                is_admin=user_data.get("is_admin", False),
                timezone=user_data.get("timezone", "UTC"),
                date_format=user_data.get("date_format", "MMM D, YYYY"),
                feedlist_minscore=user_data.get("feedlist_minscore"),
                primary_channel_id=user_data.get("primary_channel_id"),
                theme=user_data.get("theme", "light"),
            )
        return None

    # Set up OAuth
    oauth = OAuth(app)

    # Register Google OAuth if configured
    if google_config.get("client_id") and google_config.get("secret"):
        oauth.register(
            name="google",
            client_id=google_config["client_id"],
            client_secret=google_config["secret"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

    # Register GitHub OAuth if configured
    if github_config.get("client_id") and github_config.get("secret"):
        oauth.register(
            name="github",
            client_id=github_config["client_id"],
            client_secret=github_config["secret"],
            access_token_url="https://github.com/login/oauth/access_token",
            access_token_params=None,
            authorize_url="https://github.com/login/oauth/authorize",
            authorize_params=None,
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "user:email"},
        )

    # Register ORCID OAuth if configured
    if orcid_config.get("client_id") and orcid_config.get("secret"):
        # Determine if we're using sandbox or production
        is_sandbox = orcid_config.get("sandbox", False)
        orcid_base = "https://sandbox.orcid.org" if is_sandbox else "https://orcid.org"

        oauth.register(
            name="orcid",
            client_id=orcid_config["client_id"],
            client_secret=orcid_config["secret"],
            access_token_url=f"{orcid_base}/oauth/token",
            access_token_params=None,
            authorize_url=f"{orcid_base}/oauth/authorize",
            authorize_params=None,
            api_base_url=f"{orcid_base}/v3.0/",
            client_kwargs={"scope": "/authenticate"},
        )

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(feeds_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(user_bp)

    # Auto-login middleware for skip-authentication mode
    if skip_authentication:
        @app.before_request
        def auto_login():
            from flask_login import current_user
            if not current_user.is_authenticated:
                # Load the skip-auth user
                user_id = app.config.get("SKIP_AUTH_USER_ID")
                if user_id:
                    user = load_user(str(user_id))
                    if user:
                        login_user(user, remember=True)
                        # Set session as permanent to match normal login behavior
                        from flask import session
                        session.permanent = True

    # Context processor to inject site_name into all templates
    @app.context_processor
    def inject_site_name():
        return {"site_name": app.config.get("SITE_NAME", "PaperSorter")}

    # Error handlers
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("403.html"), 403

    return app
