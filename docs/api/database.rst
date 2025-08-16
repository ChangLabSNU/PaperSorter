Database API
============

This section documents the database interfaces and models used by PaperSorter.

FeedDatabase Class
------------------

The main database interface for managing papers, labels, and predictions.

.. autoclass:: PaperSorter.feed_database.FeedDatabase
   :members:
   :special-members: __init__

Core Methods
~~~~~~~~~~~~

**Paper Management**

.. automethod:: PaperSorter.feed_database.FeedDatabase.add_paper
.. automethod:: PaperSorter.feed_database.FeedDatabase.get_paper
.. automethod:: PaperSorter.feed_database.FeedDatabase.update_paper
.. automethod:: PaperSorter.feed_database.FeedDatabase.delete_paper
.. automethod:: PaperSorter.feed_database.FeedDatabase.get_recent_papers

**Label Management**

.. automethod:: PaperSorter.feed_database.FeedDatabase.add_label
.. automethod:: PaperSorter.feed_database.FeedDatabase.get_labels
.. automethod:: PaperSorter.feed_database.FeedDatabase.get_user_labels

**Prediction Management**

.. automethod:: PaperSorter.feed_database.FeedDatabase.save_prediction
.. automethod:: PaperSorter.feed_database.FeedDatabase.get_predictions
.. automethod:: PaperSorter.feed_database.FeedDatabase.get_high_scoring_papers

EmbeddingDatabase Class
-----------------------

Manages paper embeddings using pgvector for similarity search.

.. autoclass:: PaperSorter.embedding_database.EmbeddingDatabase
   :members:
   :special-members: __init__

Embedding Operations
~~~~~~~~~~~~~~~~~~~~

.. automethod:: PaperSorter.embedding_database.EmbeddingDatabase.add_embedding
.. automethod:: PaperSorter.embedding_database.EmbeddingDatabase.get_embedding
.. automethod:: PaperSorter.embedding_database.EmbeddingDatabase.find_similar
.. automethod:: PaperSorter.embedding_database.EmbeddingDatabase.bulk_add_embeddings

Database Schema
---------------

Tables
~~~~~~

**feeds**
   Main table for paper metadata.

   .. code-block:: sql

      CREATE TABLE feeds (
          id SERIAL PRIMARY KEY,
          external_id VARCHAR(255) UNIQUE,
          title TEXT NOT NULL,
          content TEXT,
          author TEXT,
          origin VARCHAR(255),
          link TEXT,
          published TIMESTAMP,
          tldr TEXT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );

**embeddings**
   Stores embedding vectors using pgvector extension.

   .. code-block:: sql

      CREATE TABLE embeddings (
          id SERIAL PRIMARY KEY,
          feed_id INTEGER REFERENCES feeds(id) ON DELETE CASCADE,
          embedding vector(1536),
          model_name VARCHAR(100),
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(feed_id, model_name)
      );

**preferences**
   User labels and ratings for papers.

   .. code-block:: sql

      CREATE TABLE preferences (
          id SERIAL PRIMARY KEY,
          feed_id INTEGER REFERENCES feeds(id) ON DELETE CASCADE,
          user_id VARCHAR(100) DEFAULT 'default',
          score FLOAT NOT NULL,
          source VARCHAR(50),
          comment TEXT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(feed_id, user_id)
      );

**predicted_preferences**
   Model predictions for papers.

   .. code-block:: sql

      CREATE TABLE predicted_preferences (
          id SERIAL PRIMARY KEY,
          feed_id INTEGER REFERENCES feeds(id) ON DELETE CASCADE,
          model_id INTEGER REFERENCES models(id),
          score FLOAT NOT NULL,
          confidence FLOAT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(feed_id, model_id)
      );

**channels**
   Notification channel configuration.

   .. code-block:: sql

      CREATE TABLE channels (
          id SERIAL PRIMARY KEY,
          name VARCHAR(100) UNIQUE NOT NULL,
          type VARCHAR(50) DEFAULT 'slack',
          webhook_url TEXT,
          email_address VARCHAR(255),
          is_active BOOLEAN DEFAULT TRUE,
          score_threshold FLOAT DEFAULT 3.5,
          model_id INTEGER REFERENCES models(id),
          broadcast_hours INTEGER[],
          max_items_per_broadcast INTEGER DEFAULT 20,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );

**broadcasts**
   Tracks sent notifications.

   .. code-block:: sql

      CREATE TABLE broadcasts (
          id SERIAL PRIMARY KEY,
          feed_id INTEGER REFERENCES feeds(id) ON DELETE CASCADE,
          channel_id INTEGER REFERENCES channels(id) ON DELETE CASCADE,
          broadcasted_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          score FLOAT,
          status VARCHAR(50),
          UNIQUE(feed_id, channel_id)
      );

**sources**
   RSS feed sources configuration.

   .. code-block:: sql

      CREATE TABLE sources (
          id SERIAL PRIMARY KEY,
          name VARCHAR(200) NOT NULL,
          url TEXT NOT NULL,
          type VARCHAR(50) DEFAULT 'rss',
          is_active BOOLEAN DEFAULT TRUE,
          last_checked TIMESTAMP,
          check_interval_hours INTEGER DEFAULT 6,
          error_count INTEGER DEFAULT 0,
          last_error TEXT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );

**models**
   Trained model metadata.

   .. code-block:: sql

      CREATE TABLE models (
          id SERIAL PRIMARY KEY,
          name VARCHAR(100),
          file_path TEXT,
          accuracy FLOAT,
          rmse FLOAT,
          r2_score FLOAT,
          training_samples INTEGER,
          parameters JSONB,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          is_active BOOLEAN DEFAULT FALSE
      );

**users**
   User accounts for web interface.

   .. code-block:: sql

      CREATE TABLE users (
          id VARCHAR(100) PRIMARY KEY,
          email VARCHAR(255) UNIQUE,
          name VARCHAR(200),
          oauth_provider VARCHAR(50),
          oauth_id VARCHAR(255),
          bookmark_position INTEGER DEFAULT 0,
          preferences JSONB,
          is_admin BOOLEAN DEFAULT FALSE,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          last_login TIMESTAMP
      );

**events**
   Event logging for analytics.

   .. code-block:: sql

      CREATE TABLE events (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(100),
          event_type VARCHAR(100),
          event_data JSONB,
          ip_address INET,
          user_agent TEXT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );

Indexes
~~~~~~~

.. code-block:: sql

   -- Performance indexes
   CREATE INDEX idx_feeds_published ON feeds(published DESC);
   CREATE INDEX idx_feeds_external_id ON feeds(external_id);
   CREATE INDEX idx_preferences_user_score ON preferences(user_id, score DESC);
   CREATE INDEX idx_predicted_preferences_score ON predicted_preferences(model_id, score DESC);
   CREATE INDEX idx_broadcasts_channel_time ON broadcasts(channel_id, broadcasted_time DESC);
   
   -- Full-text search
   CREATE INDEX idx_feeds_title_gin ON feeds USING gin(to_tsvector('english', title));
   CREATE INDEX idx_feeds_content_gin ON feeds USING gin(to_tsvector('english', content));
   
   -- Vector similarity search (pgvector)
   CREATE INDEX idx_embeddings_vector ON embeddings USING ivfflat (embedding vector_cosine_ops);

Connection Management
---------------------

Configuration
~~~~~~~~~~~~~

Database connection is configured in ``config.yml``:

.. code-block:: yaml

   db:
     type: postgres
     host: localhost
     port: 5432
     user: papersorter
     database: papersorter
     password: "secure_password"
     
     # Optional connection pool settings
     pool_size: 10
     max_overflow: 20
     pool_timeout: 30
     pool_recycle: 3600

Connection Pool
~~~~~~~~~~~~~~~

PaperSorter uses connection pooling for efficient database access:

.. code-block:: python

   from PaperSorter.feed_database import FeedDatabase
   
   # Connection pool is managed internally
   db = FeedDatabase()
   
   # Use context manager for automatic cleanup
   with db.get_connection() as conn:
       cursor = conn.cursor()
       cursor.execute("SELECT * FROM feeds LIMIT 10")
       results = cursor.fetchall()

Transactions
~~~~~~~~~~~~

.. code-block:: python

   # Atomic operations with transactions
   with db.transaction() as tx:
       tx.add_paper(paper_data)
       tx.add_embedding(paper_id, embedding)
       tx.save_prediction(paper_id, score)
       # Automatically commits on success, rolls back on error

Query Examples
--------------

Common Queries
~~~~~~~~~~~~~~

.. code-block:: python

   # Get recent high-scoring papers
   query = """
       SELECT f.*, pp.score
       FROM feeds f
       JOIN predicted_preferences pp ON f.id = pp.feed_id
       WHERE pp.score > %s
       AND f.published > CURRENT_DATE - INTERVAL '7 days'
       ORDER BY pp.score DESC
       LIMIT %s
   """
   high_scoring = db.execute(query, (4.0, 20))
   
   # Find similar papers using embeddings
   query = """
       SELECT f.*, 
              1 - (e1.embedding <=> e2.embedding) as similarity
       FROM embeddings e1
       CROSS JOIN LATERAL (
           SELECT * FROM embeddings e2
           JOIN feeds f ON e2.feed_id = f.id
           WHERE e2.feed_id != e1.feed_id
           ORDER BY e1.embedding <=> e2.embedding
           LIMIT 10
       ) AS similar
       WHERE e1.feed_id = %s
   """
   similar_papers = db.execute(query, (paper_id,))

Aggregation Queries
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Label statistics by user
   stats = db.execute("""
       SELECT user_id,
              COUNT(*) as total_labels,
              AVG(score) as avg_score,
              STDDEV(score) as score_stddev
       FROM preferences
       GROUP BY user_id
       ORDER BY total_labels DESC
   """)
   
   # Daily paper counts by source
   daily_counts = db.execute("""
       SELECT DATE(published) as date,
              origin,
              COUNT(*) as paper_count
       FROM feeds
       WHERE published > CURRENT_DATE - INTERVAL '30 days'
       GROUP BY DATE(published), origin
       ORDER BY date DESC, paper_count DESC
   """)

Migration Management
--------------------

Creating Migrations
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # migrations/001_add_user_preferences.py
   def upgrade(db):
       db.execute("""
           ALTER TABLE users 
           ADD COLUMN preferences JSONB DEFAULT '{}'::jsonb
       """)
       
   def downgrade(db):
       db.execute("""
           ALTER TABLE users 
           DROP COLUMN preferences
       """)

Running Migrations
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Apply all pending migrations
   papersorter migrate
   
   # Rollback last migration
   papersorter migrate --rollback
   
   # Check migration status
   papersorter migrate --status