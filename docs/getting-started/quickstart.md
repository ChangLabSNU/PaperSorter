# Quick Start Guide

Get PaperSorter up and running with optimal performance using our comprehensive two-stage training workflow.

## Prerequisites

- PostgreSQL 12+ with pgvector extension
- Python 3.8+
- ~10,000 articles for training (provided via PubMed import)

## Complete Setup Workflow

### Stage 1: Initial Model Training (Similarity-based)

#### Step 1: Initialize and Import Data (~5 minutes)

```bash
# Initialize database
papersorter init

# Import PubMed data with specific journal ISSNs for your field
# Target: ~10,000 articles for good model training
# Find ISSNs from JOURNALS file or https://www.ncbi.nlm.nih.gov/nlmcatalog/

# Example for neuroscience/biology:
papersorter import pubmed \
  --issn 1476-4687 \  # Nature
  --issn 0036-8075 \  # Science
  --issn 1097-6256 \  # Nature Neuroscience
  --issn 0896-6273 \  # Neuron
  --files 20          # Download 20 recent update files

# Example for computer science/AI:
papersorter import pubmed \
  --issn 2640-3498 \  # Nature Machine Intelligence
  --issn 1476-4687 \  # Nature
  --files 20
```

#### Step 2: Generate Embeddings (~10 minutes)

```bash
# Generate embeddings for ALL imported articles
# This is essential for semantic search and training
papersorter predict --all

# Alternative if you have limited API credits:
papersorter predict --count 10000
```

#### Step 3: Find Diverse Seed Papers (~10 minutes)

```bash
# Start web interface
papersorter serve --skip-authentication yourname@domain.com

# Open browser to http://localhost:5001
```

**Critical: Label 5-10 diverse "interested" papers**

Use the search box to find papers across different aspects of your research:
- Search for different methodologies (e.g., "CRISPR", "RNA sequencing", "proteomics")
- Search for different topics (e.g., "cancer", "neurodegeneration", "development")
- Search for different model organisms if applicable
- Mark 5-10 papers as "Interested" (👍 button)

**Why diversity matters**: The system will find papers similar to your seed papers. Diverse seeds = broader coverage.

#### Step 4: Create First Labeling Session (~1 minute)

```bash
# Create labeling session with 100-200 papers similar to your interests
papersorter labeling create --sample-size 200

# Output will show:
# - Papers selected from different distance bins
# - Weighted sampling (4:1 ratio favoring similar papers)
# - Link to labeling interface
```

#### Step 5: Complete First Labeling (~20 minutes)

```bash
# Go to http://localhost:5001/labeling
# You'll see a progress bar: [0/200]
```

Label each paper as:
- **Interested** (👍): Papers you'd want to read
- **Not Interested** (👎): Papers you'd skip

Tips for labeling:
- Read title and abstract carefully
- Consider: "Would I save this paper to read later?"
- Be consistent with your criteria
- Don't skip papers - the model needs complete data

#### Step 6: Train Initial Model (~2 minutes)

```bash
# Train your first model
papersorter train --name "Initial Model v1"

# The system will:
# - Use your ~200 labeled papers
# - Balance positive and negative examples
# - Create an XGBoost model
# - Show ROC-AUC score (aim for >0.8)
```

#### Step 7: Generate Initial Predictions (~5 minutes)

```bash
# Generate predictions for all papers
papersorter predict

# This will:
# - Score all papers using your model
# - Queue high-scoring papers for notifications
# - Enable "predicted score" sorting in web UI
```

### Stage 2: Model Refinement (Highly Recommended)

This stage significantly improves model generalization and prevents overfitting.

#### Step 8: Create Prediction-Based Labeling Session (~1 minute)

```bash
# Create larger session based on model predictions
# Uses your Initial Model (ID: 1) to select diverse papers
papersorter labeling create --base-model 1 --sample-size 1000

# This selects papers across the prediction score spectrum:
# - High-scoring papers (to verify true positives)
# - Medium-scoring papers (boundary cases)
# - Low-scoring papers (to verify true negatives)
```

#### Step 9: Complete Second Labeling (~60-90 minutes)

```bash
# Go to http://localhost:5001/labeling
# Progress bar: [0/1000]
```

This larger labeling session:
- Refines the model's understanding of your preferences
- Corrects false positives and false negatives
- Provides much more training data

Take breaks if needed - your progress is saved automatically.

#### Step 10: Train Production Model (~2 minutes)

```bash
# Train refined model with full dataset
papersorter train --name "Production Model v1"

# With ~1200 labeled papers, expect:
# - ROC-AUC score >0.85
# - Better generalization to new papers
# - More consistent predictions
```

#### Step 11: Generate Final Predictions (~5 minutes)

```bash
# Generate predictions with refined model
papersorter predict

# Check model performance in web UI:
# - Sort by predicted score
# - High-scoring papers should match your interests
```

### Stage 3: Configure Notifications

#### Step 12: Set Up Channels

In web interface (Settings → Channels):
```yaml
Channel Name: daily-digest
Webhook URL: https://hooks.slack.com/services/YOUR/WEBHOOK/URL
Score Threshold: 0.7  # Only papers scoring >0.7
Model: Production Model v1
Broadcast Hours: 9-10  # Send between 9-10 AM
```

#### Step 13: Schedule Regular Operations

```bash
# Add to crontab for automation
crontab -e

# Fetch new papers and generate predictions (every 6 hours)
0 */6 * * * /path/to/papersorter update

# Send notifications (every hour - respects broadcast_hours)
0 * * * * /path/to/papersorter broadcast

# Weekly model retraining (Sunday night)
0 2 * * 0 /path/to/papersorter train --name "Weekly Update"
```

## Time Investment Summary

- **Stage 1** (Required): ~45 minutes active time
  - Import & embeddings: 15 min (mostly waiting)
  - Finding seed papers: 10 min
  - First labeling: 20 min

- **Stage 2** (Recommended): ~90 minutes active time
  - Second labeling: 60-90 min
  - Can be split across multiple sessions

- **Total**: ~2.5 hours for a production-ready system

## Expected Results

After completing both stages:
- **Precision**: 80-90% of recommended papers are relevant
- **Recall**: Catches most papers in your field
- **Daily digest**: 2-5 highly relevant papers per day
- **Generalization**: Works well on new journals/topics

## Quick Troubleshooting

### Not enough papers imported
```bash
# Import more files or reduce sampling rate
papersorter import pubmed --files 30 --sample-rate 0.2
```

### Model performance is poor
```bash
# Check label distribution
papersorter labeling stats

# Need balance: aim for 30-40% interested papers
# If too skewed, label more of the minority class
```

### Predictions seem random
```bash
# Ensure embeddings exist for all papers
papersorter predict --all --force

# Retrain with more data
papersorter train --name "Improved Model" --rounds 1500
```

## Advanced Tips

### Using Multiple Models

```bash
# Train specialized models for different topics
papersorter train --name "Cancer Research" --user-id 1
papersorter train --name "Methods Papers" --user-id 2

# Assign different models to different channels
# In web UI: Settings → Channels → Edit → Model Selection
```

### Collaborative Labeling

```bash
# Multiple users can label papers
# Train consensus model using all labels
papersorter train --name "Team Consensus Model"

# Or train on specific users
papersorter train --name "PI Preferences" --user-id 1 --user-id 2
```

### Continuous Improvement

```bash
# Weekly workflow:
# 1. Review the week's recommendations in web UI
# 2. Mark false positives as "Not Interested"
# 3. Search for missed papers and mark as "Interested"
# 4. Retrain model

papersorter train --name "Week $(date +%U) Model"
```

## What's Next?

1. **Fine-tune thresholds**: Adjust score thresholds per channel
2. **Add more sources**: Configure RSS feeds for journals/preprint servers
3. **Explore features**: Try AI summaries, similar paper search, poster generation
4. **Scale up**: Deploy with proper web server and HTTPS

## Getting Help

- Check logs: `tail -f ~/.papersorter/logs/papersorter.log`
- Database issues: `papersorter test-db`
- API issues: `papersorter test-embedding --text "test"`
- Full documentation: [User Guide](../user-guide/index.md)