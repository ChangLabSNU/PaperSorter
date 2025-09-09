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
* ``--name NAME``: Model name for database registration (required)
* ``-r, --rounds INTEGER``: Number of XGBoost rounds (default: 1000)
* ``--user-id ID``: Train on specific user(s), can be repeated
* ``--embeddings-table TEXT``: Embeddings table name (default: ``embeddings``)
* ``--pos-cutoff FLOAT``: Threshold for positive labels (default: 0.5)
* ``--neg-cutoff FLOAT``: Threshold for negative labels (default: 0.2)
* ``--pseudo-weight FLOAT``: Weight for pseudo-labeled data (default: 0.5)

**Example:**

.. code-block:: bash

   # Train on all users
   papersorter train --name "Production Model v1"

   # Train on specific users
   papersorter train --name "User Model" --user-id 1 --user-id 2

   # Train with more rounds
   papersorter train --name "Accurate Model" --rounds 2000

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
* ``--skip-authentication USERNAME``: Bypass OAuth and auto-login as admin user (development only)

**Example:**

.. code-block:: bash

   # Start on default port
   papersorter serve

   # Start with debug mode
   papersorter serve --debug --port 8080

   # Production mode with multiple processes
   papersorter serve --processes 4

   # Development mode without OAuth
   papersorter serve --skip-authentication yourname@domain.com

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

models
~~~~~~

Manage trained models.

.. code-block:: bash

   papersorter models SUBCOMMAND [OPTIONS]

**Subcommands:**

* ``list``: List all models
* ``show ID``: Show detailed model information
* ``modify ID``: Update model metadata
* ``activate ID``: Activate a model
* ``deactivate ID``: Deactivate a model
* ``delete ID``: Delete a model
* ``export ID``: Export model to file
* ``import FILE``: Import model from file
* ``validate [ID]``: Validate model files

**List Options:**

* ``--active-only``: Show only active models
* ``--inactive-only``: Show only inactive models
* ``--with-channels``: Include associated channels
* ``--format {table,json}``: Output format

**Export Options:**

* ``-o, --output FILE``: Output file path (required)
* ``--include-predictions``: Include prediction statistics

**Import Options:**

* ``--name NAME``: Override model name
* ``--notes NOTES``: Override model notes
* ``--activate``: Activate model after import

**Example:**

.. code-block:: bash

   # List all models
   papersorter models list

   # Show model details
   papersorter models show 1

   # Export model for backup
   papersorter models export 1 -o backup.pkl

   # Import model
   papersorter models import backup.pkl --name "Restored Model"

   # Validate all models
   papersorter models validate

Management Commands
-------------------

embeddings
~~~~~~~~~~

Manage embeddings table and indices for vector similarity search.

.. code-block:: bash

   papersorter embeddings SUBCOMMAND [OPTIONS]

**Subcommands:**

* ``clear``: Remove all embeddings from the database
* ``reset``: Drop and recreate embeddings table with updated vector dimensions
* ``status``: Show embeddings table statistics and index information
* ``index on``: Create HNSW index for fast similarity search
* ``index off``: Drop HNSW index (useful for bulk imports)

**Clear Options:**

* ``--force``: Skip confirmation prompt

**Reset Options:**

* ``--force``: Skip confirmation prompt

**Status Options:**

* ``--detailed``: Show detailed statistics including coverage by source and recent activity

**Index On Options:**

* ``--m INTEGER``: HNSW M parameter (default: 16)
* ``--ef-construction INTEGER``: HNSW ef_construction parameter (default: 64)

**Index Off Options:**

* ``--force``: Skip confirmation prompt

**Example:**

.. code-block:: bash

   # Check embeddings status
   papersorter embeddings status
   
   # Show detailed statistics
   papersorter embeddings status --detailed
   
   # Clear all embeddings
   papersorter embeddings clear --force
   
   # Reset table with new dimensions (from config)
   papersorter embeddings reset
   
   # Optimize for bulk import
   papersorter embeddings index off
   papersorter predict --all  # Generate embeddings
   papersorter embeddings index on
   
   # Create index with custom parameters
   papersorter embeddings index on --m 32 --ef-construction 128

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

Generate embeddings and predictions for articles.

.. code-block:: bash

   papersorter predict [OPTIONS]

**Options:**

* ``--count N``: Number of articles to process
* ``--all``: Process all articles without limit
* ``--force``: Force re-prediction even if predictions exist

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