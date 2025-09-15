#!/usr/bin/env python3

"""Centralized configuration loader for PaperSorter.

This module provides a lightweight, process-wide configuration singleton
loaded from YAML. Prefer importing and calling `get_config()` from any
module that needs configuration values.

Load precedence:
- Explicit path provided to `get_config(path)` / `reload_config(path)`
- Environment variables: `PAPERSORTER_CONFIG` or `PAPER_SORTER_CONFIG`
- Default path: `./config.yml`

Usage:
    from PaperSorter.config import get_config
    cfg = get_config()
    db_cfg = cfg.raw.get('db', {})
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


_LOCK = threading.RLock()
_CONFIG: Optional["Config"] = None
_CONFIG_PATH: Optional[str] = None


@dataclass
class Config:
    """Simple configuration holder with convenience accessors."""

    raw: Dict[str, Any]

    def get(self, path: str, default: Any = None) -> Any:
        """Get a nested value using dotted path notation.

        Example: cfg.get('web.port', 5001)
        """
        cur: Any = self.raw
        for part in path.split('.'):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur


def _resolve_config_path(preferred: Optional[str]) -> str:
    if preferred:
        return str(preferred)

    env = os.environ.get("PAPERSORTER_CONFIG") or os.environ.get("PAPER_SORTER_CONFIG")
    if env:
        return env

    return "./config.yml"


def _load_yaml_config(path: str, explicit: bool) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        if explicit:
            raise FileNotFoundError(f"Configuration file not found: {path}")
        # Fallback to empty config when using defaults
        return {}

    with p.open("r") as f:
        data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError("Configuration root must be a mapping (YAML dict)")
        return data


def _load_config(path: Optional[str], refresh: bool = False) -> Config:
    global _CONFIG, _CONFIG_PATH
    with _LOCK:
        if _CONFIG is not None and not refresh:
            return _CONFIG

        resolved = _resolve_config_path(path)
        # Treat as explicit if caller supplied a path or env var is set
        explicit = path is not None or os.environ.get("PAPERSORTER_CONFIG") is not None or os.environ.get("PAPER_SORTER_CONFIG") is not None
        raw = _load_yaml_config(resolved, explicit=explicit)

        _CONFIG = Config(raw=raw)
        _CONFIG_PATH = resolved
        return _CONFIG


def get_config(path: Optional[str] = None) -> Config:
    """Return the process-wide Config instance, loading it if necessary.

    The first explicit path provided will be remembered for subsequent calls.
    """
    if path is not None:
        return _load_config(path, refresh=False)
    return _load_config(None, refresh=False)


def reload_config(path: Optional[str] = None) -> Config:
    """Force reload the configuration from the given path or the last one used."""
    # If no path provided, use the last resolved path
    target = path if path is not None else _CONFIG_PATH
    return _load_config(target, refresh=True)


def configured() -> bool:
    """Return True if a configuration has been loaded."""
    return _CONFIG is not None


def set_config_for_testing(cfg: Config) -> None:
    """Override the global configuration (use in tests)."""
    global _CONFIG
    with _LOCK:
        _CONFIG = cfg

