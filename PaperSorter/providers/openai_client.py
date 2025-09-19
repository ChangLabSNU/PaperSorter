#!/usr/bin/env python3
"""Centralized OpenAI client management.

This module exposes helper functions for retrieving shared OpenAI clients
configured via the main PaperSorter configuration. Clients are cached per
configuration section so that callers reuse authenticated sessions instead of
recreating them throughout the codebase.
"""

from __future__ import annotations

from threading import RLock
from typing import Any, Dict, Mapping, Optional, Tuple

from openai import OpenAI

from ..config import get_config

_DEFAULT_BASE_URL = "https://api.openai.com/v1"

# Cache initialized clients keyed by (section, api_key, base_url)
_CLIENT_CACHE: Dict[Tuple[str, str, str], OpenAI] = {}
_CACHE_LOCK = RLock()


def _normalize_base_url(url: Optional[str]) -> str:
    if not url:
        return _DEFAULT_BASE_URL
    return url.rstrip("/") or _DEFAULT_BASE_URL


def get_openai_client(
    section: str,
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    optional: bool = False,
) -> Optional[OpenAI]:
    """Return a shared OpenAI client for the given configuration section.

    Args:
        section: Name of the configuration section (e.g., ``"summarization_api"``).
        cfg: Optional configuration mapping overriding the global config.
        optional: When ``True``, return ``None`` instead of raising if the
            section is missing or lacks credentials.

    Raises:
        ValueError: If the configuration section or API key is missing and
            ``optional`` is ``False``.

    Returns:
        An initialized :class:`~openai.OpenAI` client or ``None`` when optional.
    """

    config_source: Optional[Mapping[str, Any]] = cfg if cfg is not None else get_config().raw
    api_section = config_source.get(section) if config_source else None

    if not isinstance(api_section, Mapping):
        if optional:
            return None
        raise ValueError(f"Configuration section '{section}' is missing or invalid")

    api_config: Mapping[str, Any] = api_section

    api_key = api_config.get("api_key")
    if not isinstance(api_key, str) or not api_key.strip():
        if optional:
            return None
        raise ValueError(f"Configuration section '{section}' is missing 'api_key'")

    base_url_value = api_config.get("api_url")
    base_url = _normalize_base_url(base_url_value if isinstance(base_url_value, str) else None)

    cache_key = (section, api_key, base_url)

    with _CACHE_LOCK:
        client = _CLIENT_CACHE.get(cache_key)
        if client is None:
            client = OpenAI(api_key=api_key, base_url=base_url)
            _CLIENT_CACHE[cache_key] = client

    return client


def reset_openai_client_cache() -> None:
    """Clear the cached OpenAI clients (useful in tests)."""

    with _CACHE_LOCK:
        _CLIENT_CACHE.clear()
