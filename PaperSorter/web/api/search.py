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
import markdown2
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from ...log import log
from ...embedding_database import EmbeddingDatabase
from ...feed_database import FeedDatabase
from ...feed_predictor import FeedPredictor
from ..auth.decorators import admin_required
from ..models.scholarly_article import ScholarlyArticleItem
from ...providers.factory import ScholarlyDatabaseFactory
from ...providers.openai_client import get_openai_client
from ..utils.database import get_user_model_id, save_search_query

search_bp = Blueprint("search", __name__)

# AI Assist system prompt - defines the role and behavior
AI_ASSIST_SYSTEM_PROMPT = """You are an expert research synthesizer and literature review specialist. Your role is to transform brief user inputs (keywords, fragmented concepts, or research questions) into high-density, narrative queries structured like a research paper's abstract or introduction.

Core Process:
1. Analyze the user's keywords to infer the scientific discipline, central problem, and potential research gaps
2. Generate two coherent paragraphs of academic prose:
   - Paragraph 1: Establish the foundational knowledge area and define the central research problem
   - Paragraph 2: Explore methodologies, applications, and future directions

Critical Output Rules:
- Write authentic scientific text, NOT meta-commentary about searching
- Maximize semantic density with technical terminology and synonyms
- Use formal, objective, third-person scientific tone
- Include NO citations, references, or quotations
- Do NOT use section headers like "Paragraph 1:" in the output
- Generate only the academic prose itself"""

# AI Assist user prompt template - provides instructions and examples
AI_ASSIST_USER_PROMPT = """Transform the following keywords into a two-paragraph academic text suitable for semantic search in scientific literature.

Example:
Input: graphene FET biosensor, non-invasive glucose monitoring, saliva diagnostics

Output:
The development of highly sensitive and selective biosensors for non-invasive molecular diagnostics remains a critical challenge in personalized medicine. Field-effect transistors (FETs) based on two-dimensional materials, particularly graphene, offer exceptional electronic properties, high surface-to-volume ratios, and biocompatibility, making them ideal candidates for next-generation sensing platforms. A key application area is the detection of biomarkers in accessible biofluids, such as saliva. The precise detection of glucose levels in saliva correlates with blood glucose concentrations, presenting a viable alternative to traditional invasive blood sampling methods for diabetes management.

Current research focuses on optimizing graphene FET (gFET) sensor architecture, including surface functionalization techniques to immobilize glucose oxidase enzymes or synthetic receptors effectively. Challenges include mitigating Debye screening effects in high ionic strength biofluids and ensuring long-term sensor stability and reproducibility. Investigation into multiplexed sensor arrays capable of simultaneously detecting glucose alongside other salivary biomarkers (e.g., lactate, cortisol) is essential for improving diagnostic accuracy. The integration of these sensors into point-of-care (POC) systems explores advancements in microfluidics and wireless data transmission for real-time health monitoring.

Now transform this input:
{query_text}"""


def assist_query(query_text, config):
    """Use LLM to transform keywords into academic-style text for better search."""
    try:
        # Load summarization API configuration (reuse for AI assist)
        api_config = config.get("summarization_api")
        if not isinstance(api_config, dict):
            log.warning("Summarization API not configured for AI assist")
            return None

        # Format the user prompt with the query text
        user_prompt = AI_ASSIST_USER_PROMPT.format(query_text=query_text)

        # Initialize OpenAI client
        client = get_openai_client("summarization_api", cfg=config, optional=True)
        if client is None:
            log.warning("Summarization API credentials missing for AI assist")
            return None

        # Generate assisted query
        response = client.chat.completions.create(
            model=api_config.get("model", "gpt-4"),
            messages=[
                {"role": "system", "content": AI_ASSIST_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=4000
        )

        assisted_text = response.choices[0].message.content.strip()

        # Basic cleanup - remove any accidental headers or markers
        lines = assisted_text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Skip lines that look like markdown headers or labels
            line_stripped = line.strip()
            if line_stripped and not (
                line_stripped.startswith('**') and line_stripped.endswith('**') or
                line_stripped.startswith('#') or
                line_stripped.endswith(':') and len(line_stripped.split()) <= 4 or
                line_stripped.lower().startswith('paragraph') or
                line_stripped.lower().startswith('output:')
            ):
                cleaned_lines.append(line)

        return '\n'.join(cleaned_lines).strip()

    except Exception as e:
        log.error(f"Error in AI assist: {e}")
        return None


@search_bp.route("/api/search", methods=["GET", "POST"])
@login_required
def api_search():
    """API endpoint to search papers by text similarity."""
    # Support both GET and POST methods
    if request.method == "POST":
        data = request.get_json()
        query = data.get("query", "").strip() if data else ""
        use_ai_assist = data.get("ai_assist", False) if data else False
        saved_search_name = data.get("saved_search", "") if data else ""
    else:
        query = request.args.get("q", "").strip()
        use_ai_assist = request.args.get("ai_assist", "").lower() == "true"
        saved_search_name = request.args.get("saved_search", "").strip()

    if not query:
        return jsonify({"error": "Query parameter is required"}), 400

    try:
        # Load configuration
        config_path = current_app.config["CONFIG_PATH"]
        from ...config import get_config
        config = get_config(config_path).raw
        db_manager = current_app.config["db_manager"]

        assisted_query = None
        search_query = query

        with db_manager.session() as session:
            connection = session.connection

            if saved_search_name and use_ai_assist:
                cursor = session.cursor()
                cursor.execute(
                    """
                    SELECT assisted_query FROM saved_searches
                    WHERE short_name = %s
                    LIMIT 1
                    """,
                    (saved_search_name,),
                )
                result = cursor.fetchone()
                cursor.close()

                if result and result[0]:
                    assisted_query = result[0]
                    search_query = assisted_query
                    log.info(
                        f"Using saved assisted query for search: {saved_search_name}"
                    )
                elif use_ai_assist:
                    assisted_query = assist_query(query, config)
                    if assisted_query:
                        search_query = assisted_query
                        log.info(
                            f"Generated new assisted query for saved search: {saved_search_name}"
                        )
            elif use_ai_assist:
                assisted_query = assist_query(query, config)
                if assisted_query:
                    search_query = assisted_query
                    log.info(
                        f"AI assist transformed query from '{query}' to assisted version"
                    )
                else:
                    log.warning("AI assist failed, falling back to original query")

            edb = EmbeddingDatabase(db_manager=db_manager)

            user_id = current_user.id
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
                    model_id = get_user_model_id(connection, current_user)
            else:
                model_id = get_user_model_id(connection, current_user)

            try:
                search_results = edb.search_by_text(
                    search_query,
                    limit=50,
                    user_id=user_id,
                    model_id=model_id,
                    channel_id=current_user.primary_channel_id,
                )
            finally:
                edb.close()

            feeds = [
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
                for feed in search_results
            ]

            try:
                short_name = save_search_query(connection, query, current_user.id, assisted_query)
            except Exception as exc:
                log.error(f"Failed to save search query: {exc}")
                short_name = None

            log_cursor = session.cursor()
            try:
                feed_id_to_log = search_results[0]["feed_id"] if search_results else None
                event_type = (
                    "web:ai-assisted-search"
                    if use_ai_assist and assisted_query
                    else "web:text-search"
                )
                log_content = (
                    json.dumps({"original": query, "assisted": assisted_query})
                    if assisted_query
                    else query
                )
                log_cursor.execute(
                    """
                    INSERT INTO events (event_type, user_id, feed_id, content)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (event_type, current_user.id, feed_id_to_log, log_content),
                )
            except Exception as exc:
                log.error(f"Failed to log text search event: {exc}")
            finally:
                log_cursor.close()

        response_data = {"feeds": feeds, "short_name": short_name}
        if assisted_query:
            response_data["assisted_query"] = assisted_query

        return jsonify(response_data)

    except Exception as e:
        log.error(f"Error searching papers: {e}")
        return jsonify({"error": str(e)}), 500


@search_bp.route("/api/search/shorten", methods=["POST"])
@login_required
def api_shorten_search():
    """Create or retrieve a shortened URL for a search query."""
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    query = data.get("query", "").strip()
    assisted_query = data.get("assisted_query", "").strip() if data.get("assisted_query") else None

    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        # Get database connection
        db_manager = current_app.config["db_manager"]

        with db_manager.session() as session:
            connection = session.connection
            short_name = save_search_query(connection, query, current_user.id, assisted_query)

        # Generate the full shortened URL
        base_url = request.host_url.rstrip('/')
        short_url = f"{base_url}/link/{short_name}"

        return jsonify({
            "short_name": short_name,
            "short_url": short_url
        })

    except Exception as e:
        log.error(f"Error creating shortened URL: {e}")
        return jsonify({"error": "Failed to create shortened URL"}), 500


@search_bp.route("/api/summarize", methods=["POST"])
@login_required
def api_summarize():
    """Generate a summary of articles using LLM."""
    try:
        data = request.get_json()
        feed_ids = data.get("feed_ids", [])

        if not feed_ids:
            return jsonify({"error": "No paper IDs provided"}), 400

        from ...config import get_config
        config = get_config().raw

        api_config = config.get("summarization_api")
        if not api_config:
            return jsonify({"error": "Summarization API not configured"}), 500

        db_manager = current_app.config["db_manager"]

        with db_manager.session() as session:
            cursor = session.cursor(dict_cursor=True)

            placeholders = ",".join(["%s"] * len(feed_ids))
            query = f"""
                SELECT id, title, author, COALESCE(journal, origin) AS origin, published, content, tldr
                FROM feeds
                WHERE id IN ({placeholders})
            """
            cursor.execute(query, feed_ids)
            articles = cursor.fetchall()
            cursor.close()

            if not articles:
                return jsonify({"error": "No articles found"}), 404

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

        if not summary_markdown:
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
        with db_manager.session() as session:
            cursor = session.cursor()
            try:
                if feed_ids:
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
            except Exception as exc:
                log.error(f"Failed to log AI summary event: {exc}")
            finally:
                cursor.close()

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
        from ...config import get_config
        config_yaml = get_config().raw

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

        db_manager = current_app.config["db_manager"]
        papers = []

        with db_manager.session() as session:
            cursor = session.cursor(dict_cursor=True)
            for article in articles:
                paper_dict = article.to_dict()
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
        # Load configuration and config path
        from ...config import get_config
        config_yaml = get_config().raw
        from flask import current_app
        config_path = current_app.config["CONFIG_PATH"]

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
            except (ValueError, TypeError):
                pass
        elif article_data.get("year"):
            try:
                pub_date = datetime(int(article_data["year"]), 1, 1)
            except (ValueError, TypeError):
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

        db_manager = current_app.config["db_manager"]
        db = None
        embeddingdb = None

        # Check if item already exists
        db = FeedDatabase(db_manager=db_manager)
        if article.unique_id not in db:
            # Add the item without starring
            feed_id = db.insert_feed_item(
                external_id=article.unique_id,
                title=article.title,
                content=article.abstract or (f"(tl;dr) {article.tldr}" if article.tldr else None),
                author=article.format_authors(),
                origin=provider.name,
                journal=article.venue or "Unknown",
                link=article.url,
                published=(article.publication_date.timestamp() if isinstance(article.publication_date, datetime) else None),
                tldr=None
            )
            db.commit()

            # Generate embeddings and predict preferences
            embeddingdb = EmbeddingDatabase(db_manager=db_manager)
            predictor = FeedPredictor(db, embeddingdb)
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
    finally:
        if embeddingdb is not None:
            embeddingdb.close()
        if db is not None:
            db.close()

# Keep old endpoint for backward compatibility
@search_bp.route("/api/semantic-scholar/add", methods=["POST"])
@admin_required
def api_semantic_scholar_add():
    """Legacy endpoint - redirects to scholarly database add."""
    return api_scholarly_database_add()
