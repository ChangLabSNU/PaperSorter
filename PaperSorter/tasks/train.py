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
    "--config", default="./config.yml", help="Database configuration file."
)
@click.option("-o", "--output", default="model.pkl", help="Output file name.")
@click.option("-r", "--rounds", default=1000, help="Number of boosting rounds.")
@click.option("--user-id", default=1, help="User ID for training preferences.")
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
    rounds,
    user_id,
    pos_cutoff,
    neg_cutoff,
    pseudo_weight,
    embeddings_table,
    log_file,
    quiet,
):
    """Train a preference model using XGBoost."""
    initialize_logging(task="train", logfile=log_file, quiet=quiet)

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
    log.info(
        f'Loading training data for user_id={user_id} using table "{embeddings_table}"...'
    )

    # Use psycopg2.sql to safely insert table name
    from psycopg2 import sql

    query = sql.SQL("""
        WITH latest_preferences AS (
            SELECT DISTINCT ON (feed_id)
                feed_id, score, time, source
            FROM preferences
            WHERE user_id = %s
            ORDER BY feed_id, time DESC
        )
        SELECT
            f.id as feed_id,
            f.external_id,
            f.title,
            f.published,
            lp.score as preference_score,
            lp.time as preference_time,
            lp.source as preference_source,
            pp.score as predicted_score,
            e.embedding
        FROM feeds f
        JOIN {embeddings_table} e ON f.id = e.feed_id
        LEFT JOIN latest_preferences lp ON f.id = lp.feed_id
        LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = 1
        ORDER BY f.id
    """).format(embeddings_table=sql.Identifier(embeddings_table))

    cursor.execute(query, (user_id,))

    results = cursor.fetchall()
    cursor.close()
    db.close()

    if not results:
        log.error("No feeds with embeddings found")
        return

    log.info(f"Found {len(results)} feeds with embeddings")

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

    log.info(
        f"Data distribution: {cnt_with_pref} labeled, {cnt_wopref_pos} pseudo-positive, {cnt_wopref_neg} pseudo-negative"
    )

    # Calculate weights for pseudo-labeled data
    wopref_pos_weight = (
        cnt_with_pref / cnt_wopref_pos * pseudo_weight if cnt_wopref_pos > 0 else 0
    )
    wopref_pos_weight = min(
        wopref_pos_weight, 1.0
    )  # Ensure weight does not exceed true label weight
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
