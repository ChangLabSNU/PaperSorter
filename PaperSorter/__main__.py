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

import sys
import importlib
from .tasks import __all__ as alltasks
from .cli.parser import main as cli_main

def main():
    """Main entry point for PaperSorter CLI."""

    # Import and register all commands

    for task in alltasks:
        # Import the task module (this triggers registration for migrated commands)
        try:
            importlib.import_module(f".tasks.{task}", package="PaperSorter")
        except ImportError as e:
            print(f"Warning: Could not import task {task}: {e}", file=sys.stderr)
            continue

    # Run the CLI
    return cli_main()

if __name__ == "__main__":
    sys.exit(main())

# Export main for use as console script
__all__ = ['main']
