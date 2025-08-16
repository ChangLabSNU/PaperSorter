CLI Commands Reference
======================

This page documents all PaperSorter CLI commands. Commands are loaded dynamically from the ``tasks`` module.

.. contents:: Command Categories
   :local:
   :depth: 2

Core Commands
-------------

update
~~~~~~

Fetch new papers from RSS feeds and generate embeddings.

.. code-block:: bash

   papersorter update [OPTIONS]

**Options:**

* ``--config PATH``: Path to configuration file (default: ``./config.yml``)
* ``--log-file PATH``: Path to log file
* ``-q, --quiet``: Suppress output
* ``--batch-size INTEGER``: Number of papers per batch (default: 50)
* ``--limit-sources INTEGER``: Maximum number of sources to process
* ``--check-interval-hours INTEGER``: Check interval for sources (default: 6)
* ``--parallel``: Process sources in parallel
* ``--workers INTEGER``: Number of parallel workers (default: 4)
* ``--force``: Force update even if recently checked

**Example:**

.. code-block:: bash

   # Update all sources
   papersorter update

   # Update with parallel processing
   papersorter update --parallel --workers 8

   # Update only 2 sources
   papersorter update --limit-sources 2

train
~~~~~

Train XGBoost model on labeled papers.

.. code-block:: bash

   papersorter train [OPTIONS]

**Options:**

* ``--config PATH``: Path to configuration file
* ``--log-file PATH``: Path to log file
* ``-q, --quiet``: Suppress output
* ``-r, --rounds INTEGER``: Number of XGBoost rounds (default: 100)
* ``-o, --output PATH``: Output model file (default: ``model.pkl``)
* ``--embeddings-table TEXT``: Embeddings table name (default: ``embeddings``)
* ``--filter TEXT``: SQL WHERE clause to filter training data
* ``--test-size FLOAT``: Test set proportion (default: 0.2)
* ``--random-state INTEGER``: Random seed for reproducibility

**Example:**

.. code-block:: bash

   # Train with defaults
   papersorter train

   # Train with more rounds
   papersorter train --rounds 500 --output models/better_model.pkl

   # Train on specific papers
   papersorter train --filter "published > '2024-01-01'"

broadcast
~~~~~~~~~

Send notifications for high-scoring papers.

.. code-block:: bash

   papersorter broadcast [OPTIONS]

**Options:**

* ``--config PATH``: Path to configuration file
* ``--log-file PATH``: Path to log file
* ``-q, --quiet``: Suppress output
* ``--limit INTEGER``: Maximum items per channel
* ``--max-content-length INTEGER``: Maximum content length (default: 1000)
* ``--clear-old-days INTEGER``: Clear broadcasts older than N days (default: 30)
* ``--dry-run``: Preview without sending
* ``--channel TEXT``: Specific channel to broadcast to

**Example:**

.. code-block:: bash

   # Send all pending notifications
   papersorter broadcast

   # Preview what would be sent
   papersorter broadcast --dry-run

   # Send to specific channel only
   papersorter broadcast --channel "ml-papers"

serve
~~~~~

Start the web interface for labeling and management.

.. code-block:: bash

   papersorter serve [OPTIONS]

**Options:**

* ``--config PATH``: Path to configuration file
* ``--log-file PATH``: Path to log file
* ``-q, --quiet``: Suppress output
* ``--host TEXT``: Host to bind to (default: ``0.0.0.0``)
* ``--port INTEGER``: Port to bind to (default: 5001)
* ``--debug``: Enable debug mode
* ``--threaded``: Enable threading
* ``--processes INTEGER``: Number of processes

**Example:**

.. code-block:: bash

   # Start on default port
   papersorter serve

   # Start with debug mode
   papersorter serve --debug --port 8080

   # Production mode with multiple processes
   papersorter serve --processes 4

Information Commands
--------------------

stats
~~~~~

Display database statistics.

.. code-block:: bash

   papersorter stats [OPTIONS]

**Output includes:**

* Total papers
* Papers with embeddings
* Labeled papers
* Label distribution
* Active feeds
* Model performance

list-feeds
~~~~~~~~~~

List all configured feeds.

.. code-block:: bash

   papersorter list-feeds [OPTIONS]

**Options:**

* ``--active``: Show only active feeds
* ``--format {table,json,csv}``: Output format

recent
~~~~~~

Show recently added papers.

.. code-block:: bash

   papersorter recent [OPTIONS]

**Options:**

* ``--limit INTEGER``: Number of papers to show (default: 10)
* ``--scored``: Only show papers with predictions

search
~~~~~~

Search papers by keyword.

.. code-block:: bash

   papersorter search QUERY [OPTIONS]

**Options:**

* ``--limit INTEGER``: Maximum results (default: 20)
* ``--semantic``: Use semantic search with embeddings

**Example:**

.. code-block:: bash

   # Text search
   papersorter search "transformer attention"

   # Semantic search
   papersorter search "neural networks" --semantic

Management Commands
-------------------

add-feed
~~~~~~~~

Add a new RSS feed source.

.. code-block:: bash

   papersorter add-feed NAME URL [OPTIONS]

**Options:**

* ``--type {rss,atom,arxiv}``: Feed type (default: ``rss``)
* ``--active/--inactive``: Set initial state

**Example:**

.. code-block:: bash

   papersorter add-feed "arXiv ML" "http://arxiv.org/rss/cs.LG" --type rss

remove-feed
~~~~~~~~~~~

Remove a feed source.

.. code-block:: bash

   papersorter remove-feed FEED_ID [OPTIONS]

**Options:**

* ``--keep-papers``: Don't delete associated papers

add-channel
~~~~~~~~~~~

Add a notification channel.

.. code-block:: bash

   papersorter add-channel NAME WEBHOOK_URL [OPTIONS]

**Options:**

* ``--type {slack,discord,email}``: Channel type
* ``--threshold FLOAT``: Score threshold (default: 3.5)
* ``--model-id INTEGER``: Model to use

label
~~~~~

Label a paper from command line.

.. code-block:: bash

   papersorter label PAPER_ID SCORE [OPTIONS]

**Options:**

* ``--user TEXT``: User ID (default: ``default``)
* ``--comment TEXT``: Optional comment

**Example:**

.. code-block:: bash

   papersorter label 12345 5 --comment "Very relevant!"

export
~~~~~~

Export data from database.

.. code-block:: bash

   papersorter export TYPE [OPTIONS]

**Types:**

* ``labels``: Export labeled papers
* ``model``: Export trained model
* ``papers``: Export paper metadata

**Options:**

* ``--output PATH``: Output file path
* ``--format {json,csv,pickle}``: Output format

import
~~~~~~

Import data into database.

.. code-block:: bash

   papersorter import TYPE FILE [OPTIONS]

**Types:**

* ``labels``: Import paper labels
* ``papers``: Import paper metadata

Testing Commands
----------------

test-db
~~~~~~~

Test database connection.

.. code-block:: bash

   papersorter test-db

test-embedding
~~~~~~~~~~~~~~

Test embedding generation.

.. code-block:: bash

   papersorter test-embedding [OPTIONS]

**Options:**

* ``--text TEXT``: Text to embed
* ``--sample INTEGER``: Test with N sample papers

test-webhook
~~~~~~~~~~~~

Test notification webhook.

.. code-block:: bash

   papersorter test-webhook --channel CHANNEL_NAME

Maintenance Commands
--------------------

cleanup
~~~~~~~

Clean up old data.

.. code-block:: bash

   papersorter cleanup [OPTIONS]

**Options:**

* ``--days INTEGER``: Delete data older than N days
* ``--orphans``: Remove orphaned embeddings
* ``--duplicates``: Remove duplicate papers

vacuum
~~~~~~

Optimize database.

.. code-block:: bash

   papersorter vacuum [OPTIONS]

**Options:**

* ``--analyze``: Update statistics
* ``--full``: Full vacuum (locks database)

backup
~~~~~~

Backup database and models.

.. code-block:: bash

   papersorter backup [OPTIONS]

**Options:**

* ``--output PATH``: Backup file path
* ``--include-embeddings``: Include embeddings (large)

restore
~~~~~~~

Restore from backup.

.. code-block:: bash

   papersorter restore BACKUP_FILE [OPTIONS]

**Options:**

* ``--force``: Overwrite existing data

Advanced Commands
-----------------

cross-validate
~~~~~~~~~~~~~~

Cross-validate model performance.

.. code-block:: bash

   papersorter cross-validate [OPTIONS]

**Options:**

* ``--folds INTEGER``: Number of CV folds (default: 5)
* ``--metric {rmse,r2,mae}``: Evaluation metric

compare-models
~~~~~~~~~~~~~~

Compare multiple models.

.. code-block:: bash

   papersorter compare-models MODEL1 MODEL2 [OPTIONS]

predict
~~~~~~~

Get predictions for specific papers.

.. code-block:: bash

   papersorter predict [OPTIONS]

**Options:**

* ``--paper-id INTEGER``: Specific paper ID
* ``--recent INTEGER``: Predict for N recent papers
* ``--unlabeled``: Predict for unlabeled papers only

retrain
~~~~~~~

Retrain model with updated labels.

.. code-block:: bash

   papersorter retrain [OPTIONS]

**Options:**

* ``--auto-tune``: Automatically tune hyperparameters
* ``--validate``: Validate before replacing current model

Global Options
--------------

All commands support these global options:

* ``--config PATH``: Configuration file path
* ``--log-file PATH``: Log file path
* ``-q, --quiet``: Suppress output
* ``-v, --verbose``: Verbose output
* ``--version``: Show version
* ``--help``: Show help

Environment Variables
---------------------

* ``PAPERSORTER_CONFIG``: Default config file path
* ``PAPERSORTER_LOG``: Default log file path
* ``PAPERSORTER_DB_URL``: Database connection string
* ``PAPERSORTER_DEBUG``: Enable debug mode

Exit Codes
----------

* ``0``: Success
* ``1``: General error
* ``2``: Configuration error
* ``3``: Database error
* ``4``: Network error
* ``5``: Authentication error

Examples
--------

Daily Workflow
~~~~~~~~~~~~~~

.. code-block:: bash

   # Morning routine
   papersorter update --parallel
   papersorter broadcast

   # Evening routine
   papersorter cleanup --days 30
   papersorter train

Automation Script
~~~~~~~~~~~~~~~~~

.. code-block:: bash

   #!/bin/bash
   # papersorter-daily.sh

   set -e

   echo "Starting PaperSorter daily update..."

   # Update papers
   papersorter update --parallel --workers 8

   # Train if Sunday
   if [ $(date +%u) -eq 7 ]; then
       papersorter train
   fi

   # Send notifications
   papersorter broadcast

   # Cleanup old data
   papersorter cleanup --days 60

   echo "Daily update complete!"

Python Integration
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   import subprocess
   import json

   # Get stats as JSON
   result = subprocess.run(
       ['papersorter', 'stats', '--format', 'json'],
       capture_output=True,
       text=True
   )
   stats = json.loads(result.stdout)

   # Conditional training
   if stats['labeled_papers'] > 1000:
       subprocess.run(['papersorter', 'train', '--rounds', '200'])