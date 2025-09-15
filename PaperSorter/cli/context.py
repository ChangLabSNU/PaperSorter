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

"""Command context management for PaperSorter CLI."""

from typing import Optional
from ..config import get_config


class CommandContext:
    """Context object passed to all commands."""

    def __init__(self, config_path: str, log_file: Optional[str] = None, quiet: bool = False):
        """
        Initialize command context.

        Args:
            config_path: Path to configuration file
            log_file: Optional log file path
            quiet: Whether to suppress output
        """
        self.config_path = config_path
        self.log_file = log_file
        self.quiet = quiet
        self._config = None
        self._db = None
        self._embedding_db = None

    @property
    def config(self) -> dict:
        """Load and cache configuration."""
        if self._config is None:
            # Centralized configuration access
            self._config = get_config(self.config_path).raw
        return self._config

    @property
    def db(self):
        """Get database connection (lazy loading)."""
        if self._db is None:
            from ..feed_database import FeedDatabase
            from ..config import get_config
            get_config(self.config_path)
            self._db = FeedDatabase()
        return self._db

    @property
    def embedding_db(self):
        """Get embedding database connection (lazy loading)."""
        if self._embedding_db is None:
            from ..embedding_database import EmbeddingDatabase
            from ..config import get_config
            get_config(self.config_path)
            self._embedding_db = EmbeddingDatabase()
        return self._embedding_db

    def cleanup(self):
        """Clean up resources."""
        if self._db is not None:
            self._db.close()
        if self._embedding_db is not None:
            self._embedding_db.close()
