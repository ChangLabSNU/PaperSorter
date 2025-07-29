# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PaperSorter is an academic paper recommendation system built in Python that uses machine learning to filter RSS feeds and predict user interest in research articles. The system fetches articles from TheOldReader, generates embeddings using OpenAI-compatible APIs (like Solar LLM), and uses XGBoost regression to predict user interest levels.

## Architecture

The system consists of several key components:

- **FeedDatabase** (`feed_database.py`): PostgreSQL-based storage for article metadata, user labels, and predictions
- **EmbeddingDatabase** (`embedding_database.py`): PostgreSQL-based storage for article embedding vectors using pgvector extension
- **Tasks** (`tasks/`): CLI commands implemented as Click commands
  - `init`: Initialize databases from TheOldReader feeds
  - `update`: Fetch new articles and generate embeddings
  - `train`: Train XGBoost model on labeled data
  - `broadcast`: Send notifications for high-scoring articles to Slack
  - `serve`: Web interface for article labeling and other interactive tasks
- **Providers** (`providers/`): TheOldReader API integration
- **Contrib** (`contrib/`): Additional utilities like Tor support
- **__main__.py**: Dynamic CLI command loader that imports all tasks from `tasks/__init__.py`

## Common Commands

### Installation
```bash
pip install -e .
```

### Core Workflow
```bash
# Initial setup - requires populated TheOldReader account
papersorter init

# Train initial model (needs ~1000 articles with ~100 starred)
papersorter train

# Regular operations
papersorter update     # Fetch new articles and generate embeddings
papersorter broadcast  # Send Slack notifications for interesting articles

# Model improvement workflow
papersorter train -o model-temporary.pkl -f feedback.xlsx  # Export for labeling
papersorter serve                                          # Run web interface for labeling
papersorter train                                          # Retrain model
```

### Development Commands
Since this is a Python package without traditional build/test configuration files, use standard Python development tools:
```bash
python -m PaperSorter.tasks.init     # Run individual tasks directly
python -m pytest                     # Run tests (if test files exist)
python -m flake8 PaperSorter/        # Code linting
python -m black PaperSorter/         # Code formatting
```

### Task-specific Options
- All tasks support `--config` (default: `qbio/config.yml`), `--log-file` and `-q/--quiet` options
- `init`: `--batch-size` (default: 100)
- `update`: `--batch-size`, `--get-full-list`, `--force-reembed`, `--force-rescore`
- `train`: `-r/--rounds` (default: 100), `-o/--output` (model file), `-f/--output-feedback` (Excel file)
- `broadcast`: `--days` (lookback period), `--score-threshold` (default: 0.7), `--max-content-length`
- `serve`: `--host` (default: 0.0.0.0), `--port` (default: 5001), `--debug`

## Environment Variables

Required for operation:
- `TOR_EMAIL`: TheOldReader account email
- `TOR_PASSWORD`: TheOldReader account password  
- `PAPERSORTER_API_KEY`: OpenAI/Solar LLM API key for embeddings
- `PAPERSORTER_WEBHOOK_URL`: Slack webhook URL for notifications

Required for Google OAuth authentication:
- `GOOGLE_CLIENT_ID`: Google OAuth client ID
- `GOOGLE_CLIENT_SECRET`: Google OAuth client secret
- `FLASK_SECRET_KEY`: Flask session secret key (generate with `secrets.token_hex(32)`)

Optional configuration:
- `PAPERSORTER_API_URL`: Custom API endpoint (defaults to Solar LLM)
- `PAPERSORTER_MODEL`: Embedding model name (default: `solar-embedding-1-large-query`)

## Data Storage

- PostgreSQL database with credentials in `qbio/config.yml`
- `model.pkl`: Trained XGBoost model for interest prediction

### Database Schema
The PostgreSQL database includes tables for:
- **feeds**: Article metadata (id, external_id, title, content, author, origin, link, published, tldr)
- **embeddings**: Embedding vectors using pgvector extension (feed_id, embedding)
- **preferences**: User labels and ratings (feed_id, user_id, score, source)
- **predicted_preferences**: Model predictions (feed_id, model_id, score)
- **broadcast_logs**: Tracking of sent notifications (feed_id, channel_id, broadcasted_time)
- **labeling_sessions**: Manual labeling interface data
- **users**: User accounts
- **channels**: Notification channels
- **models**: Trained model metadata

## Key Implementation Details

- Uses Click for CLI interface with dynamic command loading from tasks module
- Embeddings generated using OpenAI-compatible APIs with configurable models
- LLM input format combines title, authors, source, and abstract
- XGBoost regression model predicts interest scores from embeddings
- PostgreSQL database uses pgvector extension for efficient embedding storage and similarity search
- Database configuration loaded from `qbio/config.yml`
- Semantic Scholar API integration for enriching article metadata
- Support for batch processing to handle rate limits efficiently
- Maintains backward compatibility with existing SQLite field names through mapping
- Google OAuth authentication for web interface access
- Session management with Flask-Login
- Protected routes require authentication

## Dependencies

Core dependencies (from setup.py):
- click >= 8.0 (CLI framework)
- numpy >= 1.20 (numerical operations)
- openai >= 1.30 (embeddings API)
- pandas >= 2.0 (data manipulation)
- psycopg2-binary >= 2.9 (PostgreSQL database adapter)
- pgvector >= 0.2.0 (PostgreSQL vector extension support)
- python-dotenv >= 1.0 (environment variable management)
- PyYAML >= 6.0 (configuration parsing)
- requests >= 2.7.0 (HTTP requests)
- scikit-learn >= 1.4 (machine learning utilities)
- scipy >= 1.10 (scientific computing)
- xgboost > 2.0 (gradient boosting model)
- xlsxwriter >= 3.0 (Excel file generation for training feedback)
- Flask >= 2.0 (web framework for serve task)

