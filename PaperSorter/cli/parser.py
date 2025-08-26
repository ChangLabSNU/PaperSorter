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

"""Main parser creation for PaperSorter CLI."""

import argparse
from .base import registry
from .context import CommandContext
from ..__version__ import __version__


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser."""
    parser = argparse.ArgumentParser(
        prog='papersorter',
        description='Intelligent academic paper recommendation system',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False  # We'll add custom help
    )

    # Add help manually to support both -h and --help
    parser.add_argument(
        '-h', '--help',
        action='help',
        help='Show this help message and exit'
    )

    # Add version option
    parser.add_argument(
        '--version',
        action='version',
        version=f'PaperSorter, version {__version__}'
    )

    return parser


def execute_command(args: argparse.Namespace) -> int:
    """Execute the parsed command."""
    if not hasattr(args, 'command_handler'):
        return 1

    # Create context
    context = CommandContext(
        config_path=args.config,
        log_file=getattr(args, 'log_file', None),
        quiet=getattr(args, 'quiet', False)
    )

    try:
        # Execute the command
        return args.command_handler.handle(args, context)
    finally:
        # Clean up resources
        context.cleanup()


def main(argv=None):
    """Main entry point for the CLI."""
    parser = create_parser()

    # Create subparsers for all registered commands
    registry.create_subparsers(parser)

    # Parse arguments
    args = parser.parse_args(argv)

    # If no command specified, show help
    if not hasattr(args, 'command') or args.command is None:
        parser.print_help()
        return 0

    # Execute the command
    return execute_command(args)
