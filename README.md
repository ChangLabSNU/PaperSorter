# PaperSorter

PaperSorter is an intelligent academic paper recommendation system that helps researchers stay up-to-date with relevant publications. It uses machine learning to filter RSS/Atom feeds and predict which papers match your research interests, then sends notifications to Slack or Discord for high-scoring articles.

<img src="https://github.com/ChangLabSNU/PaperSorter/assets/1702891/5ef2df1f-610b-4272-b496-ecf2a480dda2" width="660px">

## Key Features

- **Multi-source feed aggregation**: Fetches articles from RSS/Atom feeds (PubMed, bioRxiv, journal feeds, etc.)
- **ML-powered filtering**: Uses XGBoost regression on article embeddings to predict interest levels
- **Flexible AI integration**: Compatible with Solar LLM, Gemini, or any OpenAI-compatible generative AI API
- **Web-based labeling interface**: Interactive UI for labeling articles and improving the model
- **Slack & Discord integration**: Automated notifications for interesting papers with customizable thresholds
- **Scholarly database integration**: Choose between Semantic Scholar (with TL;DR summaries) or OpenAlex (no API key needed) for metadata enrichment
- **Multi-channel support**: Different models and thresholds for different research groups or topics
- **AI-powered content generation**: Create concise summaries and visual infographics for article collections

> **📊 Architecture Overview**: For a detailed view of how PaperSorter's components interact, see the [Architecture Overview](#architecture-overview) section below.

## Quick Start with Docker

The easiest way to get started with PaperSorter is using Docker Compose, which automatically sets up the database and web application.

### Prerequisites

- Docker and Docker Compose installed
- API keys for your chosen services (see Configuration section below)

### 1. Clone and Configure

```bash
git clone https://github.com/ChangLabSNU/PaperSorter.git
cd PaperSorter
```

### 2. Create Environment File

Copy `.env.example` to `.env` and edit it with your configuration:

```bash
# Database Configuration
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_USER=papersorter
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=papersorter

# Google OAuth (required for web interface)
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
FLASK_SECRET_KEY=your_flask_secret_key  # generate with: python -c "import secrets; print(secrets.token_hex(32))"

# Embedding API (choose one)
EMBEDDING_API_KEY=your_api_key
EMBEDDING_API_URL=https://api.upstage.ai/v1
EMBEDDING_MODEL=solar-embedding-1-large-passage
EMBEDDING_DIMENSIONS=4096

# Summarization API (optional)
SUMMARIZATION_API_KEY=your_api_key
SUMMARIZATION_API_URL=https://generativelanguage.googleapis.com/v1beta/openai
SUMMARIZATION_MODEL=gemini-2.5-pro

# Semantic Scholar (optional)
SEMANTIC_SCHOLAR_API_KEY=your_semantic_scholar_api_key

# Web Configuration
WEB_BASE_URL=http://localhost:5001

# Storage
AI_POSTER_DIR=/app/ai_posters

# Admin user email (required)
ADMIN_EMAIL=your_email@example.com
```

### 3. Start PaperSorter

```bash
docker-compose up -d
```

The application will be available at [http://localhost:5001](http://localhost:5001).

### 4. Initial Setup

1. **Log in**: Use the Google OAuth login with the email address you set as `ADMIN_EMAIL`
2. **Add feed sources**: Go to Settings → Feed Sources and add RSS/Atom feed URLs
3. **Fetch articles**: Run `docker-compose exec app papersorter update`
4. **Label articles**: Use the web interface to mark articles as Interested/Not Interested
5. **Train model**: Run `docker-compose exec app papersorter train`

### 5. Production Deployment

For production, update your `.env` file with:

```bash
WEB_BASE_URL=https://your-domain.com
```

And configure a reverse proxy (nginx) with SSL termination.

## Manual Installation

If you prefer to install PaperSorter manually without Docker:

### System Requirements

- Python 3.8+
- PostgreSQL 12+ with pgvector extension
- Modern web browser (for labeling interface)

### Installation

```bash
git clone https://github.com/ChangLabSNU/PaperSorter.git
cd PaperSorter
pip install -e .
```

### Database Setup

#### 1. Create PostgreSQL Database

First, create a database and user for PaperSorter:

```bash
# As PostgreSQL superuser:
sudo -u postgres psql <<EOF
CREATE USER papersorter WITH PASSWORD 'your_password';
CREATE DATABASE papersorter OWNER papersorter;
\c papersorter
CREATE EXTENSION vector;
GRANT ALL ON SCHEMA public TO papersorter;
EOF
```

If you have an existing database:

```bash
# Connect to your database and install pgvector
sudo -u postgres psql -d your_database -c "CREATE EXTENSION vector;"
```

#### 2. Initialize Database Schema

```bash
papersorter init
```

To reinitialize (drops existing data):

```bash
papersorter init --drop-existing
```

## Configuration

### Docker Configuration

When using Docker, configuration is handled through environment variables in the `.env` file (see Quick Start section above).

### Manual Configuration

Create a `config.yml` file:

```yaml
db:
  type: postgres
  host: localhost
  user: papersorter
  database: papersorter
  password: "your_password"

web:
  base_url: "https://your-domain.com"  # base URL for web interface
  flask_secret_key: "your_flask_secret_key"  # generate with secrets.token_hex(32)

# OAuth configuration - configure one or more providers
oauth:
  # Google OAuth
  google:
    client_id: "your_google_client_id.apps.googleusercontent.com"
    secret: "your_google_client_secret"

  # GitHub OAuth
  github:
    client_id: "your_github_oauth_client_id"
    secret: "your_github_oauth_client_secret"

  # ORCID OAuth (essential for academic users)
  orcid:
    client_id: "your_orcid_oauth_client_id"
    secret: "your_orcid_client_secret"
    sandbox: false  # Set to true for testing with sandbox.orcid.org

embedding_api:
  api_key: "your_api_key"
  api_url: "https://api.upstage.ai/v1"       # or your preferred provider
  model: "solar-embedding-1-large-passage"   # or your preferred model
  dimensions: 4096

summarization_api:
  api_key: "your_api_key"
  api_url: "https://generativelanguage.googleapis.com/v1beta/openai"  # For Gemini
  model: "gemini-2.5-pro"

# Scholarly database configuration (choose one provider)
scholarly_database:
  provider: "semantic_scholar"  # or "openalex"

  # Option 1: Semantic Scholar (provides TL;DR summaries, requires API key)
  semantic_scholar:
    api_key: "your_semantic_scholar_api_key"

  # Option 2: OpenAlex (no API key needed, just email)
  openalex:
    email: "your_email@example.com"  # Must be a valid email address
```

## Getting Started

### 1. Add Feed Sources

**Docker users**: The web interface is already running at [http://localhost:5001](http://localhost:5001)

**Manual users**: Start the web interface:

```bash
papersorter serve
```

Navigate to http://localhost:5001 and:
- Log in with your preferred OAuth provider (ORCID, Google, or GitHub)
- Go to Settings → Feed Sources
- Add RSS/Atom feed URLs for journals, preprint servers, or PubMed searches

### 2. Initial Data Collection

**Docker users**:

```bash
docker-compose exec app papersorter update
```

**Manual users**:

```bash
papersorter update
```

### 3. Label Training Data

Use the web interface to label articles:

- Mark articles as **"Interested"** for papers relevant to your research
- Mark articles as **"Not Interested"** for irrelevant papers
- Aim for at least 100 "Interested" articles out of 1000+ total for initial training

### 4. Train the Model

**Docker users**:

```bash
docker-compose exec app papersorter train
```

**Manual users**:

```bash
papersorter train
```

The model performance (ROC-AUC) will be displayed. A score above 0.8 indicates good performance.

### 5. Deploy Web Interface for Production

For production use, deploy the web interface with a proper WSGI server and HTTPS:

#### Production Deployment (On-Premise)

```bash
# Install uWSGI
pip install uwsgi

# Run with uWSGI
uwsgi --http :5001 --module PaperSorter.web.app:app --processes 4

# Configure reverse proxy (nginx example) with SSL:
# server {
#     listen 443 ssl;
#     server_name your-domain.com;
#     ssl_certificate /path/to/cert.pem;
#     ssl_certificate_key /path/to/key.pem;
#
#     location / {
#         proxy_pass http://localhost:5001;
#         proxy_set_header Host $host;
#         proxy_set_header X-Real-IP $remote_addr;
#     }
# }
```

#### Development/Testing

For local development or testing with external services:

```bash
# Option 1: Local development
papersorter serve --port 5001 --debug

# Option 2: Testing with HTTPS (using ngrok)
papersorter serve --port 5001
ngrok http 5001  # Creates HTTPS tunnel to your local server
```

### 6. Configure Notifications (Slack or Discord)

In the web interface:

- Go to Settings → Channels
- Add a webhook URL (Slack or Discord)
- Set the score threshold (e.g., 0.7)
- Select which model to use

The system automatically detects the webhook type based on the URL:
- **Slack webhooks**: URLs ending with `slack.com`
- **Discord webhooks**: URLs ending with `discord.com` or `discordapp.com`

#### For Slack

Get a webhook URL from your Slack workspace:
1. Go to your Slack App settings or create a new app
2. Enable Incoming Webhooks
3. Create a webhook for your desired channel
4. Copy the webhook URL (format: `https://hooks.slack.com/services/...`)

**Optional: Enable Slack Interactivity**

To add interactive buttons to Slack messages:
1. **Create a Slack App** with Interactive Components enabled
2. **Configure the Request URL** in your Slack App:
   - Set to: `https://your-domain.com/slack-interactivity` (must be HTTPS)

#### For Discord

Get a webhook URL from your Discord server:
1. Go to your Discord channel settings
2. Navigate to Integrations → Webhooks
3. Create a new webhook or use an existing one
4. Copy the webhook URL (format: `https://discord.com/api/webhooks/...`)

Discord notifications include:
- Rich embeds with color-coded scores (green/yellow/red)
- Visual score indicators (🟢🟡🔴)
- Markdown-formatted action links
- Timestamp and model information

### 7. Regular Operation
**Docker users**:

```bash
# Fetch new articles and generate predictions (every 3 hours)
docker-compose exec app papersorter update

# Send Slack notifications for high-scoring articles (every 3 hours, 7am-9pm)
docker-compose exec app papersorter broadcast
```

Set up these commands to run periodically (e.g., via cron):

**Manual users**:

```bash
# Fetch new articles and generate predictions (every 3 hours)
papersorter update

# Send notifications for high-scoring articles (run hourly - channels have individual hour restrictions)
papersorter broadcast
```

Example cron configuration (see `examples/` directory for complete scripts with log rotation):

```cron
30 */3 * * * /path/to/papersorter/examples/cron-update.sh
0 * * * * /path/to/papersorter/examples/cron-broadcast.sh  # Run every hour
```

**Note**: Broadcast hours are now configured per channel in the web interface. The broadcast task can run every hour and will automatically skip channels outside their configured broadcast hours.

## Scholarly Database Providers

PaperSorter can enrich article metadata using either Semantic Scholar or OpenAlex:

### Semantic Scholar
- **Pros**: Provides TL;DR summaries, comprehensive metadata
- **Cons**: Requires API key (free with registration)
- **Best for**: Users who want article summaries
- **Configuration**:
  ```yaml
  scholarly_database:
    provider: "semantic_scholar"
    semantic_scholar:
      api_key: "your_api_key"
  ```

### OpenAlex
- **Pros**: No API key required, just email address; larger database
- **Cons**: No TL;DR summaries
- **Best for**: Quick setup, broader coverage
- **Configuration**:
  ```yaml
  scholarly_database:
    provider: "openalex"
    openalex:
      email: "your_email@example.com"  # Must be valid
  ```

Both providers will enrich your RSS feed articles with:
- Corrected author names
- Journal/venue information
- Full abstracts
- Publication dates

## Command Reference

### Core Commands

- `papersorter init` - Initialize database schema
- `papersorter update` - Fetch new articles and generate embeddings
- `papersorter train` - Train or retrain the prediction model
- `papersorter broadcast` - Send notifications (Slack/Discord) for interesting articles
- `papersorter serve` - Start the web interface for labeling and configuration

### Docker Commands

When using Docker, prefix commands with `docker-compose exec app`:

```bash
# Example: Update articles
docker-compose exec app papersorter update

# Example: Train model
docker-compose exec app papersorter train
```

### Common Options

All commands support:

- `--config PATH` - Configuration file path (default: config.yml)
- `--log-file PATH` - Log output to file
- `-q, --quiet` - Suppress console output

### Command-Specific Options

**update:**

- `--batch-size N` - Processing batch size
- `--limit-sources N` - Maximum number of feed sources to process
- `--check-interval-hours N` - Hours between checks for the same feed

**train:**

- `-r, --rounds N` - XGBoost training rounds (default: 100)
- `-o, --output PATH` - Model output file (default: model.pkl)
- `--embeddings-table NAME` - Embeddings table name (default: embeddings)

**broadcast:**

- `--limit N` - Maximum items to process per channel
- `--max-content-length N` - Maximum content length for messages
- `--clear-old-days N` - Clear broadcasts older than N days (default: 30)

**serve:**

- `--host ADDRESS` - Bind address (default: 0.0.0.0)
- `--port N` - Port number (default: 5001)
- `--debug` - Enable Flask debug mode

## Web Interface Features

The web interface provides:

### Main Feed View

- Browse all articles with predictions
- Interactive labeling (Interested/Not Interested)
- Semantic article search
- Shareable search URLs
- Filter by date, score, or label status

### Article Features

- View full abstracts and metadata
- Find similar articles
- Direct links to paper PDFs
- Semantic Scholar integration for citations

### AI-Powered Tools

- Generate article summaries
- Create visual infographics for article collections

### Admin Settings

- Manage feed sources
- Configure notification channels
- View model performance
- User management
- System event logs

## Improving Model Performance

1. **Regular labeling**: Continue labeling new articles through the web interface
2. **Balanced labels**: Maintain a good ratio of positive/negative examples
3. **Retrain periodically**: Run `papersorter train` after adding new labels
4. **Monitor performance**: Check ROC-AUC scores and adjust thresholds accordingly

## Architecture Overview

PaperSorter consists of several key components that work together to fetch, analyze, and distribute academic papers:

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                            EXTERNAL SOURCES / SERVICES                         │
├────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ RSS/Atom     │  │ Embedding    │  │ Chat API     │  │ Scholarly APIs     │  │
│  │ Feeds        │  │ API          │  │ (OpenAI-     │  │ • Semantic Scholar │  │
│  │ • arXiv      │  │ (OpenAI-     │  │  compatible) │  │ • OpenAlex         │  │
│  │ • bioRxiv    │  │  compatible) │  │              │  │                    │  │
│  │ • PubMed     │  │              │  │ AI Summary   │  │ Paper Metadata     │  │
│  │ • Journals   │  │ Text Analysis│  │ Generation   │  │ Enrichment         │  │
│  └──────┬───────┘  └──────▲───────┘  └──────▲───────┘  └─────────▲──────────┘  │
└─────────┼─────────────────┼─────────────────┼────────────────────┼─────────────┘
          ▼                 │                 │                    │
  ┌────────────────────────────────────────────────────────────────────────┐
  │                        PAPERSORTER CORE SYSTEM                         │
  ├────────────────────────────────────────────────────────────────────────┤
  │  ┌─────────────────────── Background Workflows ─────────────────────┐  │
  │  │  ┌─────────────────┐   ┌──────────────────┐  ┌────────────────┐  │  │
  │  │  │ Update Task     │   │ Train Task       │  │ Broadcast Task │  │  │
  │  │  │ • RSS Retrieval │   │ • XGBoost        │  │ • Notification │  │  │
  │  │  │ • Embedding     │──▶│   Classification │  │   Dispatch     │  │  │
  │  │  │   Generation    │   │ • Model          │  │ • Queue        │  │  │
  │  │  │ • Queue Mgmt    │   │   Training       │  │   Processing   │  │  │
  │  │  └────────┬────────┘   └────────▲─────────┘  └────────┬───────┘  │  │
  │  └───────────┼─────────────────────┼─────────────────────┼──────────┘  │
  │              ▼                     │                     ▼             │
  │      ┌─────────────────────────────────────────────────────────────┐   │
  │      │          PostgreSQL Database + pgvector extension           │   │
  │      │  ┌───────────────────────────────────────────────────────┐  │   │
  │      │  │ • Articles      • Embeddings     • User Preferences   │  │   │
  │      │  │ • Predictions   • Channels       • Broadcast Queue    │  │   │
  │      │  └───────────────────────────────────────────────────────┘  │   │
  │      └──────────────────────────▲──────────────────────────────────┘   │
  │      ┌──────────────────────────┴─────────────────────────────────┐    │
  │      │              Web Interface (Flask Application)             │    │
  │      │  ┌─────────────────────────────────────────────────────┐   │    │
  │      │  │ • Feed Display             • Article Labeling       │   │    │
  │      │  │ • Search Interface         • Admin Settings         │   │    │
  │      │  └─────────────────────────────────────────────────────┘   │    │
  │      └─────────────────────▲─────────┬────────────────────────────┘    │
  └────────────────────────────┼─────────┼─────────────────────────────────┘
   ┌───── OAuth Providers ─────▼──┐  ┌───▼─── Notification Services ─────┐
   │  ┌──────────┐  ┌──────────┐  │  │  ┌──────────┐  ┌──────────┐       │
   │  │  Google  │  │  GitHub  │  │  │  │  Slack   │  │ Discord  │       │
   │  │  OAuth   │  │  OAuth   │  │  │  │(Optional)│  │(Optional)│       │
   │  └──────────┘  └──────────┘  │  │  └──────────┘  └──────────┘       │
   │         ┌──────────┐         │  │       ┌────────────────────────┐  │
   │         │  ORCID   │         │  │       │ SMTP Server (Optional) │  │
   │         │  OAuth   │         │  │       │  Email Notifications   │  │
   │         └──────────┘         │  │       └────────────────────────┘  │
   └──────────────────────────────┘  └───────────────────────────────────┘
```

### Key Components:

- **Feed Provider System**: Modular architecture for different feed sources (RSS/Atom)
- **Background Workflows**: 
  - Update Task: Fetches articles, generates embeddings, manages broadcast queue
  - Train Task: Trains XGBoost model using labeled data
  - Broadcast Task: Processes queue and sends notifications
- **Embedding Pipeline**: Generates vector representations using OpenAI-compatible APIs
- **ML Predictor**: XGBoost model trained on user preferences for interest prediction
- **PostgreSQL + pgvector**: Efficient storage and similarity search for embeddings
- **Flask Web Application**: Modern interface with OAuth authentication (ORCID, Google, GitHub)
- **Notification System**: Multi-channel support for Slack, Discord, and email notifications

## Troubleshooting

- **"Authentication failed" error**: Check that your redirect URI exactly matches what's configured in Google Cloud Console
- **Database connection errors**: Verify your database configuration in `config.yml`
- **pgvector extension missing**: Install the pgvector extension in your PostgreSQL database

## License

MIT License - see LICENSE file for details

## Author

Hyeshik Chang <hyeshik@snu.ac.kr>

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests on [GitHub](https://github.com/ChangLabSNU/PaperSorter).