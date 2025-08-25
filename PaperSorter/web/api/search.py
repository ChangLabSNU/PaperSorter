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

"""Search API endpoints."""

import json
import yaml
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
from ..models.scholarly_article import ScholarlyArticleItem
from ...providers.factory import ScholarlyDatabaseFactory
from ..utils.database import get_user_model_id, save_search_query

search_bp = Blueprint("search", __name__)


@search_bp.route("/api/search", methods=["GET", "POST"])
@login_required
def api_search():
    """API endpoint to search papers by text similarity."""
    # Support both GET and POST methods
    if request.method == "POST":
        data = request.get_json()
        query = data.get("query", "").strip() if data else ""
    else:
        query = request.args.get("q", "").strip()

    if not query:
        return jsonify({"error": "Query parameter is required"}), 400

    try:
        # Load embedding database with config
        config_path = current_app.config["CONFIG_PATH"]
        edb = EmbeddingDatabase(config_path)

        # Get user ID and default model ID for filtering
        user_id = current_user.id
        conn = current_app.config["get_db_connection"]()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get model_id from primary channel if it exists
        if current_user.primary_channel_id:
            cursor.execute("SELECT model_id FROM channels WHERE id = %s", (current_user.primary_channel_id,))
            channel_result = cursor.fetchone()
            model_id = channel_result["model_id"] if channel_result and channel_result["model_id"] else get_user_model_id(conn, current_user)
        else:
            model_id = get_user_model_id(conn, current_user)

        # Search using embeddings
        search_results = edb.search_by_text(
            query, limit=50, user_id=user_id, model_id=model_id,
            channel_id=current_user.primary_channel_id
        )

        # Convert to format compatible with papers list
        feeds = []
        for feed in search_results:
            feeds.append(
                {
                    "rowid": feed["feed_id"],
                    "external_id": feed["external_id"],
                    "title": feed["title"],
                    "author": feed["author"],
                    "origin": feed["origin"],
                    "link": feed["link"],
                    "published": feed["published"],
                    "added": feed["added"],
                    "score": feed["predicted_score"],
                    "shared": feed["shared"],
                    "broadcasted": feed["broadcasted"],
                    "label": feed["label"],
                    "similarity": float(feed["similarity"]),
                    "positive_votes": feed["positive_votes"],
                    "negative_votes": feed["negative_votes"],
                }
            )

        # Save the search query to saved_searches table
        try:
            short_name = save_search_query(conn, query, current_user.id)
        except Exception as e:
            log.error(f"Failed to save search query: {e}")
            short_name = None

        # Log the search event
        cursor = conn.cursor()
        try:
            # Log text search event with the most relevant result (if any)
            # Store search query in content field, and the most relevant feed_id if results exist
            feed_id_to_log = search_results[0]["feed_id"] if search_results else None
            cursor.execute(
                """
                INSERT INTO events (event_type, user_id, feed_id, content)
                VALUES (%s, %s, %s, %s)
            """,
                ("web:text-search", current_user.id, feed_id_to_log, query),
            )
            conn.commit()
        except Exception as e:
            log.error(f"Failed to log text search event: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

        return jsonify({"feeds": feeds, "short_name": short_name})

    except Exception as e:
        log.error(f"Error searching papers: {e}")
        return jsonify({"error": str(e)}), 500


@search_bp.route("/api/summarize", methods=["POST"])
@login_required
def api_summarize():
    """Generate a summary of articles using LLM."""
    try:
        data = request.get_json()
        feed_ids = data.get("feed_ids", [])

        if not feed_ids:
            return jsonify({"error": "No paper IDs provided"}), 400

        # Load summarization API configuration
        config_path = current_app.config["CONFIG_PATH"]
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        api_config = config.get("summarization_api")
        if not api_config:
            return jsonify({"error": "Summarization API not configured"}), 500

        # Fetch article data from database
        conn = current_app.config["get_db_connection"]()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get articles with content/tldr
        placeholders = ",".join(["%s"] * len(feed_ids))
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
            return jsonify({"error": "No articles found"}), 404

        # Format articles for summarization
        formatted_articles = []
        article_refs = []  # Store author-year references
        for i, article in enumerate(articles, 1):
            try:
                parts = []

                # Extract first author's last name and year for reference
                first_author = "Unknown"
                year = "n.d."

                if article.get("author") and article["author"] is not None:
                    # Extract first author's last name
                    authors = str(article["author"]).split(",")[0].strip()
                    # Try to get last name (assume last word is last name)
                    first_author = authors.split()[-1] if authors else "Unknown"
                    parts.append(f"Authors: {article['author']}")

                if article.get("published") and article["published"] is not None:
                    # Extract year from published date
                    if hasattr(article["published"], "year"):
                        year = str(article["published"].year)
                    elif hasattr(article["published"], "isoformat"):
                        year = article["published"].isoformat()[:4]
                        parts.append(f"Published: {article['published'].isoformat()}")
                    else:
                        pub_str = str(article["published"])
                        if len(pub_str) >= 4:
                            year = pub_str[:4]
                        parts.append(f"Published: {article['published']}")

                article_ref = f"{first_author} {year}"
                article_refs.append(article_ref)

                if article.get("title") and article["title"] is not None:
                    parts.append(f"Title: {article['title']}")
                if article.get("origin") and article["origin"] is not None:
                    parts.append(f"Source: {article['origin']}")
                if article.get("tldr") and article["tldr"] is not None:
                    parts.append(f"Abstract: {article['tldr']}")
                elif article.get("content") and article["content"] is not None:
                    # Truncate content if too long
                    content = str(article["content"])  # Ensure it's a string
                    if len(content) > 500:
                        content = content[:497] + "..."
                    parts.append(f"Abstract: {content}")

                if parts:  # Only add if we have some content
                    formatted_articles.append(f"[{article_ref}]\n" + "\n".join(parts))
            except Exception as e:
                log.error(f"Error formatting article {i} (id={article.get('id')}): {e}")
                continue

        if not formatted_articles:
            conn.close()
            return jsonify({"error": "No valid articles to summarize"}), 400

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
        client = OpenAI(api_key=api_config["api_key"], base_url=api_config["api_url"])

        # Generate summarization
        response = client.chat.completions.create(
            model=api_config["model"],
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at analyzing and summarizing scientific literature.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=8000,
        )

        summary_markdown = response.choices[0].message.content

        # Ensure we have valid content
        if not summary_markdown:
            conn.close()
            return jsonify({"error": "Empty response from LLM"}), 500

        # Ensure it's a string
        if not isinstance(summary_markdown, str):
            log.error(f"Unexpected type for summary_markdown: {type(summary_markdown)}")
            summary_markdown = str(summary_markdown)

        # Convert Markdown to HTML
        summary_html = markdown2.markdown(
            summary_markdown,
            extras=["fenced-code-blocks", "tables", "strike", "task_list"],
        )

        # Log the event to database
        cursor = conn.cursor()
        try:
            # Log AI summary generation event - store all feed IDs in content field
            if feed_ids:
                # Store the list of feed IDs as JSON in the content field
                cursor.execute(
                    """
                    INSERT INTO events (event_type, user_id, feed_id, content)
                    VALUES (%s, %s, %s, %s)
                """,
                    (
                        "web:ai-summary-text",
                        current_user.id,
                        feed_ids[0],
                        json.dumps(feed_ids),
                    ),
                )
                conn.commit()
        except Exception as e:
            log.error(f"Failed to log AI summary event: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

        return jsonify(
            {
                "success": True,
                "summary_html": summary_html,
                "summary_markdown": summary_markdown,
            }
        )

    except Exception as e:
        import traceback

        log.error(f"Error generating summary: {e}")
        log.error(f"Traceback:\n{traceback.format_exc()}")
        return jsonify({"error": "Failed to generate summary"}), 500


@search_bp.route("/api/scholarly-database/search", methods=["POST"])
@admin_required
def api_scholarly_database_search():
    """Search for papers in the configured scholarly database (admin only)."""
    data = request.get_json()
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        # Load configuration and create provider
        config_path = current_app.config["CONFIG_PATH"]
        with open(config_path, "r") as f:
            config_yaml = yaml.safe_load(f)

        # Get scholarly database configuration
        scholarly_config = config_yaml.get("scholarly_database", {})

        # Backward compatibility: use semanticscholar config if new config doesn't exist
        if not scholarly_config:
            s2_config = config_yaml.get("semanticscholar", {})
            if s2_config:
                scholarly_config = {
                    "provider": "semantic_scholar",
                    "semantic_scholar": s2_config
                }
            else:
                return jsonify({"error": "No scholarly database configured"}), 500

        # Get provider name and config
        provider_name = scholarly_config.get("provider", "semantic_scholar")
        provider_config = scholarly_config.get(provider_name, {})

        # Create provider
        provider = ScholarlyDatabaseFactory.create_provider(provider_name, provider_config)
        if not provider:
            return jsonify({"error": f"Failed to create {provider_name} provider"}), 500

        # Search using the provider
        # Don't filter by year for the "Add" interface - users want to add any paper
        articles = provider.search(query, limit=20)

        # Check which papers already exist in our database
        conn = current_app.config["get_db_connection"]()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        papers = []
        for article in articles:
            paper_dict = article.to_dict()

            # Check if this paper already exists
            cursor.execute(
                """
                SELECT id FROM feeds WHERE external_id = %s
            """,
                (article.unique_id,),
            )

            existing = cursor.fetchone()
            paper_dict["already_added"] = existing is not None
            paper_dict["article_id"] = article.unique_id
            papers.append(paper_dict)

        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "papers": papers,
            "total": len(papers),
            "provider": provider.name
        })

    except Exception as e:
        log.error(f"Error in scholarly database search: {e}")
        return jsonify({"error": "Failed to search scholarly database"}), 500

# Keep old endpoint for backward compatibility
@search_bp.route("/api/semantic-scholar/search", methods=["POST"])
@admin_required
def api_semantic_scholar_search():
    """Legacy endpoint - redirects to scholarly database search."""
    return api_scholarly_database_search()


@search_bp.route("/api/scholarly-database/add", methods=["POST"])
@admin_required
def api_scholarly_database_add():
    """Add a paper from scholarly database to the database (admin only)."""
    data = request.get_json()
    article_data = data.get("paper")  # Keep "paper" for backward compatibility

    if not article_data:
        return jsonify({"error": "Paper data is required"}), 400

    try:
        # Load configuration
        config_path = current_app.config["CONFIG_PATH"]
        with open(config_path, "r") as f:
            config_yaml = yaml.safe_load(f)

        # Get scholarly database configuration
        scholarly_config = config_yaml.get("scholarly_database", {})

        # Backward compatibility
        if not scholarly_config:
            scholarly_config = {
                "provider": "semantic_scholar",
                "semantic_scholar": config_yaml.get("semanticscholar", {})
            }

        # Get provider name and config
        provider_name = scholarly_config.get("provider", "semantic_scholar")
        provider_config = scholarly_config.get(provider_name, {})

        # Create provider to parse the article data
        provider = ScholarlyDatabaseFactory.create_provider(provider_name, provider_config)
        if not provider:
            return jsonify({"error": f"Failed to create {provider_name} provider"}), 500

        # Create ScholarlyArticle from the paper data
        # The data is already parsed from the search endpoint, so we need to reconstruct it
        from ...providers.scholarly_database import ScholarlyArticle
        from datetime import datetime
        
        # Extract authors - handle both string array and object array formats
        authors = []
        if article_data.get("authors"):
            for author in article_data["authors"]:
                if isinstance(author, str):
                    authors.append(author)
                elif isinstance(author, dict) and author.get("name"):
                    authors.append(author["name"])
        
        # Extract publication date
        pub_date = None
        if article_data.get("publicationDate"):
            try:
                pub_date = datetime.fromisoformat(article_data["publicationDate"])
            except:
                pass
        elif article_data.get("year"):
            try:
                pub_date = datetime(int(article_data["year"]), 1, 1)
            except:
                pass
        
        # Extract venue/journal
        venue = article_data.get("venue")
        if not venue and article_data.get("journal"):
            journal = article_data["journal"]
            if isinstance(journal, dict):
                venue = journal.get("name")
            else:
                venue = journal
        
        # Extract tldr
        tldr = None
        if article_data.get("tldr"):
            tldr_data = article_data["tldr"]
            if isinstance(tldr_data, dict):
                tldr = tldr_data.get("text")
            else:
                tldr = tldr_data
        
        # Create ScholarlyArticle object
        article = ScholarlyArticle(
            title=article_data.get("title", ""),
            authors=authors,
            abstract=article_data.get("abstract", ""),
            venue=venue,
            url=article_data.get("url", ""),
            doi=article_data.get("doi"),
            publication_date=pub_date,
            tldr=tldr,
            external_ids=article_data.get("external_ids", {})
        )
        
        # Override the auto-generated unique_id if we have a specific one
        if article_data.get("paperId") or article_data.get("article_id") or article_data.get("unique_id"):
            article.unique_id = article_data.get("paperId") or article_data.get("article_id") or article_data.get("unique_id")

        # Create FeedItem from ScholarlyArticle
        item = ScholarlyArticleItem(article)

        # Create database connection
        db = FeedDatabase(config_path)

        # Check if item already exists
        if item not in db:
            # Add the item without starring
            feed_id = db.insert_item(item, shared=0)
            db.commit()

            # Generate embeddings and predict preferences
            embeddingdb = EmbeddingDatabase(config_path)
            predictor = FeedPredictor(db, embeddingdb, config_path)
            model_dir = config_yaml.get("models", {}).get("path", ".")

            try:
                # This will generate embeddings and add to broadcast queues if eligible
                predictor.predict_and_queue_feeds([feed_id], model_dir)
            except Exception as e:
                log.error(f"Failed to process feed {feed_id}: {e}")
                # Continue anyway - the item is already added

            return jsonify(
                {
                    "success": True,
                    "message": "Paper added successfully",
                    "feed_id": feed_id,
                }
            )
        else:
            return jsonify(
                {"success": False, "message": "Paper already exists in database"}
            ), 409

    except Exception as e:
        log.error(f"Error adding paper from scholarly database: {e}")
        return jsonify({"error": "Failed to add paper"}), 500

# Keep old endpoint for backward compatibility
@search_bp.route("/api/semantic-scholar/add", methods=["POST"])
@admin_required
def api_semantic_scholar_add():
    """Legacy endpoint - redirects to scholarly database add."""
    return api_scholarly_database_add()
