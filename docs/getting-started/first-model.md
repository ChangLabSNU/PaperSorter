# Training Your First Model

This guide walks you through training your first PaperSorter model to get personalized paper recommendations.

## Understanding the Model

PaperSorter uses **XGBoost regression** to predict your interest in papers:

- **Input**: Paper embeddings (high-dimensional vectors)
- **Output**: Interest score (1-5 scale)
- **Training Data**: Your labeled papers
- **Goal**: Predict which new papers you'll find interesting

## Complete Initial Training Workflow

For new users starting from scratch, follow this step-by-step workflow:

### Step-by-Step Initial Setup

```bash
# 1. Initialize the database
papersorter init

# 2. Import PubMed data (10% sample, ~10,000-20,000 articles)
papersorter import pubmed

# 3. Generate embeddings (crucial step!)
papersorter predict --count 10000

# 4. Start the web interface
papersorter serve --skip-authentication yourname@domain.com

# 5. Find and label papers in your field
# - Use semantic search: "machine learning", "cancer genomics", etc.
# - Mark 10-20 papers as "Interested"

# 6. Train your first model
papersorter train --name "Initial Model"

# 7. Generate predictions
papersorter predict

# 8. Optional: Improve the model
# - Review predictions, mark false positives/negatives
# - Retrain: papersorter train --name "Improved Model"
# - Predict: papersorter predict
```

## Prerequisites

Before training your first model:

1. ✅ Papers in database (via `papersorter import pubmed` or `papersorter update`)
2. ✅ **Embeddings generated** (via `papersorter predict --count 10000`)
3. ✅ At least some papers marked as "interested" (10+ for initial training)
4. ✅ A name for your model (required with `--name` option)

### Why Each Step Matters

- **Import PubMed**: Provides diverse, recent papers for training
- **Generate Embeddings**: Creates vector representations essential for:
  - Semantic search in the interface
  - ML model training
  - Finding similar papers
- **Predict --count 10000**: Processes many articles at once (more efficient than default)

### Initial Training Mode (New Users)
**NEW**: You can now start training with just papers marked as "interested"! The system will automatically:
- Detect when you have only positive labels (interested)
- Use unlabeled articles as negative training examples
- Apply appropriate weights to balance the model

## Step 1: Label Papers

### Using the Web Interface (Recommended)

```bash
# Start the web server
papersorter serve

# Open http://localhost:5001
# Click "Start Labeling"
```

Labeling best practices:
- **Be honest**: Rate based on genuine interest
- **Be consistent**: Use the same criteria throughout
- **Be diverse**: Don't just label papers you love
- **Be thorough**: Read abstracts carefully

### Rating Scale

| Rating | Score | Meaning | Use When |
|--------|-------|---------|----------|
| ⭐⭐⭐⭐⭐ | 5 | Must read | Directly relevant to your research |
| ⭐⭐⭐⭐ | 4 | Very interesting | Would definitely read |
| ⭐⭐⭐ | 3 | Somewhat interesting | Might read later |
| ⭐⭐ | 2 | Not very interesting | Probably won't read |
| ⭐ | 1 | Not interesting | Definitely won't read |

### Quick Labeling Tips

```python
# Bulk label papers by keyword (careful use only!)
from PaperSorter.feed_database import FeedDatabase

db = FeedDatabase()

# Label all papers with "transformer" as interesting
db.execute("""
    INSERT INTO preferences (feed_id, user_id, score, source)
    SELECT id, 'default', 4, 'bulk'
    FROM feeds
    WHERE title ILIKE '%transformer%'
    AND id NOT IN (SELECT feed_id FROM preferences)
""")
```

## Step 2: Check Label Distribution

Before training, verify you have good label diversity:

```bash
papersorter label-stats
```

Good distribution:
```
Score Distribution:
5 (Must read):        15%
4 (Very interesting): 25%
3 (Interesting):      30%
2 (Not interesting):  20%
1 (Not relevant):     10%
```

Warning signs:
- ❌ All papers rated 5 (model will predict everything as interesting)
- ❌ All papers rated 1 (model will predict nothing as interesting)
- ❌ Only extreme ratings (model won't distinguish subtle differences)

## Step 3: Train the Model

### Initial Training (Only Positive Labels)

If you're just starting and have only marked papers as "interested":

```bash
# Train with automatic negative pseudo-labeling
papersorter train --name "Initial Model v1"

# Output:
# Initial training stage detected: No negative labels found
# Using all unlabeled articles as negative pseudo-labels
# Data distribution: 25 labeled (25 positive, 0 negative), 0 pseudo-positive, 975 pseudo-negative
# Initial training: Using reduced weight for negative pseudo-labels
# Training XGBoost model...
# Model registered as 'Initial Model v1' with ID 2
# Model file saved to ./models/model-2.pkl
```

The system automatically:
1. Detects the absence of negative labels
2. Uses all unlabeled articles as negative examples
3. Applies reduced weights (50% of normal) to pseudo-negatives
4. Balances the training to prevent bias

### Basic Training (With Mixed Labels)

```bash
# Train with defaults
papersorter train --name "Production Model v1"

# Output:
# Loading 150 labeled papers...
# Data distribution: 150 labeled (100 positive, 50 negative), 0 pseudo-positive, 0 pseudo-negative
# Splitting: 120 train, 30 test
# Training XGBoost model...
# Rounds: 100
# Best iteration: 87
# Test RMSE: 0.652
# Test R²: 0.743
# Model registered as 'Production Model v1' with ID 3
# Model file saved to ./models/model-3.pkl
```

### Advanced Training Options

```bash
# More training rounds for better accuracy
papersorter train --name "High Accuracy Model" --rounds 500

# Save to specific file instead of database (legacy mode)
papersorter train --output models/my_model.pkl

# Use specific embedding table
papersorter train --name "Alternative Embeddings" --embeddings-table embeddings_v2

# Train on specific user's feedback
papersorter train --name "User1 Personal Model" --user-id 1

# Train on multiple users' feedback (consensus model)
papersorter train --name "Team Consensus" --user-id 1 --user-id 2 --user-id 3

# Train on ALL users' feedback (default when --user-id is omitted)
papersorter train --name "Global Model"

# Verbose output for debugging
papersorter train --name "Debug Model" -v
```

### Model Registration vs File Output

**New behavior (recommended):**
```bash
# Register model in database with automatic ID assignment
papersorter train --name "My Model v1"
# Creates: ./models/model-{id}.pkl
# Registers in database with metadata
```

**Legacy behavior:**
```bash
# Save to specific file without database registration
papersorter train --output custom_model.pkl
# Creates: custom_model.pkl
# No database registration
```

**Note:** You cannot use both `--name` and `--output` together.

### Multi-User Training

When training with multiple users:
- The system averages scores when multiple users label the same paper
- Shows statistics about multi-user labeled feeds
- Creates a consensus model that learns from collective preferences
- Useful for team-wide or department-wide models

### Training Parameters Explained

```python
# In code or config
training_params = {
    'n_estimators': 100,      # Number of trees
    'max_depth': 6,           # Tree depth
    'learning_rate': 0.3,     # Step size
    'subsample': 0.8,         # Data fraction per tree
    'colsample_bytree': 0.8,  # Feature fraction per tree
    'reg_alpha': 0.1,         # L1 regularization
    'reg_lambda': 1.0,        # L2 regularization
}
```

## Step 4: Evaluate the Model

### Understanding Metrics

After training, you'll see:

- **RMSE** (Root Mean Square Error): Lower is better, <0.7 is good
- **R²** (R-squared): Higher is better, >0.7 is good
- **MAE** (Mean Absolute Error): Average prediction error

### Testing Predictions

```bash
# See predictions on recent papers
papersorter predict --recent 10

# Output:
# Title: "Attention Is All You Need Revisited"
# Predicted Score: 4.7 ⭐⭐⭐⭐⭐
#
# Title: "Survey of Classical Mechanics"
# Predicted Score: 1.8 ⭐⭐
```

### Cross-Validation

```python
from PaperSorter.tasks.train import cross_validate_model

# 5-fold cross-validation
scores = cross_validate_model(n_splits=5)
print(f"CV Mean R²: {scores.mean():.3f} (+/- {scores.std():.3f})")
```

## Step 5: Use the Model

### Automatic Recommendations

```bash
# Fetch papers and predict scores
papersorter update

# Papers with score > threshold are queued
# Check the queue:
papersorter queue-status
```

### Manual Prediction

```python
from PaperSorter.predictor import PaperPredictor

predictor = PaperPredictor(model_path='model.pkl')

# Predict for specific paper
score = predictor.predict_paper(paper_id=12345)
print(f"Predicted interest: {score:.1f}/5")

# Get top recommendations
top_papers = predictor.get_recommendations(limit=10)
```

## Step 6: Improve the Model

### Continuous Improvement

```bash
# Weekly routine
every Sunday:
  1. Review week's recommendations
  2. Label false positives/negatives
  3. Retrain model
  4. Compare metrics
```

### A/B Testing

```bash
# Train alternative model
papersorter train -o model_v2.pkl --rounds 200

# Compare models
papersorter compare-models model.pkl model_v2.pkl

# Use different model for testing
UPDATE channels SET model_id = 2 WHERE name = 'test-channel';
```

### Domain-Specific Models

```python
# Train model for specific field
# Filter training data by keywords/sources
papersorter train \
  --filter "machine learning OR deep learning" \
  --output ml_model.pkl
```

## Troubleshooting

### Poor Model Performance

**Symptom**: Low R² score (<0.5)
```bash
# Solutions:
1. Label more papers (aim for 200+)
2. Ensure label diversity
3. Check for data leakage
4. Try different hyperparameters
```

**Symptom**: Overfitting (train >> test performance)
```bash
# Solutions:
papersorter train --rounds 50  # Fewer rounds
papersorter train --max-depth 3  # Shallower trees
```

### Biased Predictions

**Symptom**: Model always predicts same score
```bash
# Check label distribution
papersorter label-stats

# If imbalanced, label more diverse papers
# Consider stratified sampling
```

### Embedding Issues

**Symptom**: All papers get similar scores
```bash
# Check embedding quality
papersorter test-embedding --sample 10

# Try different embedding model
# In config.yml:
embedding_api:
  model: "text-embedding-3-large"  # More powerful
```

## Advanced Techniques

### Feature Engineering

```python
# Add custom features beyond embeddings
features = {
    'author_h_index': get_author_metric(paper),
    'venue_impact': get_venue_score(paper),
    'recency': days_since_published(paper),
    'length': len(paper.abstract),
}
```

### Ensemble Models

```python
# Combine multiple models
models = [
    ('xgboost', XGBoostRegressor()),
    ('random_forest', RandomForestRegressor()),
    ('neural_net', MLPRegressor()),
]

ensemble = VotingRegressor(models)
```

### Active Learning

```python
# Prioritize labeling uncertain papers
uncertainties = predictor.get_uncertainties()
high_uncertainty_papers = uncertainties[:20]
# Label these for maximum model improvement
```

## Model Management

### Versioning

```bash
# Save models with timestamps
papersorter train -o "models/model_$(date +%Y%m%d).pkl"

# Track model performance
echo "$(date),$(papersorter model-metrics)" >> model_history.csv
```

### Backup and Recovery

```bash
# Backup model and labels
tar -czf backup_$(date +%Y%m%d).tar.gz \
  model.pkl \
  config.yml \
  papersorter.db

# Restore from backup
tar -xzf backup_20240115.tar.gz
```

## Next Steps

After training your first model:

1. **Monitor Performance**: Track predictions vs actual interest
2. **Iterate**: Retrain weekly with new labels
3. **Specialize**: Create topic-specific models
4. **Share**: Export model for colleagues

## Tips for Success

1. **Start Simple**: Don't overthink initial labels
2. **Be Patient**: Models improve with more data
3. **Stay Consistent**: Label regularly
4. **Trust the Process**: Even 70% accuracy saves time
5. **Experiment**: Try different settings

## Getting Help

- Check the documentation for advanced techniques
- Review the model management commands for troubleshooting
- Check GitHub issues for community support