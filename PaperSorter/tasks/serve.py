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

import click
from ..log import log, initialize_logging
from ..web import create_app


@click.option(
    "--config", default="./config.yml", help="Database configuration file."
)
@click.option("--host", default="0.0.0.0", help="Host to bind to.")
@click.option("--port", default=5001, help="Port to bind to.")
@click.option("--debug", is_flag=True, help="Enable debug mode.")
@click.option("--log-file", default=None, help="Log file.")
@click.option("-q", "--quiet", is_flag=True, help="Suppress log output.")
def main(config, host, port, debug, log_file, quiet):
    """Serve web interface for article labeling and other tasks."""
    initialize_logging(task="serve", logfile=log_file, quiet=quiet)

    log.info(f"Starting web server on {host}:{port}")
    log.info(f"OAuth redirect URIs to configure:")
    log.info(f"  - http://localhost:{port}/callback (for local testing)")
    log.info(f"  - http://{host}:{port}/callback (if using {host})")
    log.info(f"  - Your production URL/callback (if applicable)")

    app = create_app(config)

    # Run the Flask app
    app.run(host=host, port=port, debug=debug)