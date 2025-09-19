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

"""Poster generation background jobs."""

import json
import time
from ...config import get_config
from ...db import DatabaseManager
from ...log import log
import os
from datetime import datetime
from ...providers.openai_client import get_openai_client


def process_poster_job(app, job_id, feed_ids, config_path):
    """Process poster generation in background thread."""
    try:
        config = get_config(config_path).raw

        api_config = config.get("summarization_api")
        if not isinstance(api_config, dict):
            log.error("Summarization API not configured in config file")
            with app.poster_jobs_lock:
                app.poster_jobs[job_id]["status"] = "error"
                app.poster_jobs[job_id]["error"] = "Summarization API not configured"
            return

        # Get database connection function from app context
        with app.app_context():
            db_manager = app.config.get("db_manager")
            owns_manager = False
            if db_manager is None:
                db_manager = DatabaseManager.from_config(
                    app.db_config,
                    application_name="papersorter-web-poster",
                )
                owns_manager = True

            articles = []

            try:
                with db_manager.session() as session:
                    cursor = session.cursor(dict_cursor=True)

                    # Get articles with content/tldr
                    placeholders = ",".join(["%s"] * len(feed_ids))
                    query = f"""
                        SELECT id, title, author, COALESCE(journal, origin) AS origin, published, content, tldr, link
                        FROM feeds
                        WHERE id IN ({placeholders})
                    """
                    cursor.execute(query, feed_ids)
                    articles = cursor.fetchall()
            finally:
                if owns_manager:
                    db_manager.close()

            if not articles:
                log.error("No articles found in database for given IDs")
                with app.poster_jobs_lock:
                    app.poster_jobs[job_id]["status"] = "error"
                    app.poster_jobs[job_id]["error"] = "No articles found"
                return

            # Format articles for infographic
            formatted_articles = []
            for i, article in enumerate(articles):
                try:
                    formatted_article = {
                        "title": article.get("title", ""),
                        "authors": article.get("author", ""),
                        "source": article.get("origin", ""),
                        "published": article.get("published", "").isoformat()
                        if article.get("published")
                        and hasattr(article.get("published"), "isoformat")
                        else str(article.get("published", "")),
                        "abstract": article.get("tldr", "")
                        or (
                            article.get("content", "")[:500] + "..."
                            if article.get("content")
                            else ""
                        ),
                        "link": article.get("link", ""),
                    }
                    formatted_articles.append(formatted_article)
                except Exception as e:
                    log.error(
                        f"Error formatting article {i} (id={article.get('id')}): {e}"
                    )
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
            client = get_openai_client("summarization_api", cfg=config, optional=True)
            if client is None:
                log.error("Summarization API credentials missing for poster generation")
                with app.poster_jobs_lock:
                    app.poster_jobs[job_id]["status"] = "error"
                    app.poster_jobs[job_id]["error"] = "Summarization API credentials missing"
                return

            # Generate infographic
            start_time = time.time()

            try:
                response = client.chat.completions.create(
                    model=api_config.get("model", "gpt-4o-mini"),
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert at creating beautiful, informative scientific infographics using React and modern web technologies. Always output complete, working HTML code.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.8,
                    max_tokens=128000,
                    timeout=300.0,  # 5 minutes timeout
                )

                elapsed_time = time.time() - start_time

            except Exception as api_error:
                elapsed_time = time.time() - start_time
                log.error(
                    f"API call failed after {elapsed_time:.2f} seconds: {api_error}"
                )
                with app.poster_jobs_lock:
                    app.poster_jobs[job_id]["status"] = "error"
                    app.poster_jobs[job_id]["error"] = (
                        f"API call failed: {str(api_error)}"
                    )
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
                app.poster_jobs[job_id]["status"] = "completed"
                app.poster_jobs[job_id]["result"] = poster_html
                user_id = app.poster_jobs[job_id]["user_id"]

            # Save poster HTML to file if directory is configured
            ai_poster_dir = config.get("storage", {}).get("ai_poster_dir")
            if ai_poster_dir:
                try:
                    # Create directory if it doesn't exist
                    os.makedirs(ai_poster_dir, exist_ok=True)

                    # Generate filename with user_id and timestamp
                    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    filename = f"{user_id}-{timestamp}.html"
                    filepath = os.path.join(ai_poster_dir, filename)

                    # Save the poster HTML
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(poster_html)
                except Exception as e:
                    log.error(f"Failed to save poster to file: {e}")
                    # Don't fail the job if file saving fails
            else:
                log.debug("AI poster directory not configured, skipping file save")

            # Log the event to database
            db_manager = app.config.get("db_manager")
            owns_manager = False
            if db_manager is None:
                db_manager = DatabaseManager.from_config(
                    app.db_config,
                    application_name="papersorter-web-poster",
                )
                owns_manager = True

            try:
                with db_manager.session() as session:
                    cursor = session.cursor()
                    # Log AI poster generation event - store all feed IDs in content field
                    if feed_ids:
                        cursor.execute(
                            """
                            INSERT INTO events (event_type, user_id, feed_id, content)
                            VALUES (%s, %s, %s, %s)
                        """,
                            (
                                "web:ai-poster-infographic",
                                user_id,
                                feed_ids[0],
                                json.dumps(feed_ids),
                            ),
                        )
            except Exception as e:
                log.error(f"Failed to log AI poster event: {e}")
            finally:
                if owns_manager:
                    db_manager.close()

    except Exception as e:
        import traceback

        log.error(
            f"Poster generation job {job_id} failed: {type(e).__name__}: {str(e)}"
        )
        log.error(f"Traceback:\n{traceback.format_exc()}")

        # Store error
        with app.poster_jobs_lock:
            app.poster_jobs[job_id]["status"] = "error"
            app.poster_jobs[job_id]["error"] = str(e)
