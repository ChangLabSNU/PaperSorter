=================
Reference
=================

Comprehensive technical reference documentation for PaperSorter. This section provides detailed specifications, schemas, and reference materials for advanced users and developers.

Use this section when you need precise technical details about configuration options, database structures, environment variables, or terminology.

Contents
========

Technical Specifications
------------------------

- **Configuration Reference**: Complete list of all configuration options with types, defaults, and descriptions
- **Database Schema**: Full PostgreSQL schema including tables, indexes, and relationships
- **Environment Variables**: All supported environment variables and their effects
- **Glossary**: Definitions of terms and concepts used throughout PaperSorter

.. toctree::
   :maxdepth: 2

   configuration-reference
   database-schema
   environment-variables
   glossary

Quick Reference
===============

Configuration Files
-------------------

Primary configuration is stored in ``config.yml`` with these main sections:

- ``db``: Database connection settings
- ``web``: Web interface configuration
- ``oauth``: Authentication provider settings
- ``embedding_api``: Embedding generation API
- ``summarization_api``: Text summarization API
- ``scholarly_database``: Academic database integration

Database Tables
---------------

Core tables in the PostgreSQL schema:

- ``feeds``: Article metadata and content
- ``embeddings``: Vector embeddings using pgvector
- ``preferences``: User ratings and labels
- ``predicted_preferences``: ML model predictions
- ``broadcasts``: Notification queue and history
- ``users``: User accounts and settings
- ``channels``: Notification channel configuration

API Endpoints
-------------

Web API organization:

- ``/api/feeds/``: Article management operations
- ``/api/search/``: Search and discovery features
- ``/api/settings/``: Administrative configuration
- ``/api/user/``: User preferences and data

CLI Commands
------------

Main command categories:

- ``papersorter update``: Content ingestion and processing
- ``papersorter train``: Model training and evaluation
- ``papersorter broadcast``: Notification delivery
- ``papersorter serve``: Web interface server

Version Compatibility
=====================

This reference documentation applies to:

- **PaperSorter**: Version 1.0+
- **Python**: 3.9+
- **PostgreSQL**: 12+ with pgvector extension
- **Dependencies**: See ``setup.py`` for specific version requirements

Standards and Conventions
=========================

Configuration Format
--------------------

- **YAML**: Human-readable configuration files
- **Environment Variables**: Override any configuration value
- **Validation**: Schema validation with helpful error messages

Database Design
---------------

- **PostgreSQL**: ACID compliance and advanced features
- **pgvector**: Efficient vector similarity search
- **Migrations**: Version-controlled schema changes

API Design
----------

- **REST**: Standard HTTP methods and status codes
- **JSON**: Consistent request/response format
- **Authentication**: OAuth 2.0 with multiple providers

Related Sections
================

- :doc:`../api/index` - API implementation details
- :doc:`../development/architecture` - System design principles
- :doc:`../admin-guide/database-setup` - Database administration