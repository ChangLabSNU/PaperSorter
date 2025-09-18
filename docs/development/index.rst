=================
Development Guide
=================

Welcome to PaperSorter development! This guide helps contributors, maintainers, and developers who want to extend or modify PaperSorter.

PaperSorter is built with extensibility in mind, featuring modular architecture that allows for custom feed providers, notification channels, and machine learning models.

Getting Started
===============

Development Environment
-----------------------

- Python 3.9+ with virtual environment
- PostgreSQL with pgvector extension
- Code editor with Python support
- Git for version control

Development Workflow
--------------------

1. Fork and clone the repository
2. Set up development environment
3. Create feature branch
4. Write tests and documentation
5. Submit pull request

.. toctree::
   :maxdepth: 2

   contributing
   architecture
   database
   testing
   plugins
   release-process

Architecture Principles
=======================

Modularity
----------

PaperSorter is designed as a collection of loosely coupled modules:

- **Separation of concerns**: Each module has a single responsibility
- **Dependency injection**: Configuration and dependencies are injected
- **Plugin architecture**: New providers and notifiers can be added easily

Extensibility
-------------

Key extension points:

- **Feed Providers**: Add support for new content sources
- **Notification Channels**: Implement custom delivery methods
- **ML Models**: Experiment with different recommendation algorithms
- **Web Interface**: Add new API endpoints and UI components

Code Quality
============

Standards
---------

- **PEP 8**: Python code style guidelines
- **Type Hints**: All public APIs include type annotations
- **Documentation**: Comprehensive docstrings and user guides
- **Testing**: Unit tests with good coverage

Tools
-----

- **Black**: Code formatting
- **Flake8**: Linting and style checking
- **MyPy**: Static type checking
- **Pytest**: Testing framework

Development Commands
====================

.. code-block:: bash

   # Setup development environment
   python -m venv venv
   source venv/bin/activate
   pip install -e ".[dev]"

   # Code quality checks
   black PaperSorter/
   flake8 PaperSorter/
   mypy PaperSorter/

   # Run tests
   pytest
   pytest --cov=PaperSorter

   # Build documentation
   cd docs
   make html

Contributing Guidelines
=======================

Code Contributions
------------------

- Follow existing code patterns and conventions
- Include tests for new functionality
- Update documentation for user-facing changes
- Keep commits focused and well-described

Documentation
-------------

- API documentation using docstrings
- User guides for new features
- Architecture documentation for significant changes
- Examples and tutorials for complex workflows

Community
=========

- **Issues**: Bug reports and feature requests
- **Discussions**: General questions and ideas
- **Pull Requests**: Code contributions and reviews
- **Wiki**: Community-maintained documentation

Related Resources
=================

- :doc:`../api/index` - Complete API reference
- :doc:`../reference/index` - Technical specifications
- :doc:`../admin-guide/index` - Deployment and operations
