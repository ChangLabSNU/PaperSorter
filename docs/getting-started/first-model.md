# Training Your First Model

This guide walks you through training your first PaperSorter model to get personalized paper recommendations.

## Understanding the Model

PaperSorter uses **XGBoost regression** to predict your interest in papers:

- **Input**: Paper embeddings (high-dimensional vectors)
- **Output**: Interest score (1-5 scale)
- **Training Data**: Your labeled papers
- **Goal**: Predict which new papers you'll find interesting

## Prerequisites

Before training your first model:

1. ✅ Papers in database (run `papersorter update`)
2. ✅ At least 50 labeled papers (100+ recommended)
3. ✅ Diverse labels (not all 5-star ratings)

Check your readiness:
```bash
papersorter stats
# Should show:
# Papers labeled: 50+ (minimum)
# Label distribution: Mixed ratings
```

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

### Basic Training

```bash
# Train with defaults
papersorter train

# Output:
# Loading 150 labeled papers...
# Splitting: 120 train, 30 test
# Training XGBoost model...
# Rounds: 100
# Best iteration: 87
# Test RMSE: 0.652
# Test R²: 0.743
# Model saved to model.pkl
```

### Advanced Training Options

```bash
# More training rounds for better accuracy
papersorter train --rounds 500

# Save to specific location
papersorter train --output models/my_model.pkl

# Use specific embedding table
papersorter train --embeddings-table embeddings_v2

# Verbose output for debugging
papersorter train -v
```

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

- Check [Training Guide](../user-guide/training-models.md) for advanced techniques
- See [Model Troubleshooting](../admin-guide/troubleshooting.md#model-issues)
- Join our [ML Discussion Forum](https://forum.papersorter.org/ml)