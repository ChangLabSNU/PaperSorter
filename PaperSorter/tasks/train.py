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
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
import xgboost as xgb
import numpy as np
import click
import pickle
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
import yaml


@click.option(
    "--config", "-c", default="./config.yml", help="Database configuration file."
)
@click.option("-o", "--output", help="Output file path. Mutually exclusive with --name.")
@click.option("--name", help="Model name for database registration. Mutually exclusive with --output.")
@click.option("-r", "--rounds", default=1000, help="Number of boosting rounds.")
@click.option("--user-id", "-u", multiple=True, type=int, help="User ID(s) for training preferences. Can be specified multiple times. If omitted, uses all users.")
@click.option(
    "--pos-cutoff",
    default=0.5,
    help="Predicted score cutoff for positive pseudo-labels.",
)
@click.option(
    "--neg-cutoff",
    default=0.2,
    help="Predicted score cutoff for negative pseudo-labels.",
)
@click.option("--pseudo-weight", default=0.5, help="Weight for pseudo-labeled data.")
@click.option(
    "--embeddings-table",
    default="embeddings",
    help="Name of the embeddings table to use.",
)
@click.option("--log-file", default=None, help="Log file.")
@click.option("-q", "--quiet", is_flag=True, help="Suppress log output.")
def main(
    config,
    output,
    name,
    rounds,
    user_id,  # This will be a tuple of user IDs or empty tuple
    pos_cutoff,
    neg_cutoff,
    pseudo_weight,
    embeddings_table,
    log_file,
    quiet,
):
    """Train XGBoost model on labeled paper preferences.
    
    Trains a machine learning model to predict user interest in papers based on
    their labeled preferences. Supports initial training with only positive labels.
    """
    initialize_logging(task="train", logfile=log_file, quiet=quiet)

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
    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Register pgvector extension
    register_vector(db)

    # Query to get all feeds with their embeddings, preferences, and predicted scores
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

    # Use psycopg2.sql to safely insert table name
    from psycopg2 import sql

    # Build the WHERE clause for user filtering
    if user_ids:
        # Use IN clause for multiple user IDs
        where_clause = sql.SQL("WHERE user_id = ANY(%s)")
        query_params = (user_ids,)
    else:
        # No WHERE clause - get all users
        where_clause = sql.SQL("")
        query_params = ()

    query = sql.SQL("""
        WITH latest_preferences AS (
            SELECT DISTINCT ON (feed_id, user_id)
                feed_id, user_id, score, time, source
            FROM preferences
            {where_clause}
            ORDER BY feed_id, user_id, time DESC
        ),
        aggregated_preferences AS (
            -- Aggregate preferences across multiple users
            SELECT
                feed_id,
                AVG(score) as preference_score,
                MAX(time) as preference_time,
                STRING_AGG(DISTINCT source::text, ', ') as preference_source,
                COUNT(DISTINCT user_id) as user_count
            FROM latest_preferences
            GROUP BY feed_id
        )
        SELECT
            f.id as feed_id,
            f.external_id,
            f.title,
            f.published,
            ap.preference_score,
            ap.preference_time,
            ap.preference_source,
            ap.user_count,
            pp.score as predicted_score,
            e.embedding
        FROM feeds f
        JOIN {embeddings_table} e ON f.id = e.feed_id
        LEFT JOIN aggregated_preferences ap ON f.id = ap.feed_id
        LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = 1
        ORDER BY f.id
    """).format(
        where_clause=where_clause,
        embeddings_table=sql.Identifier(embeddings_table)
    )

    cursor.execute(query, query_params)

    results = cursor.fetchall()
    cursor.close()
    # Keep db connection open if we need to register the model
    if output:
        db.close()

    if not results:
        log.error("No feeds with embeddings found")
        if not output:
            db.close()
        return

    log.info(f"Found {len(results)} feeds with embeddings")

    # Log information about user coverage if multiple users
    if not user_ids or len(user_ids) > 1:
        feeds_with_labels = sum(1 for r in results if r["preference_score"] is not None)
        multi_user_feeds = sum(1 for r in results if r.get("user_count") is not None and r["user_count"] > 1)
        log.info(f"Feeds with labels: {feeds_with_labels}, Multi-user labeled feeds: {multi_user_feeds}")

    # Prepare data
    feed_ids = []
    embeddings = []
    preference_scores = []
    predicted_scores = []

    for row in results:
        feed_ids.append(row["feed_id"])
        embeddings.append(np.array(row["embedding"], dtype=np.float64))
        preference_scores.append(row["preference_score"])
        predicted_scores.append(row["predicted_score"])

    embeddings = np.array(embeddings, dtype=np.float64)

    # Create masks for different data categories
    pref_available = np.array([p is not None for p in preference_scores])
    pref_notavail_pos = np.array(
        [
            (p is not None and p >= pos_cutoff) and not avail
            for p, avail in zip(predicted_scores, pref_available)
        ]
    )
    pref_notavail_neg = np.array(
        [
            (p is not None and p < neg_cutoff) and not avail
            for p, avail in zip(predicted_scores, pref_available)
        ]
    )

    # Extract data for each category
    embs_with_pref = embeddings[pref_available]
    labels_with_pref = np.array(
        [p for p, avail in zip(preference_scores, pref_available) if avail]
    )
    fids_with_pref = np.array(
        [fid for fid, avail in zip(feed_ids, pref_available) if avail]
    )

    embs_wopref_pos = embeddings[pref_notavail_pos]
    fids_wopref_pos = np.array(
        [fid for fid, pos in zip(feed_ids, pref_notavail_pos) if pos]
    )

    embs_wopref_neg = embeddings[pref_notavail_neg]
    fids_wopref_neg = np.array(
        [fid for fid, neg in zip(feed_ids, pref_notavail_neg) if neg]
    )

    cnt_with_pref = len(embs_with_pref)
    cnt_wopref_pos = len(embs_wopref_pos)
    cnt_wopref_neg = len(embs_wopref_neg)

    # Count actual negative labels in the labeled data
    cnt_negative_labels = sum(1 for score in labels_with_pref if score < 0.5) if cnt_with_pref > 0 else 0

    # Initial training stage: if no negative labels and no negative pseudo-labels,
    # use all unlabeled articles (except positive pseudo-labels) as negative pseudo-labels
    if cnt_negative_labels == 0 and cnt_wopref_neg == 0:
        log.info("Initial training stage detected: No negative labels found")
        log.info("Using all unlabeled articles as negative pseudo-labels")

        # Create mask for all articles without labels and not in positive pseudo-labels
        pref_notavail_neg = np.array([
            not avail and not pos
            for avail, pos in zip(pref_available, pref_notavail_pos)
        ])

        # Re-extract negative pseudo-label data
        embs_wopref_neg = embeddings[pref_notavail_neg]
        fids_wopref_neg = np.array(
            [fid for fid, neg in zip(feed_ids, pref_notavail_neg) if neg]
        )
        cnt_wopref_neg = len(embs_wopref_neg)

    log.info(
        f"Data distribution: {cnt_with_pref} labeled ({cnt_with_pref - cnt_negative_labels} positive, {cnt_negative_labels} negative), "
        f"{cnt_wopref_pos} pseudo-positive, {cnt_wopref_neg} pseudo-negative"
    )

    # Calculate weights for pseudo-labeled data
    wopref_pos_weight = (
        cnt_with_pref / cnt_wopref_pos * pseudo_weight if cnt_wopref_pos > 0 else 0
    )
    wopref_pos_weight = min(
        wopref_pos_weight, 1.0
    )  # Ensure weight does not exceed true label weight

    # For negative pseudo-labels, adjust weight if this is initial training
    if cnt_negative_labels == 0 and cnt_wopref_neg > 0:
        # In initial training, use lower weight for negative pseudo-labels
        # since they are just "everything else" rather than predicted negatives
        wopref_neg_weight = pseudo_weight * 0.5  # Use half the normal pseudo weight
        log.info(f"Initial training: Using reduced weight for negative pseudo-labels")
    else:
        wopref_neg_weight = (
            cnt_with_pref / cnt_wopref_neg * pseudo_weight if cnt_wopref_neg > 0 else 0
        )
        wopref_neg_weight = min(
            wopref_neg_weight, 1.0
        )  # Ensure weight does not exceed true label weight

    log.info(
        f"Pseudo-label weights: positive={wopref_pos_weight:.4f}, negative={wopref_neg_weight:.4f}"
    )

    # Combine all data
    X_all = []
    Y_all = []
    weights_all = []
    fids_all = []

    # Data with preference scores
    if cnt_with_pref > 0:
        X_all.append(embs_with_pref)
        Y_all.append(labels_with_pref)
        weights_all.append(np.ones(cnt_with_pref))
        fids_all.append(fids_with_pref)

    # Data without preference scores (positive)
    if cnt_wopref_pos > 0:
        X_all.append(embs_wopref_pos)
        Y_all.append(np.ones(cnt_wopref_pos))
        weights_all.append(np.full(cnt_wopref_pos, wopref_pos_weight))
        fids_all.append(fids_wopref_pos)

    # Data without preference scores (negative)
    if cnt_wopref_neg > 0:
        X_all.append(embs_wopref_neg)
        Y_all.append(np.zeros(cnt_wopref_neg))
        weights_all.append(np.full(cnt_wopref_neg, wopref_neg_weight))
        fids_all.append(fids_wopref_neg)

    # Combine all data
    X_all = np.vstack(X_all) if X_all else np.array([])
    Y_all = np.hstack(Y_all) if Y_all else np.array([])
    weights_all = np.hstack(weights_all) if weights_all else np.array([])
    fids_all = np.hstack(fids_all) if fids_all else np.array([])

    if len(X_all) == 0:
        log.error("No training data available")
        return

    log.info(f"Total training samples: {len(X_all)}")

    # Shuffle the data
    indices = np.arange(len(X_all))
    np.random.seed(42)  # For reproducibility
    np.random.shuffle(indices)

    X_all = X_all[indices]
    Y_all = Y_all[indices]
    weights_all = weights_all[indices]
    fids_all = fids_all[indices]

    # Scale embeddings
    log.info("Scaling embeddings...")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_all)

    # Split data
    log.info("Splitting data...")
    (
        X_train,
        X_test,
        y_train,
        y_test,
        fids_train,
        fids_test,
        weights_train,
        weights_test,
    ) = train_test_split(
        X_scaled, Y_all, fids_all, weights_all, test_size=0.25, random_state=42
    )

    # Create XGBoost datasets
    dtrain = xgb.DMatrix(X_train, y_train, weight=weights_train)
    dtest = xgb.DMatrix(X_test, y_test, weight=weights_test)

    # Training parameters
    evals = [(dtrain, "train"), (dtest, "validation")]
    params = {
        "objective": "binary:logistic",
        #'device': 'cuda',
        "max_depth": 3,
        "eta": 0.1,  # learning rate
        "eval_metric": ["logloss", "auc"],
        "seed": 42,
    }

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

    # Train final model on full dataset with validation split for early stopping
    log.info("Training final model on full dataset...")

    # Create validation split from full data (20% for validation)
    (
        X_train_final,
        X_val_final,
        y_train_final,
        y_val_final,
        weights_train_final,
        weights_val_final,
    ) = train_test_split(X_scaled, Y_all, weights_all, test_size=0.1, random_state=42)

    # Create XGBoost datasets for final model
    dtrain_final = xgb.DMatrix(X_train_final, y_train_final, weight=weights_train_final)
    dval_final = xgb.DMatrix(X_val_final, y_val_final, weight=weights_val_final)

    # Training with early stopping
    evals_final = [(dtrain_final, "train"), (dval_final, "validation")]

    # Use the best iteration from the test model as a guide
    best_iteration = model.best_iteration
    log.info(f"Using best iteration from test model: {best_iteration}")

    # Train final model
    final_model = xgb.train(
        params=params,
        dtrain=dtrain_final,
        num_boost_round=rounds,
        evals=evals_final,
        verbose_eval=10,
        early_stopping_rounds=50,
    )

    # Save final model
    log.info("Saving final model...")

    if output:
        # Save to specified file path
        pickle.dump(
            {
                "model": final_model,
                "scaler": scaler,
            },
            open(output, "wb"),
        )
        log.info(
            f"Final model saved to {output} (best iteration: {final_model.best_iteration})"
        )
    else:
        # Register model in database and save to models directory
        # Get model directory from config
        model_dir = config_data.get("models", {}).get("path", ".")

        # Ensure model directory exists
        import os
        os.makedirs(model_dir, exist_ok=True)

        # Build notes about the training
        user_info = "all users" if not user_ids else f"user(s): {user_ids}"
        notes = f"Trained on {user_info}, {len(X_all)} samples, ROC-AUC: {rocauc:.3f}"

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
                "model": final_model,
                "scaler": scaler,
            },
            open(model_path, "wb"),
        )

        log.info(
            f"Model registered as '{name}' with ID {model_id}\n"
            f"Model file saved to {model_path} (best iteration: {final_model.best_iteration})"
        )

        # Close database connection
        db.close()
