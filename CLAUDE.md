# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PaperSorter is an academic paper recommendation system built in Python that uses machine learning to filter RSS feeds and predict user interest in research articles. The system fetches articles from RSS/Atom feeds, generates embeddings using OpenAI-compatible APIs (like Solar LLM), and uses XGBoost regression to predict user interest levels.

## Architecture

The system consists of several key components:

- **FeedDatabase** (`feed_database.py`): PostgreSQL-based storage for article metadata, user labels, and predictions
- **EmbeddingDatabase** (`embedding_database.py`): PostgreSQL-based storage for article embedding vectors using pgvector extension
- **Tasks** (`tasks/`): CLI commands implemented as Click commands
  - `init`: Initialize database schema
  - `update`: Fetch new articles, generate embeddings, and queue items for broadcast
  - `import`: Import articles from external sources (currently supports PubMed)
    - `pubmed` subcommand: Downloads recent PubMed update files and imports with sampling
  - `train`: Train XGBoost model on labeled data (requires --name or --output)
  - `predict`: Generate embeddings and predictions for articles
  - `broadcast`: Process broadcast queue and send notifications to Slack
  - `serve`: Entry point for web interface (delegates to web package)
  - `test`: Test various system components
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
- **Providers** (`providers/`): Feed provider implementations
  - `base.py`: Abstract base class for feed providers
  - `rss.py`: RSS/Atom feed provider
- **Utils** (`utils/`): Utility modules
  - `pubmed_sync.py`: PubMed FTP sync and XML parsing functionality
- **__main__.py**: Dynamic CLI command loader that imports all tasks from `tasks/__init__.py`

## Common Commands

### Installation
```bash
pip install -e .
```

### Initial Setup Workflow (New Users)
```bash
# 1. Initialize database
papersorter init

# 2. Import initial data
papersorter import pubmed  # Downloads recent PubMed updates (10% sample by default)

# 3. Generate embeddings for semantic search and training
papersorter predict --count 10000

# 4. Start web interface and label papers
papersorter serve --skip-authentication user@example.com
# Use semantic search to find papers in your field
# Mark 10-20 papers as "Interested"

# 5. Train initial model (auto-handles lack of negative labels)
papersorter train --name "Initial Model"

# 6. Generate predictions
papersorter predict
```

### Regular Operations
```bash
# Periodic operations (typically run via cron)
papersorter update     # Fetch new articles and generate embeddings
papersorter broadcast  # Send notifications (respects per-channel broadcast hours)

# Model improvement workflow
papersorter serve      # Run web interface for labeling
papersorter train --name "Improved Model v2"  # Retrain model
papersorter predict    # Generate new predictions
```

### Development Commands
Since this is a Python package without traditional build/test configuration files, use standard Python development tools:
```bash
python -m PaperSorter.tasks.update     # Run individual tasks directly
python -m pytest                     # Run tests (if test files exist)
python -m flake8 PaperSorter/        # Code linting
python -m black PaperSorter/         # Code formatting
```

### Task-specific Options
- All tasks support `--config` (default: `./config.yml`), `--log-file` and `-q/--quiet` options
- `import pubmed`:
  - `--files` (default: 10): Number of recent update files to download
  - `--chunksize` (default: 2000): Articles per processing chunk
  - `--sample-rate` (default: 0.1): Random sampling rate (0.0-1.0)
  - `--seed`: Random seed for reproducible sampling
  - `--limit`: Maximum number of articles to import
  - `--parse-only`: Parse existing files instead of downloading
- `train`:
  - `--name`: Model name for database registration (mutually exclusive with --output)
  - `-o/--output`: Output file path (legacy mode, mutually exclusive with --name)
  - `-r/--rounds` (default: 1000): Number of boosting rounds
  - `--user-id` (multiple): Specific user IDs to train on (omit for all users)
  - `--embeddings-table` (default: embeddings): Embeddings table to use
  - `--pos-cutoff` (default: 0.5): Threshold for positive pseudo-labels
  - `--neg-cutoff` (default: 0.2): Threshold for negative pseudo-labels
  - `--pseudo-weight` (default: 0.5): Weight for pseudo-labeled data
- `predict`:
  - `--count`: Number of articles to process (useful for initial setup)
  - `--force`: Force re-prediction even if predictions exist
- `update`: `--batch-size`, `--limit-sources` (max sources to scan), `--check-interval-hours` (check interval)
- `broadcast`: `--limit` (max items to process per channel), `--max-content-length`, `--clear-old-days` (default: 30)
- `serve`: `--host` (default: 0.0.0.0), `--port` (default: 5001), `--debug`, `--skip-authentication` (dev mode)

## Configuration

All configuration is stored in `./config.yml`:

```yaml
db:
  type: postgres
  host: localhost
  user: papersorter
  database: papersorter
  password: "your_password"

web:
  base_url: "https://papersorter.useoul.edu" # Base URL for web interface (used for "More Like This" links in Slack)
  flask_secret_key: "your_flask_secret_key"  # generate with secrets.token_hex(32)

oauth:
  google:
    client_id: "your_google_client_id"
    secret: "your_google_client_secret"
  github:
    client_id: "your_github_client_id"
    secret: "your_github_client_secret"
  orcid:
    client_id: "APP-XXXXXXXXXXXX"  # Your ORCID App ID
    secret: "your_orcid_client_secret"
    sandbox: false  # Set to true for testing

embedding_api:
  api_key: "your_api_key"
  api_url: ""   # Optional: custom API endpoint (defaults to https://api.openai.com/v1)
  model: ""     # Optional: model name (defaults to text-embedding-3-large)
  dimensions: ""  # Optional: embedding dimensions (e.g., 1536 for pgvector HNSW indexing)

models:
  path: "./models"  # Directory for storing trained model files

summarization_api:
  api_key: "your_api_key"
  api_url: "https://generativelanguage.googleapis.com/v1beta/openai"  # For Gemini
  model: "gemini-2.0-flash-thinking-exp-01-21"

# Feed sources are configured via web interface or database
# No feed_service configuration needed anymore

# Scholarly database configuration (choose between Semantic Scholar and OpenAlex)
scholarly_database:
  provider: "semantic_scholar"  # or "openalex"
  semantic_scholar:
    api_key: "your_s2_api_key"
  openalex:
    email: "your_real_email@domain.com"  # MUST be a valid email (test@example.com won't work)

# Legacy configuration (for backward compatibility)
semanticscholar:
  api_key: "your_s2_api_key"
```

Note:
- Slack webhook URLs are stored in the database `channels` table per channel.
- The system maintains backward compatibility with old config format (`google_oauth`)

## Data Storage

- PostgreSQL database with credentials in `./config.yml`
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
- **channels**: Notification channels (webhooks with per-channel settings including broadcast_hours)
- **models**: Trained model metadata
- **events**: Event logging for user actions and system events

## Key Implementation Details

- Uses Click for CLI interface with dynamic command loading from tasks module
- Embeddings generated using OpenAI-compatible APIs with configurable models
- LLM input format combines title, authors, source, and abstract
- XGBoost regression model predicts interest scores from embeddings
- PostgreSQL database uses pgvector extension for efficient embedding storage and similarity search
- Database configuration loaded from `./config.yml`
- Scholarly database integration (Semantic Scholar or OpenAlex) for enriching article metadata
- Support for batch processing to handle rate limits efficiently
- Maintains backward compatibility with existing SQLite field names through mapping
- Google, GitHub, and ORCID OAuth authentication for web interface access
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

## Recent Updates

### Train Task Enhancement (2025)
- Now requires either `--name` (for database registration) or `--output` (for file save)
- Models registered with `--name` are saved as `model-{id}.pkl` in the models directory
- Supports training on multiple users or all users (when --user-id is omitted)
- Automatically handles initial training with only positive labels by using unlabeled articles as negatives
- Applies reduced weights (50%) to auto-generated negative pseudo-labels

### Import Task Addition (2025)
- New `import pubmed` command for bulk article ingestion
- Downloads recent update files from PubMed FTP server
- Supports random sampling (default 10%) to reduce dataset size while maintaining diversity
- Filters out articles without abstracts before sampling
- Uses ISOAbbreviation for journal names when available
- Processes articles in chronological order for consistency

### Documentation Updates (2025)
- Added complete initial setup workflow for new users
- Emphasized importance of `predict --count 10000` for embedding generation
- Updated all examples to use required `--name` option for training
- Added guidance on using semantic search to find papers for labeling

## Documentation Structure

The project documentation is organized as follows:

```
docs/
├── README.md                 # Documentation overview
├── getting-started/
│   ├── installation.md      # Installation guide
│   ├── quickstart.md        # 15-minute quick start
│   └── first-model.md       # Detailed training guide
├── user-guide/
│   └── notifications.md     # Notification setup
├── admin-guide/
│   └── authentication.md    # OAuth configuration
├── cli-reference/
│   ├── commands.rst         # CLI command reference
│   └── examples.md          # Command examples
└── api/
    └── database.rst         # Database schema documentation
```

Key documentation updates:
- **quickstart.md**: Fast track setup with complete workflow for new users
- **first-model.md**: Comprehensive guide including initial training mode
- **README.md**: Updated with step-by-step workflow and new command options

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

