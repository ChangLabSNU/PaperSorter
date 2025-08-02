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

"""Search API endpoints."""

import json
import uuid
import yaml
import requests
import markdown2
import psycopg2
import psycopg2.extras
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from openai import OpenAI
from ...log import log
from ...embedding_database import EmbeddingDatabase
from ...feed_database import FeedDatabase
from ...feed_predictor import FeedPredictor
from ..auth.decorators import admin_required
from ..models.semantic_scholar import SemanticScholarItem
from ..utils.database import get_default_model_id

search_bp = Blueprint('search', __name__)


@search_bp.route('/api/search')
@login_required
def api_search():
    """API endpoint to search feeds by text similarity."""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'Query parameter is required'}), 400

    try:
        # Load embedding database with config
        config_path = current_app.config['CONFIG_PATH']
        edb = EmbeddingDatabase(config_path)

        # Get user ID and default model ID for filtering
        user_id = current_user.id
        conn = current_app.config['get_db_connection']()
        default_model_id = get_default_model_id(conn)

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

        # Log the search event
        cursor = conn.cursor()
        try:
            # Log text search event with the most relevant result (if any)
            # Store search query in content field, and the most relevant feed_id if results exist
            feed_id_to_log = search_results[0]['feed_id'] if search_results else None
            cursor.execute("""
                INSERT INTO events (event_type, user_id, feed_id, content)
                VALUES (%s, %s, %s, %s)
            """, ('web:text-search', current_user.id, feed_id_to_log, query))
            conn.commit()
        except Exception as e:
            log.error(f"Failed to log text search event: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

        return jsonify({'feeds': feeds})

    except Exception as e:
        log.error(f"Error searching feeds: {e}")
        return jsonify({'error': str(e)}), 500


@search_bp.route('/api/summarize', methods=['POST'])
@login_required
def api_summarize():
    """Generate a summary of articles using LLM."""
    try:
        data = request.get_json()
        feed_ids = data.get('feed_ids', [])

        if not feed_ids:
            return jsonify({'error': 'No feed IDs provided'}), 400

        # Load summarization API configuration
        config_path = current_app.config['CONFIG_PATH']
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        api_config = config.get('summarization_api')
        if not api_config:
            return jsonify({'error': 'Summarization API not configured'}), 500

        # Fetch article data from database
        conn = current_app.config['get_db_connection']()
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

        if not articles:
            conn.close()
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
            conn.close()
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
            conn.close()
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

        # Log the event to database
        cursor = conn.cursor()
        try:
            # Log AI summary generation event - store all feed IDs in content field
            if feed_ids:
                # Store the list of feed IDs as JSON in the content field
                cursor.execute("""
                    INSERT INTO events (event_type, user_id, feed_id, content)
                    VALUES (%s, %s, %s, %s)
                """, ('web:ai-summary-text', current_user.id, feed_ids[0], json.dumps(feed_ids)))
                conn.commit()
        except Exception as e:
            log.error(f"Failed to log AI summary event: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

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


@search_bp.route('/api/semantic-scholar/search', methods=['POST'])
@admin_required
def api_semantic_scholar_search():
    """Search for papers on Semantic Scholar (admin only)."""
    data = request.get_json()
    query = data.get('query', '').strip()

    if not query:
        return jsonify({'error': 'Query is required'}), 400

    try:
        # Load Semantic Scholar configuration
        config_path = current_app.config['CONFIG_PATH']
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
        conn = current_app.config['get_db_connection']()
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


@search_bp.route('/api/semantic-scholar/add', methods=['POST'])
@admin_required
def api_semantic_scholar_add():
    """Add a paper from Semantic Scholar to the database (admin only)."""
    data = request.get_json()
    paper_data = data.get('paper')

    if not paper_data:
        return jsonify({'error': 'Paper data is required'}), 400

    try:
        # Create SemanticScholarItem
        item = SemanticScholarItem(paper_data)

        # Load database configuration
        config_path = current_app.config['CONFIG_PATH']
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