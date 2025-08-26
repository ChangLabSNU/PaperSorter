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

"""Web server task for PaperSorter."""

from ..log import log, initialize_logging
from ..web import create_app
from ..cli.base import BaseCommand, registry
import argparse


class ServeCommand(BaseCommand):
    """Serve web interface for article labeling."""

    name = 'serve'
    help = 'Serve web interface for article labeling and other tasks'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add serve-specific arguments."""
        parser.add_argument(
            '--host',
            default='0.0.0.0',
            help='Host to bind to'
        )
        parser.add_argument(
            '--port',
            type=int,
            default=5001,
            help='Port to bind to'
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Enable debug mode'
        )
        parser.add_argument(
            '--skip-authentication',
            help='Skip OAuth authentication and auto-login as specified admin user (DEVELOPMENT ONLY)'
        )

    def handle(self, args: argparse.Namespace, context) -> int:
        """Execute the serve command."""
        initialize_logging('serve', args.log_file, args.quiet)
        try:
            main(
                config=args.config,
                host=args.host,
                port=args.port,
                debug=args.debug,
                log_file=args.log_file,
                quiet=args.quiet,
                skip_authentication=args.skip_authentication
            )
            return 0
        except Exception as e:
            log.error(f"Serve failed: {e}")
            return 1

# Register the command
registry.register(ServeCommand)


def main(config, host, port, debug, log_file, quiet, skip_authentication):
    """Serve web interface for article labeling and other tasks."""
    initialize_logging(task="serve", logfile=log_file, quiet=quiet)

    if skip_authentication:
        log.warning(
            f"⚠️  AUTHENTICATION BYPASS ENABLED for user '{skip_authentication}' - DEVELOPMENT USE ONLY!"
        )

    log.info(f"Starting web server on {host}:{port}")

    app = create_app(config, skip_authentication=skip_authentication)

    # Run the Flask app
    app.run(host=host, port=port, debug=debug)
