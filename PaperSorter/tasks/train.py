#!/usr/bin/env python3
#
# Copyright (c) 2024-2025 Seoul National University
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

from ..log import log, initialize_logging
from ..cli.base import BaseCommand, registry
from ..cli.types import probability_float
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
import xgboost as xgb
import numpy as np
import pickle
import psycopg2
import argparse
import psycopg2.extras
from pgvector.psycopg2 import register_vector
import yaml
from psycopg2 import sql
import os


class TrainCommand(BaseCommand):
    """Train XGBoost model on labeled data."""

    name = 'train'
    help = 'Train XGBoost model on labeled data'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add train-specific arguments."""
        parser.add_argument(
            '-o', '--output',
            help='Output file path. Mutually exclusive with --name'
        )
        parser.add_argument(
            '--name',
            help='Model name for database registration. Mutually exclusive with --output'
        )
        parser.add_argument(
            '-r', '--rounds',
            type=int,
            default=1000,
            help='Number of boosting rounds'
        )
        parser.add_argument(
            '--user-id', '-u',
            action='append',
            type=int,
            help='User ID(s) for training preferences. Can be specified multiple times. If omitted, uses all users'
        )
        parser.add_argument(
            '--base-model',
            type=int,
            help='Model ID to use for pseudo-labeling unlabeled data'
        )
        parser.add_argument(
            '--embeddings-table',
            default='embeddings',
            help='Name of the embeddings table to use'
        )
        parser.add_argument(
            '--pos-cutoff',
            type=probability_float,
            default=0.5,
            help='Threshold for considering feeds as interested (positive labels)'
        )
        parser.add_argument(
            '--neg-cutoff',
            type=probability_float,
            default=0.2,
            help='Threshold for considering feeds as not interested (negative labels)'
        )
        parser.add_argument(
            '--pseudo-weight',
            type=probability_float,
            default=0.5,
            help='Weight for pseudo-labeled data'
        )
        parser.add_argument(
            '--seed',
            type=int,
            default=42,
            help='Random seed for reproducibility'
        )
        parser.add_argument(
            '--max-papers',
            type=int,
            default=100000,
            help='Maximum number of papers to include in training (prioritizes labeled data)'
        )

    def handle(self, args: argparse.Namespace, context) -> int:
        """Execute the train command."""
        initialize_logging('train', args.log_file, args.quiet)
        try:
            main(
                config=args.config,
                output=args.output,
                name=args.name,
                rounds=args.rounds,
                user_id=args.user_id or (),
                base_model=getattr(args, 'base_model', None),
                embeddings_table=args.embeddings_table,
                pos_cutoff=args.pos_cutoff,
                neg_cutoff=args.neg_cutoff,
                pseudo_weight=args.pseudo_weight,
                seed=args.seed,
                max_papers=getattr(args, 'max_papers', None),
                log_file=args.log_file,
                quiet=args.quiet
            )
            return 0
        except Exception as e:
            log.error(f"Train failed: {e}")
            return 1

# Register the command
registry.register(TrainCommand)


def select_training_feeds(db, user_ids, base_model, pos_cutoff, neg_cutoff, max_papers=None, seed=42):
    """Select feed IDs for training based on preferences and pseudolabeling.

    NOTE: This function only selects feed IDs. No embeddings are loaded here
    to minimize memory usage. Embeddings should be loaded separately after
    all selection logic is complete.

    Args:
        db: Database connection
        user_ids: List of user IDs to filter by (None for all users)
        base_model: Optional model ID for pseudolabeling
        pos_cutoff: Threshold for positive pseudo-labels
        neg_cutoff: Threshold for negative pseudo-labels
        max_papers: Maximum number of papers to include
        seed: Random seed for reproducible sampling

    Returns:
        dict: Dictionary with 'labeled' and 'pseudo' lists of feed_ids
    """
    # Build WHERE clause for user filtering
    if user_ids:
        user_where = sql.SQL("WHERE p.user_id = ANY(%s)")
        user_params = (user_ids,)
    else:
        user_where = sql.SQL("")
        user_params = ()

    # Step 1: Get all feeds with user preferences (these have priority)
    # We check for embedding existence but don't load the actual vectors
    labeled_query = sql.SQL("""
        WITH latest_preferences AS (
            SELECT DISTINCT ON (feed_id, user_id)
                feed_id, AVG(score) OVER (PARTITION BY feed_id) as avg_score
            FROM preferences p
            {user_where}
            ORDER BY feed_id, user_id, time DESC
        )
        SELECT DISTINCT lp.feed_id, lp.avg_score
        FROM latest_preferences lp
        INNER JOIN embeddings e ON lp.feed_id = e.feed_id
        ORDER BY lp.feed_id
    """).format(user_where=user_where)

    cursor = db.cursor()
    cursor.execute(labeled_query, user_params if user_ids else ())
    labeled_feeds = [(row[0], row[1]) for row in cursor.fetchall()]
    cursor.close()

    labeled_feed_ids = [fid for fid, _ in labeled_feeds]
    labeled_pos = [fid for fid, score in labeled_feeds if score > 0.5]
    labeled_neg = [fid for fid, score in labeled_feeds if score < 0.5]

    log.info(f"Found {len(labeled_feed_ids)} feeds with user preferences")

    # Step 2: Get pseudolabeled feeds if base_model is specified
    pseudo_positives = []
    pseudo_negatives = []
    if base_model:
        # Get positive pseudo-labels
        # We check for embedding existence but don't load the actual vectors
        pseudo_pos_query = sql.SQL("""
            SELECT pp.feed_id, pp.score
            FROM predicted_preferences pp
            INNER JOIN embeddings e ON pp.feed_id = e.feed_id
            WHERE pp.model_id = %s
              AND pp.score >= %s
              AND pp.feed_id NOT IN %s
            ORDER BY pp.score DESC
        """)

        cursor = db.cursor()
        cursor.execute(pseudo_pos_query,
                      (base_model, pos_cutoff, tuple(labeled_feed_ids) if labeled_feed_ids else (None,)))
        pseudo_pos_feeds = cursor.fetchall()
        cursor.close()

        # Get negative pseudo-labels
        # We check for embedding existence but don't load the actual vectors
        pseudo_neg_query = sql.SQL("""
            SELECT pp.feed_id, pp.score
            FROM predicted_preferences pp
            INNER JOIN embeddings e ON pp.feed_id = e.feed_id
            WHERE pp.model_id = %s
              AND pp.score < %s
              AND pp.feed_id NOT IN %s
            ORDER BY pp.score ASC
        """)

        cursor = db.cursor()
        cursor.execute(pseudo_neg_query,
                      (base_model, neg_cutoff, tuple(labeled_feed_ids) if labeled_feed_ids else (None,)))
        pseudo_neg_feeds = cursor.fetchall()
        cursor.close()

        pseudo_positives = [fid for fid, score in pseudo_pos_feeds]
        pseudo_negatives = [fid for fid, score in pseudo_neg_feeds]

        log.info(f"Found {len(pseudo_positives)} positive and {len(pseudo_negatives)} negative pseudo-labeled feeds")

    # Step 3: Apply max_papers limit if specified
    if max_papers and len(labeled_feed_ids) + len(pseudo_positives) + len(pseudo_negatives) > max_papers:
        # Priority: labeled data > balanced pseudo (equal positive and negative)
        available_for_pseudo = max_papers - len(labeled_feed_ids)

        if available_for_pseudo > 0:
            # Target equal number of positive and negative pseudo samples
            n_each_type = available_for_pseudo // 2

            np.random.seed(seed)
            if len(pseudo_positives) < n_each_type:
                n_pseudo_neg = available_for_pseudo - len(pseudo_positives)
                n_pseudo_pos = len(pseudo_positives)
            elif len(pseudo_negatives) < n_each_type:
                n_pseudo_pos = available_for_pseudo - len(pseudo_negatives)
                n_pseudo_neg = len(pseudo_negatives)
            else:
                n_pseudo_pos = n_each_type
                n_pseudo_neg = n_each_type

            if len(pseudo_positives) > n_pseudo_pos:
                pseudo_positives = np.random.choice(pseudo_positives, n_pseudo_pos, replace=False).tolist()
            if len(pseudo_negatives) > n_pseudo_neg:
                pseudo_negatives = np.random.choice(pseudo_negatives, n_pseudo_neg, replace=False).tolist()

            log.info(f"Limited to {max_papers} total papers: {len(labeled_feed_ids)} labeled + "
                    f"{len(pseudo_positives)} pseudo-positive + {len(pseudo_negatives)} pseudo-negative")
        else:
            pseudo_positives = []
            pseudo_negatives = []
            log.info("Max papers limit reached with labeled data alone")

    return {
        'labeled_pos': labeled_pos,
        'labeled_neg': labeled_neg,
        'pseudo_pos': pseudo_positives,
        'pseudo_neg': pseudo_negatives,
    }


def load_embeddings(db, feed_selection, embeddings_table):
    """Load training data for selected feeds.

    Args:
        db: Database connection
        feed_selection: Dictionary with 'labeled_pos', 'labeled_neg', 'pseudo_pos', 'pseudo_neg' lists
        embeddings_table: Name of the embeddings table

    Returns:
        list: List of dictionaries containing training data records
    """
    # Load embeddings for selected feeds
    query = sql.SQL("""
        SELECT e.embedding
        FROM feeds f
        JOIN {embeddings_table} e ON f.id = e.feed_id
        WHERE f.id = ANY(%s)
        ORDER BY f.id
    """).format(embeddings_table=sql.Identifier(embeddings_table))

    loaded_embeddings = {}
    batch_size = 2000

    for label, itemids in feed_selection.items():
        if not itemids:
            continue

        log.info(f"Loading {len(itemids)} embeddings for {label}...")
        embeddings_batch = []

        for i in range(0, len(itemids), batch_size):
            batch_ids = itemids[i:i+batch_size]
            batch_start = i + 1
            batch_end = min(i + batch_size, len(itemids))

            # Show progress
            log.info(f"  Processing batch {batch_start}-{batch_end} of {len(itemids)} ({label})")

            cursor = db.cursor()
            cursor.execute(query, (batch_ids,))

            partial_table = np.array(cursor.fetchall(), dtype=np.float32)
            embeddings_batch.append(partial_table.squeeze(axis=1))
            cursor.close()

        loaded_embeddings[label] = np.concatenate(embeddings_batch, axis=0)

    total_loaded = sum(map(len, loaded_embeddings.values()))

    log.info(f"Loaded embeddings for {total_loaded} feeds")
    return loaded_embeddings

#    X_scaled, Y_all, weights_all, scaler = prepare_training_data(
#        embeddings, base_model, pseudo_weight, seed)

def prepare_training_data(embeddings, pseudo_weight, seed):
    """Prepare training data from database results.

    Args:
        embeddings: Dictionary with keys 'labeled_pos', 'labeled_neg', 'pseudo_pos', 'pseudo_neg'
                   containing embedding arrays for each category
        pseudo_weight: Weight for pseudo-labeled data (0.0 to 1.0)
        seed: Random seed for reproducibility

    Returns:
        tuple: (X_scaled, Y_all, weights_all, scaler)
    """
    def count_samples(embeddings_dict):
        """Count samples by category."""
        return {
            'labeled_total': len(embeddings_dict.get('labeled_pos', [])) + len(embeddings_dict.get('labeled_neg', [])),
            'labeled_neg': len(embeddings_dict.get('labeled_neg', [])),
            'pseudo_pos': len(embeddings_dict.get('pseudo_pos', [])),
            'pseudo_neg': len(embeddings_dict.get('pseudo_neg', []))
        }

    def calculate_pseudo_weight(n_labeled, n_pseudo, base_weight, max_weight=1.0):
        """Calculate weight for pseudo-labeled samples based on class balance."""
        if n_pseudo == 0:
            return 0.0
        weight = (n_labeled / n_pseudo) * base_weight
        return min(weight, max_weight)

    def determine_negative_pseudo_weight(counts, pseudo_weight):
        """Determine weight for negative pseudo-labels based on training stage."""
        if counts['labeled_neg'] == 0 and counts['pseudo_neg'] > 0:
            # Initial training: no real negative labels, pseudo-negatives are just "unlabeled"
            weight = pseudo_weight * 0.5
            log.info("Initial training: Using reduced weight for negative pseudo-labels")
        elif counts['pseudo_neg'] > 0:
            # Normal training: have some real negative labels
            weight = calculate_pseudo_weight(counts['labeled_total'], counts['pseudo_neg'], pseudo_weight)
        else:
            weight = 0.0
        return weight

    # Count samples
    counts = count_samples(embeddings)

    # Calculate weights
    pseudo_pos_weight = calculate_pseudo_weight(counts['labeled_total'], counts['pseudo_pos'], pseudo_weight)
    pseudo_neg_weight = determine_negative_pseudo_weight(counts, pseudo_weight)

    if counts['pseudo_pos'] > 0 or counts['pseudo_neg'] > 0:
        log.info(f"Pseudo-label weights: positive={pseudo_pos_weight:.4f}, negative={pseudo_neg_weight:.4f}")

    # Define sample categories with their labels and weights
    sample_categories = [
        ("labeled_pos", 1.0, 1.0),           # (category_name, label_value, weight)
        ("labeled_neg", 0.0, 1.0),
        ("pseudo_pos", 1.0, pseudo_pos_weight),
        ("pseudo_neg", 0.0, pseudo_neg_weight)
    ]

    # Combine all embeddings with their labels and weights
    X_parts = []
    Y_parts = []
    weights_parts = []

    for category, label_value, weight in sample_categories:
        if category not in embeddings or weight <= 0:
            continue

        n_samples = len(embeddings[category])
        if n_samples > 0:
            X_parts.append(embeddings[category])
            Y_parts.append(np.full(n_samples, label_value))
            weights_parts.append(np.full(n_samples, weight))
            log.info(f"Added {n_samples} {category} samples (weight={weight:.3f})")

            del embeddings[category]  # Free memory

    # Check if we have any data
    if not X_parts:
        log.error("No training data available")
        return None, None, None, None

    # Combine all parts
    X_all = np.vstack(X_parts)
    del X_parts

    Y_all = np.concatenate(Y_parts)
    del Y_parts

    weights_all = np.concatenate(weights_parts)
    del weights_parts

    # Log statistics
    log.info(f"Total training samples: {len(X_all)}")
    log.info(f"  Positive samples: {np.sum(Y_all == 1)} ({np.sum(Y_all == 1) / len(Y_all) * 100:.1f}%)")
    log.info(f"  Negative samples: {np.sum(Y_all == 0)} ({np.sum(Y_all == 0) / len(Y_all) * 100:.1f}%)")
    log.info(f"  Average weight: {np.mean(weights_all):.3f}")
    log.info(f"  Feature dimensions: {X_all.shape[1]}")

    # Shuffle the data
    np.random.seed(seed)
    indices = np.random.permutation(len(X_all))
    X_all = X_all[indices]
    Y_all = Y_all[indices]
    weights_all = weights_all[indices]

    # Scale embeddings
    log.info("Scaling embeddings...")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_all)

    return X_scaled, Y_all, weights_all, scaler



def train_xgboost_model(X_train, y_train, X_test, y_test, weights_train, weights_test, params, rounds):
    """Train XGBoost model with given data.

    Args:
        X_train: Training features
        y_train: Training labels
        X_test: Test features
        y_test: Test labels
        weights_train: Training weights
        weights_test: Test weights
        params: XGBoost parameters
        rounds: Number of boosting rounds

    Returns:
        tuple: (model, rocauc)
    """
    # Create XGBoost datasets
    dtrain = xgb.DMatrix(X_train, y_train, weight=weights_train)
    dtest = xgb.DMatrix(X_test, y_test, weight=weights_test)

    # Training parameters
    evals = [(dtrain, "train"), (dtest, "validation")]

    # Train model
    log.info("Training XGBoost model...")
    model = xgb.train(
        params=params,
        dtrain=dtrain,
        num_boost_round=rounds,
        evals=evals,
        verbose_eval=10,
        early_stopping_rounds=50,
    )

    # Evaluate model on test set
    log.info("Evaluating model on test set...")
    y_testpred = model.predict(dtest)
    rocauc = roc_auc_score(y_test, y_testpred, sample_weight=weights_test)
    log.info(f"-> Test ROCAUC: {rocauc:.3f}")

    return model, rocauc


def save_model(model, scaler, output, name, rocauc, user_ids, num_samples, config_data, db=None):
    """Save trained model to file or database.

    Args:
        model: Trained XGBoost model
        scaler: StandardScaler used for features
        output: Output file path (if specified)
        name: Model name for database registration (if specified)
        rocauc: Model's ROC-AUC score
        user_ids: User IDs used for training
        num_samples: Number of training samples
        config_data: Configuration dictionary
        db: Database connection (required if name is specified)
    """
    log.info("Saving final model...")

    if output:
        # Save to specified file path
        pickle.dump(
            {
                "model": model,
                "scaler": scaler,
            },
            open(output, "wb"),
        )
        log.info(f"Final model saved to {output} (best iteration: {model.best_iteration})")
    else:
        # Register model in database and save to models directory
        # Get model directory from config
        model_dir = config_data.get("models", {}).get("path", ".")

        # Ensure model directory exists
        os.makedirs(model_dir, exist_ok=True)

        # Build notes about the training
        user_info = "all users" if not user_ids else f"user(s): {user_ids}"
        notes = f"Trained on {user_info}, {num_samples} samples, ROC-AUC: {rocauc:.3f}"

        # Need a new cursor for the insert
        insert_cursor = db.cursor()
        insert_cursor.execute(
            """INSERT INTO models (name, created, is_active, notes)
               VALUES (%s, NOW(), TRUE, %s)
               RETURNING id""",
            (name, notes)
        )

        model_id = insert_cursor.fetchone()[0]
        db.commit()
        insert_cursor.close()

        # Save model file with the ID
        model_path = f"{model_dir}/model-{model_id}.pkl"
        pickle.dump(
            {
                "model": model,
                "scaler": scaler,
            },
            open(model_path, "wb"),
        )

        log.info(
            f"Model registered as '{name}' with ID {model_id}\n"
            f"Model file saved to {model_path} (best iteration: {model.best_iteration})"
        )


def main(
    config,
    output,
    name,
    rounds,
    user_id,  # This will be a tuple of user IDs or empty tuple
    base_model,
    pos_cutoff,
    neg_cutoff,
    pseudo_weight,
    embeddings_table,
    seed,
    max_papers,
    log_file,
    quiet,
):
    """Train XGBoost model on labeled paper preferences.

    Trains a machine learning model to predict user interest in papers based on
    their labeled preferences. Supports initial training with only positive labels.
    """

    # Validate output/name options
    if output and name:
        log.error("Error: --output and --name options are mutually exclusive. Please specify only one.")
        return

    if not output and not name:
        log.error("Error: Either --output or --name must be specified.")
        return

    # Load database configuration
    with open(config, "r") as f:
        config_data = yaml.safe_load(f)

    db_config = config_data["db"]

    # Connect to PostgreSQL
    log.info("Connecting to PostgreSQL database...")
    db = psycopg2.connect(
        host=db_config["host"],
        database=db_config["database"],
        user=db_config["user"],
        password=db_config["password"],
    )

    # Register pgvector extension
    register_vector(db)

    # Convert user_id tuple to list, or use None for all users
    user_ids = list(user_id) if user_id else None

    if user_ids:
        log.info(
            f'Loading training data for user_id(s)={user_ids} using table "{embeddings_table}"...'
        )
    else:
        log.info(
            f'Loading training data for ALL users using table "{embeddings_table}"...'
        )

    # Log pseudolabeling status
    if base_model:
        log.info(f"Pseudolabeling enabled using base model ID: {base_model}")
        log.info(f"Pseudo-label thresholds: positive >= {pos_cutoff}, negative < {neg_cutoff}")
    else:
        log.info("Pseudolabeling disabled (no base model specified)")

    if max_papers:
        log.info(f"Maximum papers limited to: {max_papers}")

    # Step 1: Select feed IDs to use for training
    log.info("Selecting feeds for training...")
    feed_selection = select_training_feeds(
        db, user_ids, base_model, pos_cutoff, neg_cutoff, max_papers, seed
    )

    # Step 2: Load training data for selected feeds
    log.info("Loading training data from database...")
    embeddings = load_embeddings(db, feed_selection, embeddings_table)

    if not embeddings:
        log.error("No papers with embeddings found")
        db.close()
        return

    # Prepare training data
    X_scaled, Y_all, weights_all, scaler = prepare_training_data(
        embeddings, pseudo_weight, seed)

    if X_scaled is None:
        log.error("No training data available")
        db.close()
        return

    # Split data
    log.info("Splitting data...")
    (
        X_train,
        X_test,
        y_train,
        y_test,
        weights_train,
        weights_test,
    ) = train_test_split(
        X_scaled, Y_all, weights_all, test_size=0.25, random_state=seed
    )

    # Define XGBoost parameters
    params = {
        "objective": "binary:logistic",
        #'device': 'cuda',
        "max_depth": 3,
        "eta": 0.1,  # learning rate
        "eval_metric": ["logloss", "auc"],
        "seed": seed,
    }

    # Train initial model
    _, rocauc = train_xgboost_model(
        X_train, y_train, X_test, y_test,
        weights_train, weights_test, params, rounds
    )

    # Train final model on full dataset with validation split for early stopping
    log.info("Training final model on full dataset...")

    # Create validation split from full data (10% for validation)
    (
        X_train_final,
        X_val_final,
        y_train_final,
        y_val_final,
        weights_train_final,
        weights_val_final,
    ) = train_test_split(X_scaled, Y_all, weights_all, test_size=0.1, random_state=seed)

    # Train final model
    final_model, _ = train_xgboost_model(
        X_train_final, y_train_final, X_val_final, y_val_final,
        weights_train_final, weights_val_final, params, rounds
    )

    # Save the model
    save_model(
        final_model, scaler, output, name, rocauc,
        user_ids, len(X_scaled), config_data,
        db if not output else None
    )

    # Close database connection
    if not output:
        db.close()