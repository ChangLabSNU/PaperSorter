#!/usr/bin/env python3
"""Shared helpers for loading and preparing article data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..log import log


@dataclass
class ArticleRecord:
    """Normalized representation of a feed article."""

    id: int
    title: Optional[str]
    author: Optional[str]
    origin: Optional[str]
    published: Optional[Any]
    content: Optional[str]
    tldr: Optional[str]
    link: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert the record to a dictionary preserving optional fields."""

        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "origin": self.origin,
            "published": self.published,
            "content": self.content,
            "tldr": self.tldr,
            "link": self.link,
        }


def _normalize_articles(raw_rows: Iterable[Dict[str, Any]]) -> Dict[int, ArticleRecord]:
    articles: Dict[int, ArticleRecord] = {}
    for row in raw_rows:
        try:
            record = ArticleRecord(
                id=row["id"],
                title=row.get("title"),
                author=row.get("author"),
                origin=row.get("origin"),
                published=row.get("published"),
                content=row.get("content"),
                tldr=row.get("tldr"),
                link=row.get("link"),
            )
            articles[record.id] = record
        except Exception as exc:  # pragma: no cover - guard against malformed rows
            log.error(f"Failed to normalize article row {row}: {exc}")
    return articles


def fetch_articles(session, feed_ids: Sequence[int]) -> List[ArticleRecord]:
    """Load articles from the database in the provided order.

    Args:
        session: Active :class:`~PaperSorter.db.manager.DatabaseSession`.
        feed_ids: Sequence of feed identifiers to retrieve.

    Returns:
        Articles ordered to match ``feed_ids``.
    """

    if not feed_ids:
        return []

    cursor = session.cursor(dict_cursor=True)
    try:
        cursor.execute(
            """
            SELECT id, title, author, COALESCE(journal, origin) AS origin, published, content, tldr, link
            FROM feeds
            WHERE id = ANY(%s)
            """,
            (list(feed_ids),),
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()

    articles_by_id = _normalize_articles(rows)
    ordered: List[ArticleRecord] = [
        articles_by_id[fid]
        for fid in feed_ids
        if fid in articles_by_id
    ]

    if len(ordered) != len(feed_ids):
        missing = {fid for fid in feed_ids if fid not in articles_by_id}
        if missing:
            log.warning(f"Missing articles for feed IDs: {sorted(missing)}")

    return ordered


def summarization_snippets(articles: Sequence[ArticleRecord]) -> List[str]:
    """Prepare markdown-friendly snippets for article summarization prompts."""

    formatted: List[str] = []
    for index, article in enumerate(articles, start=1):
        parts: List[str] = []

        author = article.author
        # Derive reference label
        first_author = "Unknown"
        if author:
            first_author_tokens = author.split(",")[0].strip().split()
            if first_author_tokens:
                first_author = first_author_tokens[-1]
            parts.append(f"Authors: {author}")

        published = article.published
        year = "n.d."
        if published is not None:
            if hasattr(published, "year"):
                year = str(getattr(published, "year"))
            elif hasattr(published, "isoformat"):
                iso = published.isoformat()
                year = iso[:4]
                parts.append(f"Published: {iso}")
            else:
                published_str = str(published)
                if len(published_str) >= 4:
                    year = published_str[:4]
                parts.append(f"Published: {published_str}")

        title = article.title
        if title:
            parts.append(f"Title: {title}")

        origin = article.origin
        if origin:
            parts.append(f"Source: {origin}")

        abstract = article.tldr or (article.content or "")
        if abstract:
            abstract_str = str(abstract)
            if len(abstract_str) > 500:
                abstract_str = abstract_str[:497] + "..."
            parts.append(f"Abstract: {abstract_str}")

        if not parts:
            log.debug(f"Article {article.id} skipped due to missing content")
            continue

        label = f"{first_author} {year}"
        formatted.append(f"[{label}]\n" + "\n".join(parts))

    return formatted


def poster_payload(articles: Sequence[ArticleRecord]) -> List[Dict[str, Any]]:
    """Format article data for infographic poster generation."""

    payload: List[Dict[str, Any]] = []
    for index, article in enumerate(articles):
        try:
            published = article.published
            if published and hasattr(published, "isoformat"):
                published_str: Optional[str] = published.isoformat()
            else:
                published_str = str(published) if published is not None else ""

            abstract_source = article.tldr or article.content or ""
            abstract = abstract_source[:500] + "..." if abstract_source and len(abstract_source) > 500 else abstract_source

            payload.append(
                {
                    "title": article.title or "",
                    "authors": article.author or "",
                    "source": article.origin or "",
                    "published": published_str,
                    "abstract": abstract,
                    "link": article.link or "",
                }
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            log.error(f"Failed to format article {article.id} for poster: {exc}")
    return payload

