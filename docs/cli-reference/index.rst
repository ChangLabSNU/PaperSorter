=============
CLI Reference
=============

PaperSorter provides a comprehensive command-line interface for all system operations. This reference documents every command, option, and usage pattern.

The CLI is built using Click and follows standard Unix conventions for options and arguments. All commands support ``--help`` for detailed usage information.

Command Overview
================

Core Operations
---------------

- **update**: Fetch new articles, generate embeddings, and score papers
- **train**: Train or retrain machine learning models on labeled data
- **broadcast**: Send notifications and recommendations to configured channels
- **serve**: Start the web interface for interactive paper management

The typical workflow involves running these commands in sequence, often automated via cron jobs for regular operation.

.. toctree::
   :maxdepth: 2

   commands
   examples

Global Options
==============

All commands support these common options:

``--config PATH``
  Configuration file location (default: ./config.yml)

``--log-file PATH``
  Write logs to specified file instead of stdout

``-q, --quiet``
  Suppress non-error output

``--help``
  Show command-specific help and exit

Environment Variables
=====================

Configuration can also be provided via environment variables:

- ``PAPERSORTER_CONFIG``: Path to configuration file
- ``PAPERSORTER_LOG_LEVEL``: Logging level (DEBUG, INFO, WARNING, ERROR)
- ``PAPERSORTER_LOG_FILE``: Log file path

Exit Codes
==========

PaperSorter follows standard Unix exit code conventions:

- ``0``: Success
- ``1``: General error
- ``2``: Command-line usage error
- ``3``: Configuration error
- ``4``: Database error

Examples
========

Common usage patterns:

.. code-block:: bash

   # Daily automation (typical cron setup)
   papersorter update --batch-size 50
   papersorter train --rounds 100
   papersorter broadcast --limit 10

   # Development and testing
   papersorter serve --debug --port 5000
   papersorter update --limit-sources 5 --check-interval-hours 1

Related Documentation
=====================

- :doc:`../admin-guide/deployment` - Production automation setup