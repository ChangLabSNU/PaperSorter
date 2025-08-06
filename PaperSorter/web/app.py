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

"""Flask application factory for PaperSorter web interface."""

import yaml
import secrets
import psycopg2
import psycopg2.extras
import threading
import time
from datetime import timedelta
from flask import Flask, render_template
from flask_login import LoginManager
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix
from ..log import log
from .auth import User, auth_bp
from .main import main_bp
from .api import feeds_bp, settings_bp, search_bp, user_bp


def create_app(config_path):
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="../templates")

    # Configure for reverse proxy (fixes HTTPS redirect URIs)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Load database configuration
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    db_config = config["db"]
    google_config = config.get("google_oauth", {})

    # Store configurations in app
    app.db_config = db_config
    app.config["CONFIG_PATH"] = config_path

    # Set up Flask secret key
    app.secret_key = google_config.get("flask_secret_key", secrets.token_hex(32))

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
            "SELECT id, username, is_admin, timezone, feedlist_minscore FROM users WHERE id = %s",
            (int(user_id),),
        )
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()

        if user_data:
            return User(
                user_data["id"],
                user_data["username"],
                is_admin=user_data.get("is_admin", False),
                timezone=user_data.get("timezone", "Asia/Seoul"),
                feedlist_minscore=user_data.get("feedlist_minscore"),
            )
        return None

    # Set up OAuth
    oauth = OAuth(app)
    oauth.register(
        name="google",
        client_id=google_config["client_id"],
        client_secret=google_config["secret"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(feeds_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(user_bp)

    # Error handlers
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("403.html"), 403

    return app
