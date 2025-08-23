# CLI Examples and Recipes

This page provides practical examples and recipes for common PaperSorter workflows.

## Basic Operations

### Setting Up a New Installation

```bash
# 1. Initialize database
papersorter test-db

# 2. Add your first feed
papersorter add-feed "arXiv CS" "http://arxiv.org/rss/cs"

# 3. Fetch initial papers
papersorter update --limit-sources 1

# 4. Start labeling
papersorter serve
```

### Daily Research Workflow

```bash
# Morning: Check new papers
papersorter update
papersorter recent --limit 20

# Label interesting papers via web UI
papersorter serve

# Evening: Retrain and notify
papersorter train
papersorter broadcast
```

## Feed Management

### Adding Multiple Feeds

```bash
# Add multiple arXiv categories
for category in cs.LG cs.AI stat.ML; do
    papersorter add-feed "arXiv $category" \
        "http://arxiv.org/rss/$category" \
        --type rss
done

# Add conference proceedings
papersorter add-feed "NeurIPS 2024" \
    "https://proceedings.neurips.cc/rss/2024" \
    --active
```

### Managing Feed Updates

```bash
# Update specific feeds only
papersorter update --limit-sources 3

# Force update despite recent check
papersorter update --force --check-interval-hours 0

# Parallel updates for speed
papersorter update --parallel --workers 8
```

### Disabling Problematic Feeds

```bash
# List all feeds to find ID
papersorter list-feeds

# Disable a feed temporarily
psql -d papersorter -c "UPDATE sources SET is_active = FALSE WHERE id = 5"

# Remove feed and its papers
papersorter remove-feed 5
```

## Model Training

### Initial Model Training

```bash
# Check if ready to train
papersorter stats

# Need at least 50 labeled papers with diversity
# If not enough labels, use web interface:
papersorter serve

# Train first model
papersorter train --rounds 100 --output models/initial.pkl
```

### Improving Model Performance

```bash
# Cross-validation to find best parameters
papersorter cross-validate --folds 5

# Train with more rounds
papersorter train --rounds 500

# Train on recent papers only
papersorter train --filter "published > CURRENT_DATE - INTERVAL '6 months'"
```

### Multiple Models for Different Topics

```bash
# ML-specific model
papersorter train \
    --filter "title ILIKE '%machine learning%' OR title ILIKE '%neural%'" \
    --output models/ml_model.pkl

# Biology-specific model
papersorter train \
    --filter "origin ILIKE '%biorxiv%' OR title ILIKE '%protein%'" \
    --output models/bio_model.pkl
```

## Notification Configuration

### Slack Integration

```bash
# Add Slack channel
papersorter add-channel "research-papers" \
    "https://hooks.slack.com/services/T00/B00/XXX" \
    --type slack \
    --threshold 3.5

# Test the webhook
papersorter test-webhook --channel "research-papers"

# Send test broadcast
papersorter broadcast --channel "research-papers" --dry-run
```

### Email Newsletter Setup

```bash
# Configure email in config.yml first
# Then add email channel
papersorter add-channel "weekly-digest" \
    "your-email@example.com" \
    --type email \
    --threshold 4.0

# Send weekly digest
papersorter broadcast --channel "weekly-digest" --limit 10
```

### Time-Based Notifications

```bash
# Set broadcast hours (9 AM - 5 PM)
psql -d papersorter -c "
UPDATE channels
SET broadcast_hours = '[9, 17]'
WHERE name = 'work-papers'
"

# Morning digest only
psql -d papersorter -c "
UPDATE channels
SET broadcast_hours = '[9, 10]'
WHERE name = 'morning-digest'
"
```

## Search and Discovery

### Finding Papers

```bash
# Text search
papersorter search "transformer attention mechanism"

# Search with filters
papersorter search "BERT" --limit 50

# Semantic similarity search
papersorter search "neural architecture search" --semantic
```

### Exploring Related Papers

```python
# Find papers similar to a specific one
from PaperSorter.feed_database import FeedDatabase

db = FeedDatabase()
similar = db.find_similar_papers(paper_id=12345, limit=10)
for paper in similar:
    print(f"{paper['score']:.2f}: {paper['title']}")
```

## Data Management

### Backup and Restore

```bash
# Full backup
papersorter backup --output backups/full_$(date +%Y%m%d).tar.gz

# Backup without embeddings (smaller)
papersorter backup --output backups/light_$(date +%Y%m%d).tar.gz

# Restore from backup
papersorter restore backups/full_20240115.tar.gz --force
```

### Database Maintenance

```bash
# Clean old data
papersorter cleanup --days 90

# Remove duplicate papers
papersorter cleanup --duplicates

# Optimize database
papersorter vacuum --analyze

# Full vacuum (requires downtime)
papersorter vacuum --full
```

### Exporting Data

```bash
# Export labeled papers for sharing
papersorter export labels --output my_labels.json

# Export papers as CSV
papersorter export papers --format csv --output papers.csv

# Export model for deployment
papersorter export model --output production_model.pkl
```

## Automation Scripts

### Cron Setup

```bash
# Edit crontab
crontab -e

# Add these lines:
# Update papers every 6 hours
0 */6 * * * /path/to/venv/bin/papersorter update --quiet

# Morning broadcast at 9 AM
0 9 * * * /path/to/venv/bin/papersorter broadcast

# Weekly training on Sunday 2 AM
0 2 * * 0 /path/to/venv/bin/papersorter train

# Monthly cleanup
0 3 1 * * /path/to/venv/bin/papersorter cleanup --days 60
```

### Systemd Service

```ini
# /etc/systemd/system/papersorter-web.service
[Unit]
Description=PaperSorter Web Interface
After=network.target postgresql.service

[Service]
Type=simple
User=papersorter
WorkingDirectory=/opt/papersorter
Environment="PATH=/opt/papersorter/venv/bin"
ExecStart=/opt/papersorter/venv/bin/papersorter serve --host 0.0.0.0 --port 5001
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl enable papersorter-web
sudo systemctl start papersorter-web
```

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install -e .

# Run multiple commands
CMD ["sh", "-c", "papersorter update && papersorter broadcast"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  papersorter:
    build: .
    volumes:
      - ./config.yml:/app/config.yml
      - ./models:/app/models
    environment:
      - PAPERSORTER_CONFIG=/app/config.yml
    depends_on:
      - postgres

  postgres:
    image: pgvector/pgvector:pg14
    environment:
      POSTGRES_DB: papersorter
      POSTGRES_USER: papersorter
      POSTGRES_PASSWORD: secret
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

## Troubleshooting Recipes

### Fixing Encoding Issues

```bash
# Export with proper encoding
LANG=en_US.UTF-8 papersorter export papers --output papers.json

# Fix database encoding
psql -d papersorter -c "UPDATE pg_database SET encoding = 'UTF8'"
```

### Recovering from Failed Updates

```bash
# Check last update time
papersorter stats | grep "Last update"

# Reset feed check times
psql -d papersorter -c "UPDATE sources SET last_checked = NULL"

# Force update
papersorter update --force
```

### Debugging Slow Performance

```bash
# Profile update process
python -m cProfile -o profile.stats \
    $(which papersorter) update --limit-sources 1

# Analyze embeddings performance
papersorter test-embedding --sample 100

# Check database indexes
psql -d papersorter -c "\di"
```

## Advanced Workflows

### A/B Testing Models

```bash
# Train two models
papersorter train --output model_a.pkl --rounds 100
papersorter train --output model_b.pkl --rounds 200

# Compare performance
papersorter compare-models model_a.pkl model_b.pkl

# Use different models for different channels
psql -d papersorter -c "
UPDATE channels SET model_id = 1 WHERE name = 'channel_a';
UPDATE channels SET model_id = 2 WHERE name = 'channel_b';
"
```

### Custom Scoring Pipeline

```python
#!/usr/bin/env python
"""Custom scoring with multiple factors"""

from PaperSorter.feed_database import FeedDatabase
from PaperSorter.predictor import PaperPredictor
import numpy as np

db = FeedDatabase()
predictor = PaperPredictor()

# Get recent papers
papers = db.get_recent_papers(days=7)

for paper in papers:
    # ML model score
    ml_score = predictor.predict(paper['id'])

    # Keyword boost
    keyword_score = 0
    keywords = ['transformer', 'attention', 'bert']
    for kw in keywords:
        if kw in paper['title'].lower():
            keyword_score += 1

    # Author reputation (custom logic)
    author_score = get_author_score(paper['authors'])

    # Combine scores
    final_score = (
        0.7 * ml_score +
        0.2 * keyword_score +
        0.1 * author_score
    )

    # Save custom score
    db.save_prediction(paper['id'], final_score, model_id=999)
```

### Collaborative Filtering

```bash
# Export labels from multiple users
for user in alice bob charlie; do
    papersorter export labels --user $user --output ${user}_labels.json
done

# Merge and train ensemble model
python merge_labels.py alice_labels.json bob_labels.json charlie_labels.json
papersorter train --input merged_labels.json --output collaborative_model.pkl
```

## Performance Optimization

### Batch Processing

```bash
# Process in batches to manage memory
papersorter update --batch-size 100

# Parallel processing for speed
papersorter update --parallel --workers $(nproc)
```

### Database Optimization

```sql
-- Add indexes for common queries
CREATE INDEX idx_feeds_published ON feeds(published DESC);
CREATE INDEX idx_preferences_user_score ON preferences(user_id, score);

-- Optimize embedding searches
CREATE INDEX idx_embeddings_vector ON embeddings USING ivfflat (embedding vector_cosine_ops);
```

### Resource Limits

```bash
# Limit memory usage
ulimit -v 4000000  # 4GB limit
papersorter train

# Nice priority for background tasks
nice -n 10 papersorter update

# Timeout for hanging operations
timeout 1h papersorter update
```