#!/usr/bin/env python
"""WSGI entry point for gunicorn with Docker."""
from PaperSorter.web.app import create_app

# Create the application with the config path
app = create_app("/app/config.yml")