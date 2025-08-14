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
import threading
import time
from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from ..log import log, initialize_logging
from ..web import create_app


def print_server_box(port):
    """Print a beautiful boxed display of the server URL using Rich."""
    console = Console()
    url = f"http://localhost:{port}"
    
    # Create a beautiful panel with gradient-like styling
    title = Text("🚀 PaperSorter Web Interface", style="bold blue")
    url_text = Text(url, style="bold green")
    instruction = Text("Press Ctrl+C to stop server", style="dim italic")
    
    # Create a table for better layout
    table = Table(show_header=False, box=box.ROUNDED, show_edge=False)
    table.add_column("Content", justify="center")
    table.add_row(title)
    table.add_row(url_text)
    table.add_row(instruction)
    
    # Create the panel with the table
    panel = Panel(
        Align.center(table),
        border_style="bright_blue",
        padding=(1, 2),
        title="[bold cyan]Server Ready[/bold cyan]",
        title_align="center"
    )
    
    console.print()
    console.print(panel)
    console.print()


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

    app = create_app(config)

    # Print the server box after a short delay to ensure Flask has started
    def print_box_delayed():
        time.sleep(0.5)  # Small delay to ensure Flask output appears first
        print_server_box(port)
    
    # Start the box printing in a separate thread
    box_thread = threading.Thread(target=print_box_delayed, daemon=True)
    box_thread.start()

    # Run the Flask app with suppressed output if not in debug mode
    if debug:
        app.run(host=host, port=port, debug=debug)
    else:
        # Suppress Flask's default output by setting use_reloader=False
        app.run(host=host, port=port, debug=False, use_reloader=False)
