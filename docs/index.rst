.. PaperSorter documentation master file

========================================
PaperSorter Documentation
========================================

.. image:: https://img.shields.io/badge/python-3.9+-blue.svg
   :target: https://www.python.org/downloads/
   :alt: Python Version

.. image:: https://img.shields.io/badge/license-MIT-green.svg
   :target: https://opensource.org/licenses/MIT
   :alt: License

**PaperSorter** is an intelligent academic paper recommendation system that uses machine learning to help researchers stay up-to-date with the latest research in their fields. It automatically fetches papers from RSS feeds, generates embeddings, and uses XGBoost to predict which papers will be most relevant to you.

Key Features
============

- 🤖 **Smart Filtering**: Machine learning-based paper recommendations
- 📰 **Multi-Source Support**: RSS/Atom feeds, arXiv, and more
- 🔔 **Flexible Notifications**: Slack, Discord, and email newsletters
- 🎯 **Personalized Models**: Train custom models for different research areas
- 🌐 **Web Interface**: User-friendly labeling and management interface
- 🔍 **Semantic Search**: Find related papers using embedding similarity
- 📄 **Search from PDF**: Select text from PDFs to find similar papers (Paper Connect)

Quick Start
===========

.. code-block:: bash

   # Install PaperSorter
   pip install -e .

   # Configure your settings
   cp config.example.yml config.yml
   # Edit config.yml with your database and API credentials

   # Fetch papers and generate embeddings
   papersorter update

   # Train your first model (after labeling ~100 papers)
   papersorter train

   # Send notifications
   papersorter broadcast

Documentation Overview
======================

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   getting-started/index
   getting-started/installation
   getting-started/quickstart
   getting-started/first-model

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   user-guide/index
   user-guide/configuration
   user-guide/feed-sources
   user-guide/training-models
   user-guide/notifications
   user-guide/search-from-pdf
   user-guide/web-interface
   user-guide/workflows

.. toctree::
   :maxdepth: 2
   :caption: Administrator Guide

   admin-guide/index
   admin-guide/deployment
   admin-guide/database-setup
   admin-guide/backup-restore
   admin-guide/monitoring
   admin-guide/security
   admin-guide/troubleshooting

.. toctree::
   :maxdepth: 2
   :caption: CLI Reference

   cli-reference/index
   cli-reference/commands
   cli-reference/examples

.. toctree::
   :maxdepth: 2
   :caption: API Documentation

   api/index
   api/modules
   api/database
   api/providers
   api/notifications
   api/web

.. toctree::
   :maxdepth: 2
   :caption: Development

   development/index
   development/contributing
   development/architecture
   development/testing
   development/plugins
   development/release-process

.. toctree::
   :maxdepth: 2
   :caption: Tutorials

   tutorials/index
   tutorials/gmail-setup
   tutorials/slack-integration
   tutorials/custom-embeddings
   tutorials/multi-model

.. toctree::
   :maxdepth: 2
   :caption: Reference

   reference/index
   reference/configuration-reference
   reference/database-schema
   reference/environment-variables
   reference/glossary

.. toctree::
   :maxdepth: 1
   :caption: About

   changelog
   license

Indices and Tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

Need Help?
==========

- 📖 Check the documentation guides
- 🐛 Report issues on `GitHub <https://github.com/ChangLabSNU/papersorter/issues>`_
- 💬 Join our community discussions

License
=======

PaperSorter is released under the MIT License. See the LICENSE file for details.