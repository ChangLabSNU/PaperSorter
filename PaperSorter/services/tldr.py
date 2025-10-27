#!/usr/bin/env python3
"""Helpers to ensure TL;DR summaries exist for feed items."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping, Optional

from ..config import get_config
from ..feed_database import FeedDatabase
from ..log import log
from ..providers.openai_client import get_openai_client

SYSTEM_PROMPT = (
    "You create crisp single-sentence summaries of research articles for a lab newsletter."
)

USER_PROMPT_TEMPLATE = """Using the following article information, write exactly one sentence (no bullet points) that explains what they did and what is new about their work. Keep it under {word_limit} words, refer to the authors as "they" or "their", and avoid phrases like "the researchers" or "the authors". Maintain a neutral, non-promotional tone.

{formatted_article}
"""


def _should_use_gemini(api_config: Mapping[str, Any]) -> bool:
    base_url = api_config.get("api_url")
    if isinstance(base_url, str):
        return "generativelanguage.googleapis.com" in base_url
    return False


def _normalize_summary(text: str) -> str:
    """Collapse whitespace to make sure we return a single line."""
    return " ".join(text.split())


@dataclass
class TLDRGenerator:
    """Thin wrapper around the summarization API."""

    WORD_LIMIT: ClassVar[int] = 45
    client: Any
    model: str
    temperature: float
    max_tokens: Optional[int]
    use_gemini: bool

    @classmethod
    def from_config(cls, config: Optional[Mapping[str, Any]] = None) -> Optional["TLDRGenerator"]:
        cfg = config if config is not None else get_config().raw
        api_config = cfg.get("summarization_api") if isinstance(cfg, Mapping) else None
        if not isinstance(api_config, Mapping):
            log.debug("Summarization API configuration missing; skipping TL;DR generation")
            return None

        client = get_openai_client("summarization_api", cfg=cfg, optional=True)
        if client is None:
            log.debug("Summarization API client unavailable; skipping TL;DR generation")
            return None

        model = str(api_config.get("model", "gpt-4o-mini"))
        temperature = float(api_config.get("temperature", 0.2))
        max_tokens_value = api_config.get("max_tokens")
        max_tokens = int(max_tokens_value) if max_tokens_value is not None else None
        use_gemini = _should_use_gemini(api_config)

        return cls(
            client=client,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            use_gemini=use_gemini,
        )

    def generate(self, formatted_article: str) -> Optional[str]:
        """Generate a single-line summary for the provided formatted article."""
        if not formatted_article:
            return None

        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": USER_PROMPT_TEMPLATE.format(
                        formatted_article=formatted_article,
                        word_limit=self.WORD_LIMIT,
                    ),
                },
            ],
            "temperature": self.temperature,
        }

        if self.max_tokens is not None:
            if self.use_gemini:
                request_kwargs["extra_body"] = {"max_output_tokens": self.max_tokens}
            else:
                request_kwargs["max_tokens"] = self.max_tokens

        response = self.client.chat.completions.create(**request_kwargs)
        message = response.choices[0].message if response.choices else None
        summary = _extract_message_text(message)
        if not summary:
            log.warning("Received empty TL;DR response from summarization model")
            return None
        return _normalize_summary(summary)


def _extract_message_text(message: Any) -> str:
    """Normalize chat completion payloads into a single text string."""

    if message is None:
        return ""

    content = getattr(message, "content", message)

    if isinstance(content, str):
        return content.strip()

    collected: list[str] = []
    if isinstance(content, (list, tuple)):
        for part in content:
            if isinstance(part, str):
                collected.append(part)
            elif isinstance(part, Mapping):
                text_value = part.get("text")
                if isinstance(text_value, str):
                    collected.append(text_value)
            else:
                text_attr = getattr(part, "text", None)
                if isinstance(text_attr, str):
                    collected.append(text_attr)
    else:
        text_attr = getattr(content, "text", None)
        if isinstance(text_attr, str):
            collected.append(text_attr)

    combined = " ".join(segment.strip() for segment in collected if segment)
    return combined.strip()


def ensure_feed_tldr(
    feeddb: FeedDatabase,
    feed_id: int,
    *,
    config: Optional[Mapping[str, Any]] = None,
    generator: Optional[TLDRGenerator] = None,
    update_db: bool = True,
) -> Optional[str]:
    """Return an existing TL;DR or generate and persist a new one."""

    current = _fetch_existing_tldr(feeddb, feed_id)
    if current and _word_count(current) <= TLDRGenerator.WORD_LIMIT:
        return current

    formatted = feeddb.get_formatted_item(feed_id)
    if not formatted:
        log.debug("No formatted article available for TL;DR generation (id=%s)", feed_id)
        return None

    generator_obj = generator or TLDRGenerator.from_config(config)
    if generator_obj is None:
        return None

    try:
        summary = generator_obj.generate(formatted)
    except Exception as exc:  # pragma: no cover - defensive logging
        log.error("Failed to generate TL;DR for feed %s: %s", feed_id, exc)
        return None

    if summary and update_db:
        try:
            feeddb.update_tldr(feed_id, summary)
        except Exception as exc:  # pragma: no cover - defensive logging
            log.error("Failed to persist TL;DR for feed %s: %s", feed_id, exc)
        else:
            log.info("Generated TL;DR for feed %s", feed_id)

    return summary


def _word_count(text: str) -> int:
    if not text:
        return 0
    return len(text.split())


def _fetch_existing_tldr(feeddb: FeedDatabase, feed_id: int) -> Optional[str]:
    feeddb.cursor.execute("SELECT tldr FROM feeds WHERE id = %s", (feed_id,))
    row = feeddb.cursor.fetchone()
    if not row:
        return None
    value = row.get("tldr")
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None
