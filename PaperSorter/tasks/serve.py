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

import os
import yaml
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, abort
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix
from functools import wraps
from ..log import log, initialize_logging
from ..embedding_database import EmbeddingDatabase
import click
import secrets

class User(UserMixin):
    def __init__(self, id, username, email=None, is_admin=False):
        self.id = id
        self.username = username
        self.email = email
        self.is_admin = is_admin

def admin_required(f):
    """Decorator to require admin privileges for a route"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)  # Forbidden
        return f(*args, **kwargs)
    return decorated_function

def create_app(config_path):
    """Create and configure the Flask application"""
    app = Flask(__name__, template_folder='../templates')

    # Configure for reverse proxy (fixes HTTPS redirect URIs)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Load database configuration
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    db_config = config['db']
    google_config = config.get('google_oauth', {})

    # Set up Flask secret key
    app.secret_key = google_config.get('flask_secret_key', secrets.token_hex(32))

    # Set up Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    # Set up OAuth
    oauth = OAuth(app)
    google = oauth.register(
        name='google',
        client_id=google_config['client_id'],
        client_secret=google_config['secret'],
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )

    def get_db_connection():
        return psycopg2.connect(
            host=db_config['host'],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )

    @login_manager.user_loader
    def load_user(user_id):
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT id, username, is_admin FROM users WHERE id = %s", (int(user_id),))
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()

        if user_data:
            return User(user_data['id'], user_data['username'], is_admin=user_data.get('is_admin', False))
        return None

    def get_unlabeled_item():
        """Get a random unlabeled item from the database"""
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get all unlabeled items and pick one randomly, joining with feeds for the URL and predicted score
        cursor.execute("""
            SELECT ls.id, ls.feed_id, f.title, f.author, f.origin, f.content, ls.score, f.link,
                   pp.score as predicted_score
            FROM labeling_sessions ls
            JOIN feeds f ON ls.feed_id = f.id
            LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = 1
            WHERE ls.score IS NULL
            ORDER BY RANDOM()
            LIMIT 1
        """)

        item = cursor.fetchone()
        cursor.close()
        conn.close()

        return item

    def update_label(session_id, label_value):
        """Update the label for a specific item"""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE labeling_sessions SET score = %s, update_time = CURRENT_TIMESTAMP WHERE id = %s",
            (float(label_value), session_id)
        )

        conn.commit()
        cursor.close()
        conn.close()

    def get_labeling_stats():
        """Get statistics about labeling progress"""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM labeling_sessions WHERE score IS NULL")
        unlabeled = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM labeling_sessions WHERE score IS NOT NULL")
        labeled = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM labeling_sessions")
        total = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return {
            'unlabeled': unlabeled,
            'labeled': labeled,
            'total': total,
            'progress': (labeled / total * 100) if total > 0 else 0
        }

    # Authentication routes
    @app.route('/login')
    def login():
        """Login page"""
        return render_template('login.html')

    @app.route('/login/google')
    def google_login():
        """Initiate Google OAuth login"""
        redirect_uri = url_for('google_callback', _external=True)
        return google.authorize_redirect(redirect_uri)

    @app.route('/callback')
    def google_callback():
        """Handle Google OAuth callback"""
        try:
            token = google.authorize_access_token()
            user_info = token.get('userinfo')

            if user_info:
                email = user_info.get('email')
                name = user_info.get('name', email.split('@')[0])

                conn = get_db_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

                # Check if user exists
                cursor.execute("SELECT id, username, is_admin FROM users WHERE username = %s", (email,))
                user_data = cursor.fetchone()

                if not user_data:
                    # Create new user (non-admin by default)
                    cursor.execute("""
                        INSERT INTO users (username, password, created, is_admin)
                        VALUES (%s, %s, CURRENT_TIMESTAMP, false)
                        RETURNING id, username, is_admin
                    """, (email, 'oauth'))
                    user_data = cursor.fetchone()
                    conn.commit()

                # Update last login
                cursor.execute("""
                    UPDATE users SET lastlogin = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (user_data['id'],))
                conn.commit()

                cursor.close()
                conn.close()

                # Log the user in
                user = User(user_data['id'], user_data['username'], email, is_admin=user_data.get('is_admin', False))
                login_user(user)

                # Redirect to the original requested page or home
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('index'))

        except Exception as e:
            log.error(f"OAuth callback error: {e}")
            return redirect(url_for('login', error='Authentication failed'))

    @app.route('/logout')
    @login_required
    def logout():
        """Logout the user"""
        logout_user()
        return redirect(url_for('login', message='You have been logged out'))

    @app.route('/')
    @login_required
    def index():
        """Show list of all feeds with their labels"""
        return render_template('feeds_list.html')

    @app.route('/label', methods=['POST'])
    @login_required
    def label_item():
        """Handle labeling requests"""
        data = request.get_json()
        session_id = data.get('id')
        label_value = data.get('label')

        if session_id and label_value is not None:
            update_label(session_id, label_value)

            # Also update preferences table
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Get feed_id and user_id from labeling_sessions
            cursor.execute("SELECT feed_id, user_id FROM labeling_sessions WHERE id = %s", (session_id,))
            result = cursor.fetchone()

            if result:
                feed_id = result['feed_id']
                user_id = result['user_id']

                # First check if a preference already exists
                cursor.execute("""
                    SELECT id FROM preferences
                    WHERE feed_id = %s AND user_id = %s AND source = 'interactive'
                """, (feed_id, user_id))

                existing = cursor.fetchone()

                if existing:
                    # Update existing preference
                    cursor.execute("""
                        UPDATE preferences
                        SET score = %s, time = CURRENT_TIMESTAMP
                        WHERE feed_id = %s AND user_id = %s AND source = 'interactive'
                    """, (float(label_value), feed_id, user_id))
                else:
                    # Insert new preference
                    cursor.execute("""
                        INSERT INTO preferences (feed_id, user_id, time, score, source)
                        VALUES (%s, %s, CURRENT_TIMESTAMP, %s, 'interactive')
                    """, (feed_id, user_id, float(label_value)))

                conn.commit()

            cursor.close()
            conn.close()

            return jsonify({'status': 'success'})

        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    @app.route('/labeling')
    @login_required
    def labeling():
        """Labeling interface - hidden page"""
        item = get_unlabeled_item()
        stats = get_labeling_stats()

        if not item:
            return render_template('complete.html', stats=stats)

        return render_template('labeling.html', item=item, stats=stats)

    @app.route('/api/feeds')
    @login_required
    def api_feeds():
        """API endpoint to get feeds with pagination"""
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        min_score = float(request.args.get('min_score', 0))
        offset = (page - 1) * limit

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get feeds with all the necessary information
        cursor.execute("""
            SELECT
                f.id as rowid,
                f.external_id,
                f.title,
                f.author,
                f.origin,
                f.link,
                EXTRACT(EPOCH FROM f.published)::integer as published,
                pp.score as score,
                CASE WHEN p.score > 0 THEN true ELSE false END as starred,
                CASE WHEN bl.broadcasted_time IS NOT NULL THEN true ELSE false END as broadcasted,
                pf.score as label
            FROM feeds f
            LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = 1
            LEFT JOIN preferences p ON f.id = p.feed_id AND p.source = 'feed-star'
            LEFT JOIN broadcast_logs bl ON f.id = bl.feed_id
            LEFT JOIN preferences pf ON f.id = pf.feed_id AND pf.source = 'interactive'
            WHERE pp.score >= %s OR pp.score IS NULL
            ORDER BY f.published DESC
            LIMIT %s OFFSET %s
        """, (min_score, limit + 1, offset))

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        # Check if there are more results
        has_more = len(results) > limit
        feeds = results[:limit] if has_more else results

        return jsonify({
            'feeds': feeds,
            'has_more': has_more
        })

    @app.route('/api/feeds/<int:feed_id>/content')
    @login_required
    def api_feed_content(feed_id):
        """API endpoint to get feed content"""
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT content, tldr
            FROM feeds
            WHERE id = %s
        """, (feed_id,))

        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if result:
            return jsonify(result)
        else:
            return jsonify({'error': 'Feed not found'}), 404

    @app.route('/api/feeds/<int:feed_id>/star', methods=['POST'])
    @login_required
    def api_star_feed(feed_id):
        """API endpoint to star/unstar a feed"""
        user_id = 1  # Default user

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            # Check if preference already exists
            cursor.execute("""
                SELECT id, score FROM preferences
                WHERE feed_id = %s AND user_id = %s AND source = 'feed-star'
            """, (feed_id, user_id))

            existing = cursor.fetchone()

            if existing:
                # Update existing preference to starred
                cursor.execute("""
                    UPDATE preferences
                    SET score = 1.0, time = CURRENT_TIMESTAMP
                    WHERE feed_id = %s AND user_id = %s AND source = 'feed-star'
                """, (feed_id, user_id))
            else:
                # Insert new preference
                cursor.execute("""
                    INSERT INTO preferences (feed_id, user_id, time, score, source)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, 1.0, 'feed-star')
                """, (feed_id, user_id))

            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({'success': True})
        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/feeds/<int:feed_id>/feedback', methods=['POST'])
    @login_required
    def api_feedback_feed(feed_id):
        """API endpoint to set feedback (like/dislike) for a feed"""
        user_id = 1  # Default user
        data = request.get_json()
        score = data.get('score')

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            if score is None:
                # Remove feedback
                cursor.execute("""
                    DELETE FROM preferences
                    WHERE feed_id = %s AND user_id = %s AND source = 'interactive'
                """, (feed_id, user_id))
            else:
                # Check if preference already exists
                cursor.execute("""
                    SELECT id FROM preferences
                    WHERE feed_id = %s AND user_id = %s AND source = 'interactive'
                """, (feed_id, user_id))

                existing = cursor.fetchone()

                if existing:
                    # Update existing preference
                    cursor.execute("""
                        UPDATE preferences
                        SET score = %s, time = CURRENT_TIMESTAMP
                        WHERE feed_id = %s AND user_id = %s AND source = 'interactive'
                    """, (float(score), feed_id, user_id))
                else:
                    # Insert new preference
                    cursor.execute("""
                        INSERT INTO preferences (feed_id, user_id, time, score, source)
                        VALUES (%s, %s, CURRENT_TIMESTAMP, %s, 'interactive')
                    """, (feed_id, user_id, float(score)))

            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({'success': True})
        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    # Settings routes
    @app.route('/settings')
    @admin_required
    def settings():
        """Settings main page"""
        return render_template('settings.html')

    @app.route('/settings/channels')
    @admin_required
    def settings_channels():
        """Channels settings page"""
        return render_template('settings_channels.html')

    @app.route('/settings/users')
    @admin_required
    def settings_users():
        """Users settings page"""
        return render_template('settings_users.html')

    @app.route('/settings/models')
    @admin_required
    def settings_models():
        """Models settings page"""
        return render_template('settings_models.html')

    # Channels API endpoints
    @app.route('/api/settings/channels')
    @admin_required
    def api_get_channels():
        """Get all channels"""
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT id, name, endpoint_url, score_threshold, model_id
            FROM channels
            ORDER BY id
        """)

        channels = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify({'channels': channels})

    @app.route('/api/settings/channels', methods=['POST'])
    @admin_required
    def api_create_channel():
        """Create a new channel"""
        data = request.get_json()

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO channels (name, endpoint_url, score_threshold, model_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (data['name'], data['endpoint_url'], 
                  data.get('score_threshold', 0.7), data.get('model_id', 1)))

            channel_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({'success': True, 'id': channel_id})
        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/settings/channels/<int:channel_id>', methods=['PUT'])
    @admin_required
    def api_update_channel(channel_id):
        """Update a channel"""
        data = request.get_json()

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE channels
                SET name = %s, endpoint_url = %s, score_threshold = %s, model_id = %s
                WHERE id = %s
            """, (data['name'], data['endpoint_url'], 
                  data.get('score_threshold', 0.7), data.get('model_id', 1), 
                  channel_id))

            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({'success': True})
        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/settings/channels/<int:channel_id>', methods=['DELETE'])
    @admin_required
    def api_delete_channel(channel_id):
        """Delete a channel"""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM channels WHERE id = %s", (channel_id,))
            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({'success': True})
        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    # Users API endpoints
    @app.route('/api/settings/users')
    @admin_required
    def api_get_users():
        """Get all users"""
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT id, username, created, lastlogin
            FROM users
            ORDER BY id
        """)

        users = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify({'users': users})

    @app.route('/api/settings/users', methods=['POST'])
    @admin_required
    def api_create_user():
        """Create a new user"""
        data = request.get_json()

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO users (username, password, created)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            """, (data['username'], data.get('password', 'default')))

            user_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({'success': True, 'id': user_id})
        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/settings/users/<int:user_id>', methods=['PUT'])
    @admin_required
    def api_update_user(user_id):
        """Update a user"""
        data = request.get_json()

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE users
                SET username = %s
                WHERE id = %s
            """, (data['username'], user_id))

            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({'success': True})
        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/settings/users/<int:user_id>', methods=['DELETE'])
    @admin_required
    def api_delete_user(user_id):
        """Delete a user"""
        if user_id == 1:
            return jsonify({'success': False, 'error': 'Cannot delete default user'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({'success': True})
        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    # Similar articles routes
    @app.route('/similar/<int:feed_id>')
    @login_required
    def similar_articles(feed_id):
        """Show articles similar to the given feed"""
        return render_template('similar_articles.html', source_feed_id=feed_id)
    
    @app.route('/api/feeds/<int:feed_id>/similar')
    @login_required
    def api_similar_feeds(feed_id):
        """API endpoint to get similar feeds"""
        try:
            # Load embedding database with config
            edb = EmbeddingDatabase(config_path)
            
            # Get similar articles
            similar_feeds = edb.find_similar(feed_id, limit=30)
            
            # Convert to format compatible with feeds list
            feeds = []
            for feed in similar_feeds:
                feeds.append({
                    'rowid': feed['feed_id'],
                    'external_id': feed['external_id'],
                    'title': feed['title'],
                    'author': feed['author'],
                    'origin': feed['origin'],
                    'link': feed['link'],
                    'published': feed['published'],
                    'score': feed['predicted_score'],
                    'starred': feed['starred'],
                    'broadcasted': feed['broadcasted'],
                    'label': feed['label'],
                    'similarity': float(feed['similarity'])
                })
            
            # Also get the source article info
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute("""
                SELECT title, author, origin
                FROM feeds
                WHERE id = %s
            """, (feed_id,))
            source_article = cursor.fetchone()
            cursor.close()
            conn.close()
            
            return jsonify({
                'source_article': source_article,
                'similar_feeds': feeds
            })
            
        except Exception as e:
            log.error(f"Error finding similar articles: {e}")
            return jsonify({'error': str(e)}), 500

    # Models API endpoints
    @app.route('/api/settings/models')
    @admin_required
    def api_get_models():
        """Get all models"""
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT id, name, user_id, created
            FROM models
            ORDER BY id
        """)

        models = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify({'models': models})

    @app.route('/api/settings/models', methods=['POST'])
    @admin_required
    def api_create_model():
        """Create a new model"""
        data = request.get_json()

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO models (name, user_id, created)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            """, (data['name'], data.get('user_id', 1)))

            model_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({'success': True, 'id': model_id})
        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/settings/models/<int:model_id>', methods=['PUT'])
    @admin_required
    def api_update_model(model_id):
        """Update a model"""
        data = request.get_json()

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE models
                SET name = %s
                WHERE id = %s
            """, (data['name'], model_id))

            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({'success': True})
        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/settings/models/<int:model_id>', methods=['DELETE'])
    @admin_required
    def api_delete_model(model_id):
        """Delete a model"""
        if model_id == 1:
            return jsonify({'success': False, 'error': 'Cannot delete default model'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM models WHERE id = %s", (model_id,))
            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({'success': True})
        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    # Error handlers
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('403.html'), 403

    return app

@click.option('--config', default='qbio/config.yml', help='Database configuration file.')
@click.option('--host', default='0.0.0.0', help='Host to bind to.')
@click.option('--port', default=5001, help='Port to bind to.')
@click.option('--debug', is_flag=True, help='Enable debug mode.')
@click.option('--log-file', default=None, help='Log file.')
@click.option('-q', '--quiet', is_flag=True, help='Suppress log output.')
def main(config, host, port, debug, log_file, quiet):
    """Serve web interface for article labeling and other tasks"""
    initialize_logging(task='serve', logfile=log_file, quiet=quiet)

    log.info(f'Starting web server on {host}:{port}')

    app = create_app(config)

    # Run the Flask app
    app.run(host=host, port=port, debug=debug)