====================
Database Integration
====================

PaperSorter now ships with a centralized PostgreSQL access layer located at
``PaperSorter/db/manager.py``.  The :class:`~PaperSorter.db.DatabaseManager`
wraps a thread-safe psycopg2 connection pool and provides convenient context
managers for opening sessions and cursors with consistent settings (pgvector
registration, RealDict cursors, timeouts, and automatic rollbacks).

Key Features
============

- **Connection pooling**: ``DatabaseManager`` relies on
  :class:`~psycopg2.pool.ThreadedConnectionPool` to reuse connections across the
  application.
- **pgvector registration**: Every connection registers the pgvector extension
  once and caches the result so callers do not need to repeat the boilerplate.
- **Context-managed sessions**: ``db_manager.session()`` yields a
  ``DatabaseSession`` object that commits on success and rolls back on failure.
- **Legacy compatibility**: ``db_manager.connect()`` returns a
  ``PooledConnection`` wrapper that mimics the old ``psycopg2.connect`` object
  so existing code can opt in gradually.

Web Application Usage
=====================

``create_app`` instantiates a single ``DatabaseManager`` and stores it on the
Flask application config as ``app.config["db_manager"]``.  Application code
should always work inside ``db_manager.session()`` blocks rather than calling a
legacy ``get_db_connection`` helper:

.. code-block:: python

   from flask import current_app

   db_manager = current_app.config["db_manager"]
   with db_manager.session() as session:
       cursor = session.cursor(dict_cursor=True)
       cursor.execute("SELECT ...")
       rows = cursor.fetchall()

The session automatically commits when the ``with`` block exits without an
exception.  Call ``session.commit()`` explicitly if you need to flush changes
midway through a longer workflow.

CLI and Task Usage
==================

Tasks that previously invoked ``psycopg2.connect`` should construct a manager
from configuration and use sessions to run their queries.  For example, both
``papersorter models`` and ``papersorter predict`` now follow this pattern:

.. code-block:: python

   from PaperSorter.db import DatabaseManager

   db_manager = DatabaseManager.from_config(db_config, application_name="papersorter-cli-models")
   try:
       with db_manager.session() as session:
           cursor = session.cursor(dict_cursor=True)
           cursor.execute("SELECT ...")
           # session.commit() when writes are performed
   finally:
       db_manager.close()

Within long-running loops, pass the current ``session`` alongside the cursor so
helpers can issue ``session.commit()`` (e.g., after ``execute_batch`` calls).

Migration Tips
==============

- Replace manual ``psycopg2.connect`` calls with ``DatabaseManager.from_config``.
- Wrap database work in ``with db_manager.session():`` and request cursors via
  ``session.cursor(dict_cursor=True)`` when row dictionaries are needed.
- Remove explicit ``conn.commit()`` / ``conn.rollback()`` pairs; the session
  handles transaction boundaries.  Keep explicit ``session.commit()`` invocations
  when you intentionally persist work before a long sequence continues.
- Legacy helpers like ``PaperSorter.feed_database.FeedDatabase`` still manage
  their own connections.  They can be refactored incrementally to depend on the
  manager when practical.

Adopting the shared manager provides predictable transaction handling, unified
logging, and a single place to evolve database settings across the codebase.
