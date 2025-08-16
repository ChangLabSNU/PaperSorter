=================
API Documentation
=================

This section provides comprehensive documentation for PaperSorter's internal APIs, modules, and extension points.

Whether you're developing custom integrations, contributing to the project, or building extensions, this reference will help you understand PaperSorter's architecture and interfaces.

Architecture Overview
=====================

PaperSorter is organized into several key components:

- **Core Modules**: Database interfaces, embedding generation, and ML models
- **Feed Providers**: Pluggable RSS/Atom feed processors
- **Web Framework**: Flask-based REST API and user interface
- **Notification System**: Multi-channel broadcast capabilities
- **CLI Tasks**: Command-line interface implementations

.. toctree::
   :maxdepth: 2

   modules
   database
   providers
   notifications
   web

Key Interfaces
==============

Database Layer
--------------

The database layer provides unified access to PostgreSQL with pgvector support:

- **FeedDatabase**: Article metadata and user preferences
- **EmbeddingDatabase**: Vector storage and similarity search
- **Schema Management**: Migrations and table definitions

Provider System
---------------

Feed providers implement a common interface for content ingestion:

- **BaseProvider**: Abstract interface for all feed sources
- **RSSProvider**: RSS/Atom feed implementation
- **Custom Providers**: Extension points for new content sources

Web API
-------

RESTful endpoints organized by functional domain:

- **Feeds API**: Article management and labeling
- **Search API**: Text and semantic search capabilities
- **Settings API**: Administrative configuration
- **User API**: Preferences and personalization

Extension Points
================

Custom Feed Providers
----------------------

Implement ``BaseProvider`` to add new content sources:

.. code-block:: python

   from PaperSorter.providers.base import BaseProvider
   
   class CustomProvider(BaseProvider):
       def fetch_articles(self):
           # Implementation here
           pass

Custom Notification Channels
-----------------------------

Extend the notification system for new delivery methods:

.. code-block:: python

   from PaperSorter.notifications import BaseNotifier
   
   class CustomNotifier(BaseNotifier):
       def send(self, articles):
           # Implementation here
           pass

API Conventions
===============

- All APIs use consistent error handling and response formats
- Database operations support transaction management
- Configuration is injected via dependency injection patterns
- Logging follows structured format for operational monitoring

Related Resources
=================

- :doc:`../development/architecture` - High-level system design
- :doc:`../development/contributing` - Development guidelines
- :doc:`../reference/database-schema` - Complete schema reference