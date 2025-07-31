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
import json
import psycopg2
import psycopg2.extras
import markdown2
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, abort, make_response
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix
from functools import wraps
from ..log import log, initialize_logging
from ..embedding_database import EmbeddingDatabase
from ..feed_predictor import FeedPredictor
import click
import secrets
import requests
import uuid
from openai import OpenAI
from datetime import datetime, timedelta
from ..providers.theoldreader import Item
from ..feed_database import FeedDatabase
import threading
import time
from collections import defaultdict

class User(UserMixin):
    def __init__(self, id, username, email=None, is_admin=False, timezone='Asia/Seoul', feedlist_minscore=None):
        self.id = id
        self.username = username
        self.email = email
        self.is_admin = is_admin
        self.timezone = timezone
        # Store the integer value from DB, convert to decimal for internal use
        self.feedlist_minscore_int = feedlist_minscore if feedlist_minscore is not None else 25
        self.feedlist_minscore = self.feedlist_minscore_int / 100.0  # Convert to decimal (e.g., 25 -> 0.25)

class SemanticScholarItem(Item):
    def __init__(self, paper_info):
        self.paper_info = paper_info
        article_id = uuid.uuid3(uuid.NAMESPACE_URL, paper_info['url'])

        super().__init__(None, str(article_id))

        tldr = (
            ('(tl;dr) ' + paper_info['tldr']['text'])
            if paper_info['tldr'] and paper_info['tldr']['text']
            else '')
        self.title = paper_info['title']
        self.content = paper_info['abstract'] or tldr
        self.href = paper_info['url']
        self.author = ', '.join([a['name'] for a in paper_info['authors']])
        self.origin = self.determine_journal(paper_info)
        self.mediaUrl = paper_info['url']

        pdate = paper_info['publicationDate']
        if pdate is not None:
            pubtime = datetime(*list(map(int, paper_info['publicationDate'].split('-'))))
            self.published = int(pubtime.timestamp())
        else:
            self.published = None

    def determine_journal(self, paper_info):
        if paper_info['journal']:
            return paper_info['journal']['name']
        elif paper_info['venue']:
            return paper_info['venue']
        elif 'ArXiv' in paper_info['externalIds']:
            return 'arXiv'
        else:
            return 'Unknown'

def admin_required(f):
    """Decorator to require admin privileges for a route"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)  # Forbidden
        return f(*args, **kwargs)
    return decorated_function

def _process_poster_job(app, job_id, feed_ids, config_path):
    """Process poster generation in background thread"""
    try:
        
        # Load summarization API configuration
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        api_config = config.get('summarization_api')
        if not api_config:
            log.error("Summarization API not configured in config file")
            with app.poster_jobs_lock:
                app.poster_jobs[job_id]['status'] = 'error'
                app.poster_jobs[job_id]['error'] = 'Summarization API not configured'
            return
        
        
        # Get database connection function from app context
        with app.app_context():
            # Fetch article data from database
            # Filter out non-PostgreSQL parameters
            pg_config = {k: v for k, v in app.db_config.items() if k != 'type'}
            conn = psycopg2.connect(**pg_config)
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Get articles with content/tldr
            placeholders = ','.join(['%s'] * len(feed_ids))
            query = f"""
                SELECT id, title, author, origin, published, content, tldr, link
                FROM feeds
                WHERE id IN ({placeholders})
            """
            cursor.execute(query, feed_ids)
            
            articles = cursor.fetchall()
            cursor.close()
            conn.close()
            
            if not articles:
                log.error("No articles found in database for given IDs")
                with app.poster_jobs_lock:
                    app.poster_jobs[job_id]['status'] = 'error'
                    app.poster_jobs[job_id]['error'] = 'No articles found'
                return
            
            # Format articles for infographic
            formatted_articles = []
            for i, article in enumerate(articles):
                try:
                    formatted_article = {
                        "title": article.get("title", ""),
                        "authors": article.get("author", ""),
                        "source": article.get("origin", ""),
                        "published": article.get("published", "").isoformat() if article.get("published") and hasattr(article.get("published"), "isoformat") else str(article.get("published", "")),
                        "abstract": article.get("tldr", "") or (article.get("content", "")[:500] + "..." if article.get("content") else ""),
                        "link": article.get("link", "")
                    }
                    formatted_articles.append(formatted_article)
                except Exception as e:
                    log.error(f"Error formatting article {i} (id={article.get('id')}): {e}")
                    continue
            
            
            # Create prompt for infographic generation
            prompt = f"""You are an expert at creating beautiful, informative scientific infographics. Create a single-page React-based HTML infographic poster that visualizes the following collection of research articles.

Articles data:
{json.dumps(formatted_articles, indent=2)}

Create a complete, self-contained HTML file with the following requirements:

1. Use React and modern CSS (with inline styles) to create a visually appealing infographic poster
2. Include these sections:
   - Header with title "Research Landscape Overview"
   - Visual representation of common themes (use icons, shapes, or creative layouts)
   - Key topics displayed as interconnected nodes or cards with relationships
   - Article Insights section: DO NOT create a simple list. Instead, create visual cards or elements that highlight:
     * The core scientific contribution or breakthrough of each paper
     * Key methodologies or techniques introduced
     * Impact and implications of the findings
     * Connections between papers (show relationships visually)
     * Use visual metaphors, diagrams, or icons to represent concepts
   - Future research directions as an inspiring visual element

3. Design requirements:
   - WHITE BACKGROUND with clean, modern design
   - Use a professional color palette with colorful accents for visual elements (avoid dark backgrounds)
   - Include data visualization elements (charts, graphs, or creative visual metaphors)
   - Make article insights visually rich with icons, diagrams, or conceptual illustrations
   - Each article should have substantial visual representation of its key message
   - Make it responsive and visually balanced
   - Use icons from Font Awesome or create simple SVG icons
   - Include subtle animations or transitions for interactivity

4. Technical requirements:
   - Complete HTML file with React CDN links
   - All styles inline or in <style> tags
   - No external dependencies except React and Font Awesome CDN
   - Use React hooks for any interactive elements
   - The file should be immediately viewable in a browser

IMPORTANT: For the Article Insights section, avoid boring lists. Create rich visual representations that capture the essence and key contributions of each paper. Use creative layouts, visual metaphors, and detailed information design.

Generate ONLY the complete HTML code, starting with <!DOCTYPE html> and ending with </html>. Make it visually stunning and informative, focusing on clarity and impact."""

            # Initialize OpenAI client
            
            client = OpenAI(
                api_key=api_config["api_key"],
                base_url=api_config.get("api_url", "https://api.openai.com/v1")
            )
            
            # Generate infographic
            start_time = time.time()
            
            try:
                # Set a longer timeout for the client
                client.timeout = 300.0  # 5 minutes timeout
                
                response = client.chat.completions.create(
                    model=api_config.get("model", "gpt-4o-mini"),
                    messages=[
                        {"role": "system", "content": "You are an expert at creating beautiful, informative scientific infographics using React and modern web technologies. Always output complete, working HTML code."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.8,
                    max_tokens=128000,
                    timeout=300.0  # 5 minutes timeout
                )
                
                elapsed_time = time.time() - start_time
                
            except Exception as api_error:
                elapsed_time = time.time() - start_time
                log.error(f"API call failed after {elapsed_time:.2f} seconds: {api_error}")
                with app.poster_jobs_lock:
                    app.poster_jobs[job_id]['status'] = 'error'
                    app.poster_jobs[job_id]['error'] = f'API call failed: {str(api_error)}'
                return
            
            poster_html = response.choices[0].message.content
            
            # Extract HTML content if wrapped in markdown code blocks
            if "```html" in poster_html:
                start = poster_html.find("```html") + 7
                end = poster_html.find("```", start)
                poster_html = poster_html[start:end].strip()
            elif "```" in poster_html:
                start = poster_html.find("```") + 3
                end = poster_html.find("```", start)
                poster_html = poster_html[start:end].strip()
            
            # Store result
            with app.poster_jobs_lock:
                app.poster_jobs[job_id]['status'] = 'completed'
                app.poster_jobs[job_id]['result'] = poster_html
            
    except Exception as e:
        import traceback
        log.error(f"Poster generation job {job_id} failed: {type(e).__name__}: {str(e)}")
        log.error(f"Traceback:\n{traceback.format_exc()}")
        
        # Store error
        with app.poster_jobs_lock:
            app.poster_jobs[job_id]['status'] = 'error'
            app.poster_jobs[job_id]['error'] = str(e)


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
    
    # Store db_config in app for background threads
    app.db_config = db_config

    # Set up Flask secret key
    app.secret_key = google_config.get('flask_secret_key', secrets.token_hex(32))

    # Set session lifetime to 30 days
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
    
    # Initialize job queue for poster generation
    app.poster_jobs = {}
    app.poster_jobs_lock = threading.Lock()
    
    # Cleanup old jobs every 5 minutes
    def cleanup_old_jobs():
        while True:
            time.sleep(300)  # 5 minutes
            with app.poster_jobs_lock:
                current_time = time.time()
                # Remove jobs older than 10 minutes
                jobs_to_remove = [
                    job_id for job_id, job_data in app.poster_jobs.items()
                    if current_time - job_data.get('created_at', 0) > 600
                ]
                for job_id in jobs_to_remove:
                    log.info(f"Cleaning up old poster job: {job_id}")
                    del app.poster_jobs[job_id]
    
    cleanup_thread = threading.Thread(target=cleanup_old_jobs, daemon=True)
    cleanup_thread.start()

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

    def get_default_model_id():
        """Get the most recent active model ID"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM models
            WHERE is_active = TRUE
            ORDER BY id DESC
            LIMIT 1
        """)
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result[0] if result else 1  # Fallback to 1 if no active models

    @login_manager.user_loader
    def load_user(user_id):
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT id, username, is_admin, timezone, feedlist_minscore FROM users WHERE id = %s", (int(user_id),))
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()

        if user_data:
            return User(user_data['id'], user_data['username'],
                       is_admin=user_data.get('is_admin', False),
                       timezone=user_data.get('timezone', 'Asia/Seoul'),
                       feedlist_minscore=user_data.get('feedlist_minscore'))
        return None

    def get_unlabeled_item():
        """Get a random unlabeled item from the database"""
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get all unlabeled items and pick one randomly, joining with feeds for the URL and predicted score
        default_model_id = get_default_model_id()
        cursor.execute("""
            SELECT ls.id, ls.feed_id, f.title, f.author, f.origin, f.content, ls.score, f.link,
                   pp.score as predicted_score
            FROM labeling_sessions ls
            JOIN feeds f ON ls.feed_id = f.id
            LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = %s
            WHERE ls.score IS NULL
            ORDER BY RANDOM()
            LIMIT 1
        """, (default_model_id,))

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
        # If user is already authenticated, redirect to the main page
        if current_user.is_authenticated:
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('index'))

        # Get the next parameter from the request
        next_page = request.args.get('next')
        return render_template('login.html', next=next_page)

    @app.route('/login/google')
    def google_login():
        """Initiate Google OAuth login"""
        # Store the next parameter in session to preserve it through OAuth flow
        next_page = request.args.get('next')
        if next_page:
            session['next_page'] = next_page

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
                cursor.execute("SELECT id, username, is_admin, timezone, feedlist_minscore FROM users WHERE username = %s", (email,))
                user_data = cursor.fetchone()

                if not user_data:
                    # Create new user (non-admin by default)
                    cursor.execute("""
                        INSERT INTO users (username, password, created, is_admin, timezone)
                        VALUES (%s, %s, CURRENT_TIMESTAMP, false, 'Asia/Seoul')
                        RETURNING id, username, is_admin, timezone
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
                user = User(user_data['id'], user_data['username'], email,
                           is_admin=user_data.get('is_admin', False),
                           timezone=user_data.get('timezone', 'Asia/Seoul'),
                           feedlist_minscore=user_data.get('feedlist_minscore'))
                login_user(user)

                # Make the session permanent
                session.permanent = True

                # Redirect to the original requested page or home
                # First check session, then request args
                next_page = session.pop('next_page', None) or request.args.get('next')
                if next_page and next_page.startswith('/'):
                    return redirect(next_page)
                else:
                    return redirect(url_for('index'))

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
        # Filter preferences by current user
        user_id = current_user.id
        default_model_id = get_default_model_id()


        # Get user's bookmark
        cursor.execute("SELECT bookmark FROM users WHERE id = %s", (user_id,))
        bookmark_result = cursor.fetchone()
        bookmark_id = bookmark_result['bookmark'] if bookmark_result else None

        # Build WHERE clause based on min_score
        if min_score <= 0:
            where_clause = "1=1"  # Show all feeds
            query_params = (user_id, default_model_id, limit + 1, offset)
        else:
            where_clause = "pp.score >= %s"  # Only show feeds with scores above threshold
            query_params = (user_id, default_model_id, min_score, limit + 1, offset)

        cursor.execute(f"""
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
            ),
            broadcast_status AS (
                SELECT DISTINCT feed_id, TRUE as has_broadcast
                FROM broadcasts
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
                COALESCE(star_p.score > 0, FALSE) as starred,
                COALESCE(b.has_broadcast, FALSE) as broadcasted,
                inter_p.score as label,
                COALESCE(vc.positive_votes, 0) as positive_votes,
                COALESCE(vc.negative_votes, 0) as negative_votes
            FROM feeds f
            LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = %s
            LEFT JOIN latest_prefs star_p ON f.id = star_p.feed_id AND star_p.source = 'feed-star'
            LEFT JOIN latest_prefs inter_p ON f.id = inter_p.feed_id AND inter_p.source IN ('interactive', 'alert-feedback')
            LEFT JOIN broadcast_status b ON f.id = b.feed_id
            LEFT JOIN vote_counts vc ON f.id = vc.feed_id
            WHERE {where_clause}
            ORDER BY f.added DESC
            LIMIT %s OFFSET %s
        """, query_params)

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        # Check if there are more results
        has_more = len(results) > limit
        feeds = results[:limit] if has_more else results

        # Include bookmark ID on first page
        response_data = {
            'feeds': feeds,
            'has_more': has_more,
            'bookmark_id': bookmark_id
        }

        return jsonify(response_data)

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
        user_id = current_user.id
        data = request.get_json() or {}
        action = data.get('action', 'toggle')  # 'star', 'unstar', or 'toggle'

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            # Check if preference already exists
            cursor.execute("""
                SELECT id, score FROM preferences
                WHERE feed_id = %s AND user_id = %s AND source = 'feed-star'
            """, (feed_id, user_id))

            existing = cursor.fetchone()

            if action == 'toggle':
                # Toggle based on current state
                if existing and existing['score'] > 0:
                    action = 'unstar'
                else:
                    action = 'star'

            if action == 'unstar':
                if existing:
                    # Remove the star preference
                    cursor.execute("""
                        DELETE FROM preferences
                        WHERE feed_id = %s AND user_id = %s AND source = 'feed-star'
                    """, (feed_id, user_id))
            else:  # action == 'star'
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

                # When starring, add to broadcasts table for all active channels
                cursor.execute("""
                    INSERT INTO broadcasts (feed_id, channel_id, broadcasted_time)
                    SELECT %s, id, NULL
                    FROM channels
                    WHERE is_active = TRUE
                    ON CONFLICT (feed_id, channel_id) DO NOTHING
                """, (feed_id,))

            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({'success': True, 'action': action})
        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/feeds/<int:feed_id>/feedback', methods=['POST'])
    @login_required
    def api_feedback_feed(feed_id):
        """API endpoint to set feedback (like/dislike) for a feed"""
        user_id = current_user.id
        data = request.get_json()
        score = data.get('score')

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            if score is None:
                # Remove feedback from both sources
                cursor.execute("""
                    DELETE FROM preferences
                    WHERE feed_id = %s AND user_id = %s AND source IN ('interactive', 'alert-feedback')
                """, (feed_id, user_id))
            else:
                # Check if preference already exists from either source
                cursor.execute("""
                    SELECT id, source FROM preferences
                    WHERE feed_id = %s AND user_id = %s AND source IN ('interactive', 'alert-feedback')
                    ORDER BY time DESC
                    LIMIT 1
                """, (feed_id, user_id))

                existing = cursor.fetchone()

                if existing:
                    # Update existing preference (keep the original source)
                    cursor.execute("""
                        UPDATE preferences
                        SET score = %s, time = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (float(score), existing['id']))
                else:
                    # Insert new preference with 'interactive' source
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

    @app.route('/api/user/preferences', methods=['PUT'])
    @login_required
    def api_update_user_preferences():
        """Update current user's preferences"""
        data = request.get_json()

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Handle feedlist_minscore update
            if 'feedlist_minscore' in data:
                # Convert decimal to integer for storage (e.g., 0.25 -> 25)
                min_score_decimal = float(data['feedlist_minscore'])
                min_score_int = int(min_score_decimal * 100)

                cursor.execute("""
                    UPDATE users
                    SET feedlist_minscore = %s
                    WHERE id = %s
                """, (min_score_int, current_user.id))

                # Update the current user object
                current_user.feedlist_minscore_int = min_score_int
                current_user.feedlist_minscore = min_score_decimal

            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({'success': True})
        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/user/bookmark', methods=['PUT'])
    @login_required
    def api_update_bookmark():
        """Update user's reading position bookmark"""
        data = request.get_json()
        feed_id = data.get('feed_id')

        if not feed_id:
            return jsonify({'success': False, 'error': 'feed_id is required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE users
                SET bookmark = %s
                WHERE id = %s
            """, (feed_id, current_user.id))

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

    @app.route('/settings/events')
    @admin_required
    def settings_events():
        """Event logs viewer page"""
        return render_template('settings_events.html')

    # Channels API endpoints
    @app.route('/api/settings/channels')
    @admin_required
    def api_get_channels():
        """Get all channels"""
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT id, name, endpoint_url, score_threshold, model_id, is_active
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
                INSERT INTO channels (name, endpoint_url, score_threshold, model_id, is_active)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (data['name'], data['endpoint_url'],
                  data.get('score_threshold', 0.7), data.get('model_id', 1),
                  data.get('is_active', True)))

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
                SET name = %s, endpoint_url = %s, score_threshold = %s, model_id = %s, is_active = %s
                WHERE id = %s
            """, (data['name'], data['endpoint_url'],
                  data.get('score_threshold', 0.7), data.get('model_id', 1),
                  data.get('is_active', True), channel_id))

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
            SELECT id, username, created, lastlogin, timezone
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
                INSERT INTO users (username, password, created, timezone)
                VALUES (%s, %s, CURRENT_TIMESTAMP, %s)
                RETURNING id
            """, (data['username'], data.get('password', 'default'),
                  data.get('timezone', 'Asia/Seoul')))

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
            # Update query parts
            update_parts = ['username = %s']
            update_values = [data['username']]

            if 'timezone' in data:
                update_parts.append('timezone = %s')
                update_values.append(data['timezone'])

            # Add user_id at the end
            update_values.append(user_id)

            cursor.execute(f"""
                UPDATE users
                SET {', '.join(update_parts)}
                WHERE id = %s
            """, update_values)

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

    @app.route('/api/search')
    @login_required
    def api_search():
        """API endpoint to search feeds by text similarity"""
        query = request.args.get('q', '').strip()
        if not query:
            return jsonify({'error': 'Query parameter is required'}), 400

        try:
            # Load embedding database with config
            edb = EmbeddingDatabase(config_path)

            # Get user ID and default model ID for filtering
            user_id = current_user.id
            default_model_id = get_default_model_id()

            # Search using embeddings
            search_results = edb.search_by_text(query, limit=50, user_id=user_id, model_id=default_model_id)

            # Convert to format compatible with feeds list
            feeds = []
            for feed in search_results:
                feeds.append({
                    'rowid': feed['feed_id'],
                    'external_id': feed['external_id'],
                    'title': feed['title'],
                    'author': feed['author'],
                    'origin': feed['origin'],
                    'link': feed['link'],
                    'published': feed['published'],
                    'added': feed['added'],
                    'score': feed['predicted_score'],
                    'starred': feed['starred'],
                    'broadcasted': feed['broadcasted'],
                    'label': feed['label'],
                    'similarity': float(feed['similarity']),
                    'positive_votes': feed['positive_votes'],
                    'negative_votes': feed['negative_votes']
                })

            return jsonify({'feeds': feeds})

        except Exception as e:
            log.error(f"Error searching feeds: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/feeds/<int:feed_id>/similar')
    @login_required
    def api_similar_feeds(feed_id):
        """API endpoint to get similar feeds"""
        try:
            # Load embedding database with config
            edb = EmbeddingDatabase(config_path)

            # Get similar articles filtered by current user with default model
            default_model_id = get_default_model_id()
            similar_feeds = edb.find_similar(feed_id, limit=30, user_id=current_user.id, model_id=default_model_id)

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
                    'similarity': float(feed['similarity']),
                    'positive_votes': feed['positive_votes'],
                    'negative_votes': feed['negative_votes']
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

            response_data = {
                'source_article': source_article,
                'similar_feeds': feeds
            }

            return jsonify(response_data)

        except Exception as e:
            log.error(f"Error finding similar articles: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/summarize', methods=['POST'])
    @login_required
    def api_summarize():
        """Generate a summary of articles using LLM"""
        try:
            data = request.get_json()
            feed_ids = data.get('feed_ids', [])
            
            if not feed_ids:
                return jsonify({'error': 'No feed IDs provided'}), 400
            
            # Load summarization API configuration
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            api_config = config.get('summarization_api')
            if not api_config:
                return jsonify({'error': 'Summarization API not configured'}), 500
            
            # Fetch article data from database
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Get articles with content/tldr
            placeholders = ','.join(['%s'] * len(feed_ids))
            query = f"""
                SELECT id, title, author, origin, published, content, tldr
                FROM feeds
                WHERE id IN ({placeholders})
            """
            cursor.execute(query, feed_ids)
            
            articles = cursor.fetchall()
            cursor.close()
            conn.close()
            if not articles:
                return jsonify({'error': 'No articles found'}), 404
            
            # Format articles for summarization
            formatted_articles = []
            article_refs = []  # Store author-year references
            for i, article in enumerate(articles, 1):
                try:
                    parts = []
                    
                    # Extract first author's last name and year for reference
                    first_author = "Unknown"
                    year = "n.d."
                    
                    if article.get('author') and article['author'] is not None:
                        # Extract first author's last name
                        authors = str(article['author']).split(',')[0].strip()
                        # Try to get last name (assume last word is last name)
                        first_author = authors.split()[-1] if authors else "Unknown"
                        parts.append(f"Authors: {article['author']}")
                    
                    if article.get('published') and article['published'] is not None:
                        # Extract year from published date
                        if hasattr(article['published'], 'year'):
                            year = str(article['published'].year)
                        elif hasattr(article['published'], 'isoformat'):
                            year = article['published'].isoformat()[:4]
                            parts.append(f"Published: {article['published'].isoformat()}")
                        else:
                            pub_str = str(article['published'])
                            if len(pub_str) >= 4:
                                year = pub_str[:4]
                            parts.append(f"Published: {article['published']}")
                    
                    article_ref = f"{first_author} {year}"
                    article_refs.append(article_ref)
                    
                    if article.get('title') and article['title'] is not None:
                        parts.append(f"Title: {article['title']}")
                    if article.get('origin') and article['origin'] is not None:
                        parts.append(f"Source: {article['origin']}")
                    if article.get('tldr') and article['tldr'] is not None:
                        parts.append(f"Abstract: {article['tldr']}")
                    elif article.get('content') and article['content'] is not None:
                        # Truncate content if too long
                        content = str(article['content'])  # Ensure it's a string
                        if len(content) > 500:
                            content = content[:497] + '...'
                        parts.append(f"Abstract: {content}")
                    
                    if parts:  # Only add if we have some content
                        formatted_articles.append(f"[{article_ref}]\n" + "\n".join(parts))
                except Exception as e:
                    log.error(f"Error formatting article {i} (id={article.get('id')}): {e}")
                    continue
            
            if not formatted_articles:
                return jsonify({'error': 'No valid articles to summarize'}), 400
            
            articles_text = "\n\n---\n\n".join(formatted_articles)
            
            # Create prompt
            prompt = f"""You are an expert scientific literature analyst. Analyze the following collection of research articles and provide a focused summary.

{articles_text}

Start your response directly with the numbered sections below. Do not include any introductory sentences like "Here is my analysis" or "Based on the provided articles". Do not repeat the format instructions (like "2-3 sentences" or "3-4 bullet points") in your output. Begin immediately with:

1. **Common Themes**: Identify the main research areas connecting these articles in 2-3 sentences.

2. **Key Topics**: List the most significant concepts, methods, or findings that appear across multiple papers as 3-4 bullet points.

3. **Unique Contributions**: For each article, briefly state what distinguishes it from the others in one sentence. Reference articles using their author-year format (e.g., "Smith 2023 introduces...").

4. **Future Directions**: Based on these papers, provide 2-3 bullet points on the most promising research opportunities.

Keep your response focused and actionable, using clear Markdown formatting. When referencing specific papers, use the author-year format provided in square brackets for each article."""
            
            # Initialize OpenAI client with Gemini backend
            client = OpenAI(
                api_key=api_config["api_key"],
                base_url=api_config["api_url"]
            )
            
            # Generate summarization
            response = client.chat.completions.create(
                model=api_config["model"],
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing and summarizing scientific literature."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=8000
            )
            
            summary_markdown = response.choices[0].message.content
            
            # Ensure we have valid content
            if not summary_markdown:
                return jsonify({'error': 'Empty response from LLM'}), 500
            
            # Ensure it's a string
            if not isinstance(summary_markdown, str):
                log.error(f"Unexpected type for summary_markdown: {type(summary_markdown)}")
                summary_markdown = str(summary_markdown)
            
            # Convert Markdown to HTML
            summary_html = markdown2.markdown(
                summary_markdown,
                extras=['fenced-code-blocks', 'tables', 'strike', 'task_list']
            )
            
            return jsonify({
                'success': True,
                'summary_html': summary_html,
                'summary_markdown': summary_markdown
            })
            
        except Exception as e:
            import traceback
            log.error(f"Error generating summary: {e}")
            log.error(f"Traceback:\n{traceback.format_exc()}")
            return jsonify({'error': 'Failed to generate summary'}), 500

    @app.route('/api/generate-poster', methods=['POST'])
    @login_required
    def api_generate_poster():
        """Queue a poster generation job and return job ID"""
        try:
            data = request.get_json()
            feed_ids = data.get('feed_ids', [])
            
            if not feed_ids:
                log.error("No feed IDs provided in request")
                return jsonify({'error': 'No feed IDs provided'}), 400
            
            # Generate unique job ID
            job_id = str(uuid.uuid4())
            
            # Store job in queue
            with app.poster_jobs_lock:
                app.poster_jobs[job_id] = {
                    'status': 'pending',
                    'created_at': time.time(),
                    'user_id': current_user.id,
                    'feed_ids': feed_ids,
                    'result': None,
                    'error': None
                }
            
            # Start background thread to process the job
            thread = threading.Thread(
                target=_process_poster_job, 
                args=(app, job_id, feed_ids, config_path),
                daemon=True
            )
            thread.start()
            
            # Return job ID immediately
            return jsonify({
                'success': True,
                'job_id': job_id
            })
            
        except Exception as e:
            log.error(f"Error creating poster job: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/poster-status/<job_id>', methods=['GET'])
    @login_required
    def api_poster_status(job_id):
        """Check the status of a poster generation job"""
        with app.poster_jobs_lock:
            job = app.poster_jobs.get(job_id)
            
            if not job:
                return jsonify({'error': 'Job not found'}), 404
            
            # Check if job belongs to current user
            if job['user_id'] != current_user.id and not current_user.is_admin:
                return jsonify({'error': 'Unauthorized'}), 403
            
            # Return job status
            response = {
                'job_id': job_id,
                'status': job['status'],
                'created_at': job['created_at']
            }
            
            if job['status'] == 'completed':
                response['poster_html'] = job['result']
                # Clear the job after returning it
                del app.poster_jobs[job_id]
            elif job['status'] == 'error':
                response['error'] = job['error']
                # Clear the job after returning the error
                del app.poster_jobs[job_id]
            
            return jsonify(response)

    # Models API endpoints
    @app.route('/api/settings/models')
    @admin_required
    def api_get_models():
        """Get all models"""
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute("""
            SELECT id, name, user_id, created, is_active
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
                INSERT INTO models (name, user_id, created, is_active)
                VALUES (%s, %s, CURRENT_TIMESTAMP, %s)
                RETURNING id
            """, (data['name'], data.get('user_id', 1),
                  data.get('is_active', True)))

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
            # Update query parts
            update_parts = ['name = %s']
            update_values = [data['name']]

            if 'is_active' in data:
                update_parts.append('is_active = %s')
                update_values.append(data['is_active'])

            # Add model_id at the end
            update_values.append(model_id)

            cursor.execute(f"""
                UPDATE models
                SET {', '.join(update_parts)}
                WHERE id = %s
            """, update_values)

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

    # Event logs API endpoints
    @app.route('/api/settings/events')
    @admin_required
    def api_get_events():
        """Get event logs with pagination"""
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        offset = (page - 1) * per_page

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            # Get total count
            cursor.execute("SELECT COUNT(*) as total FROM events")
            total = cursor.fetchone()['total']

            # Get events with feed information
            cursor.execute("""
                SELECT e.*, f.title as feed_title
                FROM events e
                LEFT JOIN feeds f ON e.feed_id = f.id
                ORDER BY e.occurred DESC
                LIMIT %s OFFSET %s
            """, (per_page, offset))
            events = cursor.fetchall()

            cursor.close()
            conn.close()

            # Convert datetime to ISO format for JSON
            for event in events:
                if event['occurred']:
                    event['occurred'] = event['occurred'].isoformat()

            return jsonify({
                'events': events,
                'total': total,
                'page': page,
                'per_page': per_page,
                'has_more': offset + per_page < total
            })
        except Exception as e:
            cursor.close()
            conn.close()
            return jsonify({'error': str(e)}), 500

    # Slack feedback routes
    @app.route('/feedback/<int:feed_id>/interested')
    def slack_feedback_interested(feed_id):
        """Handle Slack feedback for interested"""
        return handle_slack_feedback(feed_id, 1)

    @app.route('/feedback/<int:feed_id>/not-interested')
    def slack_feedback_not_interested(feed_id):
        """Handle Slack feedback for not interested"""
        return handle_slack_feedback(feed_id, 0)

    def handle_slack_feedback(feed_id, score):
        """Common handler for Slack feedback routes"""
        # Check if user is logged in, if not, redirect to login
        if not current_user.is_authenticated:
            return redirect(url_for('login', next=request.path))

        user_id = current_user.id

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            # First, check if the feed exists
            cursor.execute("SELECT id, title FROM feeds WHERE id = %s", (feed_id,))
            feed = cursor.fetchone()

            if not feed:
                cursor.close()
                conn.close()
                return render_template('feedback_error.html', message="Article not found"), 404

            # Check if any recent preference exists (within 1 month)
            cursor.execute("""
                SELECT id, source FROM preferences
                WHERE feed_id = %s AND user_id = %s
                AND time > CURRENT_TIMESTAMP - INTERVAL '1 month'
                ORDER BY time DESC
                LIMIT 1
            """, (feed_id, user_id))

            existing = cursor.fetchone()

            if existing:
                # Update the existing recent preference (override regardless of source)
                cursor.execute("""
                    UPDATE preferences
                    SET score = %s, time = CURRENT_TIMESTAMP, source = 'alert-feedback'
                    WHERE id = %s
                """, (float(score), existing['id']))
            else:
                # No recent preference exists, insert new one
                cursor.execute("""
                    INSERT INTO preferences (feed_id, user_id, time, score, source)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, %s, 'alert-feedback')
                """, (feed_id, user_id, float(score)))

            conn.commit()
            cursor.close()
            conn.close()

            # Render feedback confirmation page with similar articles link
            feedback_type = "interested" if score == 1 else "not interested"
            return render_template('feedback_success.html',
                                 feed_title=feed['title'],
                                 feedback_type=feedback_type,
                                 feed_id=feed_id)

        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            log.error(f"Error recording Slack feedback: {e}")
            return render_template('feedback_error.html',
                                 message="Error recording feedback. Please try again."), 500

    # Slack interactivity endpoint
    @app.route('/slack-interactivity', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
    def slack_interactivity():
        """Handle Slack interactivity requests"""
        payload = json.loads(dict(request.form)['payload'])
        if 'user' in payload and 'actions' in payload:
            user_id = payload['user']['id']
            user_name = payload['user']['name']
            action, related_feed_id = payload['actions'][0]['value'].split('_', 1)
            related_feed_id = int(related_feed_id)
            log.info(f"User {user_name} ({user_id}) performed action: {action} on feed ID {related_feed_id}")

            # Insert event into database
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                # Check if feed exists
                cursor.execute("SELECT id FROM feeds WHERE id = %s", (related_feed_id,))
                if cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO events (event_type, user_id, user_name, feed_id)
                        VALUES (%s, %s, %s, %s)
                    """, (action, user_id, user_name, related_feed_id))
                    conn.commit()
                    log.info(f"Event logged to database: {action} by {user_name} on feed {related_feed_id}")
                else:
                    log.warning(f"Feed ID {related_feed_id} not found, skipping event logging")
            except Exception as e:
                log.error(f"Failed to log event to database: {e}")
                conn.rollback()
            finally:
                cursor.close()
                conn.close()

        return '', 200

    # Semantic Scholar search endpoints
    @app.route('/api/semantic-scholar/search', methods=['POST'])
    @admin_required
    def api_semantic_scholar_search():
        """Search for papers on Semantic Scholar (admin only)"""
        data = request.get_json()
        query = data.get('query', '').strip()

        if not query:
            return jsonify({'error': 'Query is required'}), 400

        try:
            # Load Semantic Scholar configuration
            with open(config_path, 'r') as f:
                config_yaml = yaml.safe_load(f)

            s2_config = config_yaml.get('semanticscholar', {})
            api_key = s2_config.get('api_key')
            api_base_url = s2_config.get('api_url', 'https://api.semanticscholar.org/graph/v1/paper')
            api_url = f"{api_base_url}/search"

            if not api_key:
                return jsonify({'error': 'Semantic Scholar API key not configured'}), 500

            # Search Semantic Scholar
            fields = 'title,year,url,authors,abstract,venue,journal,publicationDate,externalIds,tldr'
            api_headers = {'X-API-KEY': api_key}
            params = {
                'query': query,
                'fields': fields,
                'year': '2023-',  # Only recent papers
                'limit': 20
            }

            response = requests.get(api_url, headers=api_headers, params=params)
            response.raise_for_status()

            result = response.json()
            papers = result.get('data', [])

            # Check which papers already exist in our database
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            for paper in papers:
                # Generate the same ID that SemanticScholarItem would generate
                article_id = str(uuid.uuid3(uuid.NAMESPACE_URL, paper['url']))

                # Check if this paper already exists
                cursor.execute("""
                    SELECT id FROM feeds WHERE external_id = %s
                """, (article_id,))

                existing = cursor.fetchone()
                paper['already_added'] = existing is not None
                paper['article_id'] = article_id

            cursor.close()
            conn.close()

            return jsonify({
                'success': True,
                'papers': papers,
                'total': len(papers)
            })

        except requests.RequestException as e:
            log.error(f"Semantic Scholar API error: {e}")
            return jsonify({'error': 'Failed to search Semantic Scholar'}), 500
        except Exception as e:
            log.error(f"Error in Semantic Scholar search: {e}")
            return jsonify({'error': 'An error occurred'}), 500

    @app.route('/api/semantic-scholar/add', methods=['POST'])
    @admin_required
    def api_semantic_scholar_add():
        """Add a paper from Semantic Scholar to the database (admin only)"""
        data = request.get_json()
        paper_data = data.get('paper')

        if not paper_data:
            return jsonify({'error': 'Paper data is required'}), 400

        try:
            # Create SemanticScholarItem
            item = SemanticScholarItem(paper_data)

            # Load database configuration
            with open(config_path, 'r') as f:
                config_yaml = yaml.safe_load(f)

            # Create database connection
            db = FeedDatabase(config_path)

            # Check if item already exists
            if item not in db:
                # Add the item without starring
                feed_id = db.insert_item(item, starred=0)
                db.commit()

                # Generate embeddings and predict preferences
                embeddingdb = EmbeddingDatabase(config_path)
                predictor = FeedPredictor(db, embeddingdb, config_path)
                model_dir = config_yaml.get('models', {}).get('path', '.')

                try:
                    # This will generate embeddings and add to broadcast queues if eligible
                    predictor.predict_and_queue_feeds([feed_id], model_dir)
                except Exception as e:
                    log.error(f"Failed to process feed {feed_id}: {e}")
                    # Continue anyway - the item is already added

                return jsonify({
                    'success': True,
                    'message': 'Paper added successfully',
                    'feed_id': feed_id
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Paper already exists in database'
                }), 409

        except Exception as e:
            log.error(f"Error adding Semantic Scholar paper: {e}")
            return jsonify({'error': 'Failed to add paper'}), 500

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
