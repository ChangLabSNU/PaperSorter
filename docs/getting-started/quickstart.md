# Quick Start Guide

Get PaperSorter up and running in 15 minutes! This guide provides the fastest path to a working recommendation system.

## Fast Track Setup (New Users)

### Complete Initial Setup

```bash
# 1. Initialize database
papersorter init

# 2. Import PubMed data (fastest way to get started)
papersorter import pubmed

# 3. Generate embeddings (essential!)
papersorter predict --count 10000

# 4. Start web interface
papersorter serve --skip-authentication yourname@domain.com

# 5. Find and label papers in your field
# Go to http://localhost:5001
# Use search box: "your research keywords"
# Mark 10-20 papers as "Interested"

# 6. Train your first model
papersorter train --name "My First Model"

# 7. Generate predictions
papersorter predict

# Done! Your system is now recommending papers
```

## Alternative: RSS Feed Setup

If you prefer using RSS feeds instead of PubMed:

### Step 1: Add Your First Feed

```bash
# Start the web interface
papersorter serve --skip-authentication yourname@domain.com

# Open browser to http://localhost:5001
# Navigate to Settings > Feed Sources
# Add RSS feeds (e.g., bioRxiv, arXiv, journal feeds)
```

### Step 2: Fetch Papers & Generate Embeddings

```bash
# Fetch new papers from feeds
papersorter update

# Generate embeddings for semantic search
papersorter predict --count 1000

# Check what was fetched
papersorter stats
```

Expected output:
```
Papers in database: 523
Papers with embeddings: 523
Papers labeled: 0
Active feeds: 1
```

### Step 3: Label Papers Using Search

```bash
# Web interface should already be running
# Go to http://localhost:5001

# Use semantic search to find relevant papers:
# - Search: "CRISPR"
# - Search: "machine learning"
# - Search: your specific research area

# Mark papers as:
# 👍 = Interested (for training)
# 👎 = Not Interested (optional, for better accuracy)
```

### Step 4: Train Your First Model

After labeling 10+ papers as "Interested":

```bash
# Train the model (name is required!)
papersorter train --name "Initial Model"

# The system will:
# - Detect you only have positive labels
# - Automatically use unlabeled papers as negatives
# - Create a balanced training set
```

### Step 5: Get Recommendations

```bash
# Process papers and queue notifications
papersorter update

# Send notifications (if configured)
papersorter broadcast
```

## Basic Workflow

### Daily Routine

```bash
# Morning: Fetch new papers and get recommendations
papersorter update
papersorter broadcast

# Throughout the day: Label interesting papers via web UI
# Evening: Retrain model with new labels
papersorter train
```

### Automated Setup (Cron)

```bash
# Edit crontab
crontab -e

# Add these lines:
# Fetch papers every 6 hours
0 */6 * * * /path/to/venv/bin/papersorter update

# Send morning digest at 9 AM
0 9 * * * /path/to/venv/bin/papersorter broadcast

# Retrain model weekly on Sunday night
0 2 * * 0 /path/to/venv/bin/papersorter train
```

## Essential Commands

### Information Commands

```bash
# Show statistics
papersorter stats

# List active feeds
papersorter list-feeds

# Show recent papers
papersorter recent --limit 10

# Search papers
papersorter search "transformer attention"
```

### Management Commands

```bash
# Update papers from feeds
papersorter update [OPTIONS]
  --limit-sources N    # Process only N sources
  --batch-size N       # Papers per batch (default: 50)

# Train model
papersorter train [OPTIONS]
  -r, --rounds N       # XGBoost rounds (default: 100)
  -o, --output FILE    # Model file path

# Send notifications
papersorter broadcast [OPTIONS]
  --limit N            # Max items per channel
  --dry-run           # Preview without sending
```

## Configuration Basics

### Minimal config.yml

```yaml
# Database (required)
db:
  type: postgres
  host: localhost
  user: papersorter
  database: papersorter
  password: "your_password"

# Web interface (required for labeling)
web:
  base_url: "http://localhost:5001"
  flask_secret_key: "generate_random_key_here"

# Embeddings (required for ML)
embedding_api:
  api_key: "your_openai_api_key"
  model: "text-embedding-3-small"  # Cheaper option
```

### Adding Slack Notifications

```yaml
# In web interface: Settings > Channels
# Or add to database directly:
```

```sql
INSERT INTO channels (name, webhook_url, is_active, score_threshold)
VALUES (
  'research-papers',
  'https://hooks.slack.com/services/YOUR/WEBHOOK/URL',
  TRUE,
  3.5  -- Only papers scored > 3.5
);
```

## Quick Tips

### Performance Optimization

```bash
# Process feeds in parallel
papersorter update --parallel --workers 4

# Limit embedding dimensions for faster search
# In config.yml:
embedding_api:
  dimensions: 1536  # Smaller = faster
```

### Debugging Issues

```bash
# Verbose output
papersorter -v update

# Check logs
tail -f papersorter.log

# Test specific component
papersorter test-db
papersorter test-embedding --text "test"
```

### Managing Multiple Models

```bash
# Train model for specific topic
papersorter train -o models/ml_model.pkl --filter "machine learning"

# Use different model for channel
# In database:
UPDATE channels SET model_id = 2 WHERE name = 'ml-papers';
```

## Common Workflows

### Research Group Setup

1. **Shared Database**: Multiple users label papers
2. **Personalized Models**: Each user trains their own model
3. **Group Channels**: Shared Slack channels for different topics

### Personal Research Assistant

1. **Morning Digest**: Daily email with top papers
2. **Weekly Training**: Retrain model with week's labels
3. **Archive Search**: Find similar papers to interesting ones

### Conference Tracking

1. **Conference Feeds**: Add RSS for specific conferences
2. **Deadline Reminders**: Set up notification timing
3. **Collaboration**: Share interesting papers with team

## Troubleshooting Quick Fixes

### No Papers Fetched
```bash
# Check feed is active
papersorter list-feeds --active

# Test feed manually
curl -I "http://arxiv.org/rss/cs"

# Force update
papersorter update --force --limit-sources 1
```

### Model Not Improving
```bash
# Check label distribution
papersorter label-stats

# Need diverse labels (not all 5-star)
# Aim for: 20% five-star, 60% middle, 20% one-star
```

### Notifications Not Sending
```bash
# Test webhook
papersorter test-webhook --channel "channel-name"

# Check broadcast hours (if configured)
# Notifications only send during configured hours
```

## What's Next?

Now that you have PaperSorter running:

1. **Customize**: See [Configuration Guide](../user-guide/configuration.md)
2. **Add Sources**: Learn about [Feed Sources](../user-guide/feed-sources.md)
3. **Improve Model**: Read [Training Models](../user-guide/training-models.md)
4. **Scale Up**: Check [Deployment Guide](../admin-guide/deployment.md)

## Getting Help

- 📖 [Full Documentation](../index.rst)
- 💬 [Community Forum](https://forum.papersorter.org)
- 🐛 [Report Issues](https://github.com/yourusername/papersorter/issues)
- 📧 Email: support@papersorter.org