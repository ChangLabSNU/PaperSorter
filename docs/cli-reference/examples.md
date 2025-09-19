# CLI Examples and Recipes

This page provides practical examples and recipes for common PaperSorter workflows.

## Docker vs Manual Commands

All examples show both Docker and manual installation commands:
- **Docker**: Use `./papersorter-cli` wrapper
- **Manual**: Use `papersorter` directly

## Basic Operations

### Setting Up a New Installation

#### Docker Setup
```bash
# 1. Start services
docker-compose up -d

# 2. Initialize database
./papersorter-cli init

# 3. Import initial data
./papersorter-cli import pubmed --files 10

# 4. Generate embeddings
./papersorter-cli predict --count 1000

# 5. Web interface at http://localhost:5001
```

#### Manual Setup
```bash
# 1. Initialize database
papersorter init

# 2. Add your first feed
papersorter add-feed "arXiv CS" "http://arxiv.org/rss/cs"

# 3. Fetch initial papers
papersorter update --limit-sources 1

# 4. Start labeling
papersorter serve
```

### Daily Research Workflow

#### With Docker (Automated)
```bash
# Everything runs automatically via scheduler container
# Just check the web UI at http://localhost:5001

# Manual operations if needed:
./papersorter-cli update
./papersorter-cli recent --limit 20
./papersorter-cli broadcast
```

#### Manual Installation
```bash
# Morning: Check new papers
papersorter update
papersorter recent --limit 20

# Label interesting papers via web UI
papersorter serve

# Evening: Retrain and notify
papersorter train --name "Daily Update"
papersorter broadcast
```

## Feed Management

### Adding Multiple Feeds

```bash
# Docker:
for category in cs.LG cs.AI stat.ML; do
    ./papersorter-cli add-feed "arXiv $category" \
        "http://arxiv.org/rss/$category" \
        --type rss
done

# Manual:
for category in cs.LG cs.AI stat.ML; do
    papersorter add-feed "arXiv $category" \
        "http://arxiv.org/rss/$category" \
        --type rss
done
```

### Managing Feed Updates

```bash
# Docker:
./papersorter-cli update --limit-sources 3
./papersorter-cli update --force --check-interval-hours 0
./papersorter-cli update --parallel --workers 8

# Manual:
papersorter update --limit-sources 3
papersorter update --force --check-interval-hours 0
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
# Docker:
./papersorter-cli stats  # Check readiness
# Web interface at http://localhost:5001 for labeling
./papersorter-cli train --name "Initial Model" --rounds 100

# Manual:
papersorter stats  # Check readiness
papersorter serve  # For labeling
papersorter train --name "Initial Model" --rounds 100
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
from PaperSorter.config import get_config
from PaperSorter.db import DatabaseManager
from PaperSorter.embedding_database import EmbeddingDatabase

config = get_config().raw
db_manager = DatabaseManager.from_config(config["db"], application_name="papersorter-cli-examples")

embedding_db = EmbeddingDatabase(db_manager=db_manager)
try:
    similar = embedding_db.find_similar(
        feed_id=12345,
        limit=10,
        user_id=1,          # replace with your user ID
        model_id=1,         # replace with an active model ID
        channel_id=None,    # optional channel context
    )
    for paper in similar:
        print(f"{paper['similarity']:.2f}: {paper['title']}")
finally:
    embedding_db.close()
    db_manager.close()
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

### Embeddings Management

```bash
# Check embeddings status
papersorter embeddings status

# Get detailed statistics
papersorter embeddings status --detailed

# Clear embeddings before bulk re-import
papersorter embeddings clear --force

# Reset embeddings when changing vector dimensions
# 1. Update config.yml with new dimensions
# 2. Reset the table
papersorter embeddings reset --force

# Optimize bulk embedding generation
# Drop index for faster inserts
papersorter embeddings index off --force

# Generate embeddings for all articles
papersorter predict --all

# Recreate index after bulk operation
papersorter embeddings index on

# Create index with custom parameters for better performance
papersorter embeddings index on --m 32 --ef-construction 128
```

### Embedding Dimension Changes

```bash
# Scenario: Changing from 1536 to 768 dimensions
# 1. Update config.yml:
#    embedding_api:
#      dimensions: 768

# 2. Reset embeddings table
papersorter embeddings reset --force

# 3. Regenerate all embeddings
papersorter predict --all --force

# 4. Retrain models with new embeddings
papersorter train --name "Model with 768D embeddings"
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

## Docker-Specific Operations

### Container Management

```bash
# View logs
./papersorter-cli logs

# Open shell in container
./papersorter-cli shell

# Database shell
./papersorter-cli db-shell

# Restart services
./papersorter-cli restart

# Check status
./papersorter-cli status

# Update Docker images
./papersorter-cli update-image
```

### Docker Backups

```bash
# Backup database
docker-compose exec postgres pg_dump -U papersorter papersorter > backup.sql

# Backup data volume
docker run --rm -v papersorter_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/papersorter-data.tar.gz /data

# Restore database
docker-compose exec -T postgres psql -U papersorter papersorter < backup.sql
```

## Automation Scripts

### Docker (Automatic)

Docker includes automatic scheduling via the scheduler container:
- Update: Every 3 hours
- Broadcast: Every hour
- Predict: Every 6 hours

To customize, edit `docker/cron/crontab` and rebuild:
```bash
docker-compose build scheduler
docker-compose up -d scheduler
```

### Manual Cron Setup

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
"""Custom scoring with multiple factors."""

from PaperSorter.config import get_config
from PaperSorter.db import DatabaseManager
from PaperSorter.feed_database import FeedDatabase
from PaperSorter.embedding_database import EmbeddingDatabase

config = get_config().raw
db_manager = DatabaseManager.from_config(config["db"], application_name="papersorter-custom-scorer")
feeddb = FeedDatabase(db_manager=db_manager)
embeddingdb = EmbeddingDatabase(db_manager=db_manager)

try:
    with db_manager.session() as session:
        cursor = session.cursor(dict_cursor=True)
        cursor.execute(
            """
            SELECT id, title, author
            FROM feeds
            ORDER BY added DESC
            LIMIT 100
            """
        )
        papers = cursor.fetchall()

    keywords = {"transformer", "attention", "bert"}

    for paper in papers:
        ml_score = compute_model_score(paper["id"])  # your custom model here

        keyword_score = sum(1 for kw in keywords if kw in paper["title"].lower())
        author_score = get_author_score(paper["author"])  # your custom logic

        final_score = 0.7 * ml_score + 0.2 * keyword_score + 0.1 * author_score
        feeddb.update_score(paper["id"], final_score, model_id=999)

    feeddb.commit()
finally:
    embeddingdb.close()
    feeddb.close()
    db_manager.close()
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

-- Optimize embedding searches (use papersorter command instead)
-- papersorter embeddings index on
```

### Embedding Performance Optimization

```bash
# For large-scale embedding operations

# 1. Disable index for bulk insert (10x faster inserts)
papersorter embeddings index off

# 2. Generate embeddings in parallel
papersorter predict --all --parallel --workers 8

# 3. Recreate index with optimized parameters
# Higher m = better recall, slower build
# Higher ef_construction = better quality, slower build
papersorter embeddings index on --m 48 --ef-construction 200

# Monitor embedding generation progress
watch -n 5 'papersorter embeddings status | head -10'
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
