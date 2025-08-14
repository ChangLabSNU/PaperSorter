#!/usr/bin/env python3
"""
WSGI entry point for PaperSorter web application.
This file is used by uWSGI to load the Flask application.
"""

from PaperSorter.web.app import create_app

# Create the Flask application instance
app = create_app("/app/config.yml")
