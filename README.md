# PaperSorter

PaperSorter is an intelligent academic paper recommendation system that helps researchers stay up-to-date with relevant publications. It uses machine learning to filter RSS/Atom feeds and predict which papers match your research interests, then sends notifications to Slack or Discord for high-scoring articles.

<img src="https://github.com/ChangLabSNU/PaperSorter/assets/1702891/5ef2df1f-610b-4272-b496-ecf2a480dda2" width="660px">

## Key Features

- **Multi-source feed aggregation**: Fetches articles from RSS/Atom feeds (PubMed, bioRxiv, journal feeds, etc.)
- **ML-powered filtering**: Uses XGBoost regression on article embeddings to predict interest levels
- **Flexible AI integration**: Compatible with Solar LLM, Gemini, or any OpenAI-compatible generative AI API
- **Web-based labeling interface**: Interactive UI for labeling articles and improving the model
- **Search from PDF (Paper Connect)**: Select text from PDFs to find semantically similar papers
- **Slack & Discord integration**: Automated notifications for interesting papers with customizable thresholds
- **Scholarly database integration**: Choose between Semantic Scholar (with TL;DR summaries) or OpenAlex (no API key needed) for metadata enrichment
- **Multi-channel support**: Different models and thresholds for different research groups or topics
- **AI-powered content generation**: Create concise summaries and visual infographics for article collections

> **📊 Architecture Overview**: For a detailed view of how PaperSorter's components interact, see the [Architecture Overview](#architecture-overview) section below.

## Installation

Install PaperSorter using pip:

```bash
git clone https://github.com/ChangLabSNU/PaperSorter.git

cd PaperSorter
pip install -e .
```

### System Requirements

- Python 3.8+
- PostgreSQL 12+ with pgvector extension
- Modern web browser (for labeling interface)

## Configuration

Create a configuration file at `config.yml` (or specify with `--config`). See `examples/config.yml` for a complete example:

```yaml
# Admin users - automatically promoted to admin on login (never demoted)
admin_users:
  - "admin@example.com"              # For Google/GitHub OAuth
  - "0000-0002-1825-0097@orcid.org"  # For ORCID OAuth

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

## Database Setup

### 1. Create PostgreSQL Database

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

Alternatively, if you have an existing database:

```bash
# Connect to your database and install pgvector
sudo -u postgres psql -d your_database -c "CREATE EXTENSION vector;"
```

### 2. Initialize Database Schema

```bash
papersorter init
```

To reinitialize (drops existing data):

```bash
papersorter init --drop-existing
```

## Getting Started

### Recommended Setup Workflow for New Users

For optimal model performance, follow this comprehensive workflow that uses a two-stage training process:

#### Stage 1: Initial Model Training (Similarity-based)

```bash
# 1. Initialize database
papersorter init

# 2. Import PubMed data with specific ISSNs for your field (target ~10,000 articles)
# Find relevant journal ISSNs from the JOURNALS file or PubMed
papersorter import pubmed --issn 1476-4687 --issn 0036-8075 --issn 1097-6256 --files 20

# 3. Generate embeddings for all imported articles (essential for search and training)
papersorter predict --all  # or --count 10000

# 4. Start web interface
papersorter serve --skip-authentication yourname@domain.com

# 5. Find and label 5-10 diverse "interested" papers using semantic search
# - Go to http://localhost:5001
# - Use search to find papers across different aspects of your research
# - Examples: "CRISPR gene editing", "protein folding", "neural networks"
# - Mark 5-10 papers as "Interested" (diversity is crucial!)

# 6. Create first labeling session based on similarity to interested papers
papersorter labeling create --sample-size 200

# 7. Complete the labeling session in the web interface
# - Go to http://localhost:5001/labeling
# - Label all 200 papers as "Interested" or "Not Interested"

# 8. Train your initial model
papersorter train --name "Initial Model v1"

# 9. Generate predictions with the initial model
papersorter predict
```

#### Stage 2: Model Refinement (Prediction-based) - Highly Recommended

```bash
# 10. Create second labeling session based on model predictions
papersorter labeling create --base-model 1 --sample-size 1000

# 11. Complete the second labeling session
# - Go to http://localhost:5001/labeling
# - Label all 1000 papers (this refines the model significantly)

# 12. Train improved model with larger dataset
papersorter train --name "Production Model v1"

# 13. Generate final predictions
papersorter predict

# 14. Set up notifications and regular operations
# Configure channels, thresholds, and feeds in the web interface
```

**Note**: Stage 2 (steps 10-13) can be omitted but is highly recommended as it:
- Prevents overfitting to the initial small set of papers
- Creates a more generalized model
- Significantly improves prediction accuracy

### Detailed Setup Guide

#### 1. Initialize and Import Data

```bash
# Initialize database
papersorter init

# Import from PubMed (recommended for initial data)
papersorter import pubmed  # Downloads 10 recent files, 10% sampling

# OR fetch from configured RSS feeds
papersorter update
```

#### 2. Generate Embeddings

For initial setup, generate embeddings for many articles:

```bash
# Generate embeddings for up to 10,000 articles
papersorter predict --count 10000
```

This step is crucial as it creates the vector representations needed for:
- Semantic search in the web interface
- Training the ML model
- Finding similar papers

#### 3. Label Training Data

Start the web interface:

```bash
papersorter serve
# Or for development without OAuth:
papersorter serve --skip-authentication yourname@domain.com
```

Navigate to http://localhost:5001 and:
- Use **semantic search** to find papers in your research area
- Mark papers as **"Interested"** (👍) for relevant research
- Initially, you only need positive labels (the system handles the rest)

Tips for effective labeling:
- Search for key terms in your field
- Look for papers from authors you follow
- Check papers from your favorite journals

#### 4. Train the Model

All trained models must be registered with a name:

```bash
# Initial training (only positive labels needed)
papersorter train --name "Initial Model v1"

# The system will:
# - Detect if you have only positive labels
# - Automatically use unlabeled articles as negative examples
# - Apply appropriate weights to balance the training
```

#### 5. Generate Predictions

After training, generate predictions for all articles:

```bash
papersorter predict
```

This will score all articles and queue high-scoring ones for notifications.

#### 6. Iterative Improvement (Optional but Recommended)

For better accuracy, perform a second round:

```bash
# Review predictions in the web interface
# Mark false positives as "Not Interested"
# Mark false negatives as "Interested"

# Retrain with mixed labels
papersorter train --name "Improved Model v2"

# Generate new predictions
papersorter predict
```

### Training Options

```bash
# Train on all users (default)
papersorter train --name "Consensus Model"

# Train on specific users
papersorter train --name "User1 Model" --user-id 1

# Train on multiple specific users
papersorter train --name "Team Model" --user-id 1 --user-id 2 --user-id 3

# Advanced options
papersorter train --name "Advanced Model" --rounds 500 --embeddings-table embeddings_v2
```

### 5. Deploy Web Interface for Production

For production use, deploy the web interface with a proper WSGI server and HTTPS:

#### Production Deployment

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

Set up these commands to run periodically (e.g., via cron):

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

Both providers will enrich your articles with:
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

### Common Options

All commands support:
- `--config PATH` - Configuration file path (default: config.yml)
- `--log-file PATH` - Log output to file
- `-q, --quiet` - Suppress console output

### Command-Specific Options

**update:**
- `--batch-size N` - Processing batch size
- `--limit-sources N` - Maximum number of feeds to process
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
- `--skip-authentication USERNAME` - Bypass OAuth and auto-login as admin user (development only)

## Web Interface Features

The web interface (http://localhost:5001) provides:

### Main Paper View
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

### Search from PDF (Paper Connect)
- Upload and view PDF files directly in browser
- Select text from PDFs to automatically search for similar papers
- Split-pane interface with resizable columns
- No server-side storage - PDFs processed entirely in browser
- Automatic search triggers when selecting 10+ characters

### AI-Powered Tools
- Generate article summaries
- Create visual infographics for article collections

### Admin Settings
- Manage feeds
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
  │      │  │ • Paper List Display       • Paper Labeling         │   │    │
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

- **RSS Feed System**: Modular architecture for different feed sources (RSS/Atom)
- **Background Workflows**:
  - Update Task: Fetches articles, generates embeddings, manages broadcast queue
  - Train Task: Trains XGBoost model using labeled data
  - Broadcast Task: Processes queue and sends notifications
- **Embedding Pipeline**: Generates vector representations using OpenAI-compatible APIs
- **ML Predictor**: XGBoost model trained on user preferences for interest prediction
- **PostgreSQL + pgvector**: Efficient storage and similarity search for embeddings
- **Flask Web Application**: Modern interface with OAuth authentication (ORCID, Google, GitHub)
- **Notification System**: Multi-channel support for Slack, Discord, and email notifications

## License

MIT License - see LICENSE file for details

## Author

Hyeshik Chang <hyeshik@snu.ac.kr>

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests on [GitHub](https://github.com/ChangLabSNU/PaperSorter).