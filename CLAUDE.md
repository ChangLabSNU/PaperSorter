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
  - `update`: Fetch new articles, generate embeddings, and queue items for broadcast
  - `train`: Train XGBoost model on labeled data
  - `broadcast`: Process broadcast queue and send notifications to Slack
  - `serve`: Entry point for web interface (delegates to web package)
- **Web** (`web/`): Modular web interface implementation
  - `app.py`: Flask application factory
  - `main.py`: Main route handlers for feed list and labeling
  - `auth/`: Authentication module with Google OAuth integration
    - `models.py`: User model for Flask-Login
    - `decorators.py`: Authentication decorators (admin_required)
    - `routes.py`: Login/logout/OAuth callback routes
  - `api/`: RESTful API endpoints organized by domain
    - `feeds.py`: Feed operations (list, star, feedback, similar articles)
    - `search.py`: Text search, AI summarization, Semantic Scholar integration
    - `settings.py`: Admin settings for channels, users, models, events
    - `user.py`: User preferences and poster generation
  - `models/`: Data models
    - `semantic_scholar.py`: Semantic Scholar paper representation
  - `utils/`: Shared utilities
    - `database.py`: Database helper functions
  - `jobs/`: Background job processors
    - `poster.py`: AI-powered infographic poster generation
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
- `update`: `--batch-size`, `--get-full-list`, `--force-reembed`, `--force-rescore`, `--score-threshold` (default: 0.7)
- `train`: `-r/--rounds` (default: 100), `-o/--output` (model file), `--embeddings-table` (default: embeddings)
- `broadcast`: `--limit` (max items to process per channel), `--max-content-length`, `--clear-old-days` (default: 30)
- `serve`: `--host` (default: 0.0.0.0), `--port` (default: 5001), `--debug`

## Configuration

All configuration is stored in `qbio/config.yml`:

```yaml
db:
  type: postgres
  host: localhost
  user: papersorter
  database: papersorter
  password: "your_password"

google_oauth:
  client_id: "your_google_client_id"
  secret: "your_google_client_secret"
  flask_secret_key: "your_flask_secret_key"  # generate with secrets.token_hex(32)

embedding_api:
  api_key: "your_api_key"
  api_url: ""   # Optional: custom API endpoint (defaults to https://api.openai.com/v1)
  model: ""     # Optional: model name (defaults to text-embedding-3-large)
  dimensions: ""  # Optional: embedding dimensions (e.g., 1536 for pgvector HNSW indexing)

summarization_api:
  api_key: "your_api_key"
  api_url: "https://generativelanguage.googleapis.com/v1beta/openai"  # For Gemini
  model: "gemini-2.0-flash-thinking-exp-01-21"

feed_service:
  type: "theoldreader"
  username: "your_email"
  password: "your_password"

semanticscholar:
  api_key: "your_s2_api_key"

web:
  base_url: "https://reader.qbio.io"  # Base URL for web interface (used for "More Like This" links in Slack)
```

Note: Slack webhook URLs are stored in the database `channels` table per channel.

## Data Storage

- PostgreSQL database with credentials in `qbio/config.yml`
- `model.pkl`: Trained XGBoost model for interest prediction

### Database Schema
The PostgreSQL database includes tables for:
- **feeds**: Article metadata (id, external_id, title, content, author, origin, link, published, tldr)
- **embeddings**: Embedding vectors using pgvector extension (feed_id, embedding)
- **preferences**: User labels and ratings (feed_id, user_id, score, source)
- **predicted_preferences**: Model predictions (feed_id, model_id, score)
- **broadcasts**: Tracking and queuing of notifications (feed_id, channel_id, broadcasted_time)
- **labeling_sessions**: Manual labeling interface data
- **users**: User accounts (includes bookmark position and preferences)
- **channels**: Notification channels (Slack webhooks with per-channel settings)
- **models**: Trained model metadata
- **events**: Event logging for user actions and system events
- **broadcasts**: Record of articles sent to channels (prevents duplicates)

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
- Broadcast queue mechanism: items are queued during update phase based on score threshold and processed during broadcast phase
- Broadcast task iterates through all active channels (is_active=TRUE) and processes their associated broadcast queue items
- Each channel can have its own model_id and score_threshold settings

### Web Interface Architecture
- Modular Flask application using blueprints for better organization
- Authentication handled separately with reusable decorators
- API endpoints organized by functional domain (feeds, search, settings, user)
- Background jobs (like poster generation) run in separate threads
- Shareable search URLs with query parameters (`?q=search+terms`)
- Real-time feed content loading and interactive labeling
- AI-powered summarization and infographic generation for article collections

## Dependencies

Core dependencies (from setup.py):
- click >= 8.0 (CLI framework)
- numpy >= 1.20 (numerical operations)
- openai >= 1.30 (embeddings API)
- pandas >= 2.0 (data manipulation)
- psycopg2-binary >= 2.9 (PostgreSQL database adapter)
- pgvector >= 0.2.0 (PostgreSQL vector extension support)
- PyYAML >= 6.0 (configuration parsing)
- requests >= 2.7.0 (HTTP requests)
- scikit-learn >= 1.4 (machine learning utilities)
- scipy >= 1.10 (scientific computing)
- xgboost > 2.0 (gradient boosting model)
- Flask >= 2.0 (web framework for serve task)
- Flask-Login >= 0.6.0 (user session management)
- Authlib >= 1.2.0 (OAuth authentication)

