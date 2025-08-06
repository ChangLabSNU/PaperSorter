#!/usr/bin/env python3
#
# Copyright (c) 2024 Hyeshik Chang
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

from ..feed_database import FeedDatabase
from ..log import log, initialize_logging
import xgboost as xgb
import numpy as np
import click
import pickle
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
import yaml
import openai
import os


def generate_embeddings(feeds_without_embeddings, config_data, feeddb):
    """Generate embeddings for feeds that don't have them yet."""
    embedding_config = config_data.get("embedding_api", {})

    # Set up OpenAI client
    api_key = embedding_config.get("api_key", os.environ.get("OPENAI_API_KEY"))
    api_url = embedding_config.get("api_url", "https://api.openai.com/v1")
    model = embedding_config.get("model", "text-embedding-3-large")

    client = openai.OpenAI(api_key=api_key, base_url=api_url)

    embeddings = []
    for feed in feeds_without_embeddings:
        try:
            # Prepare input text using the same format as update task
            input_text = feeddb.get_formatted_item(feed["id"])

            # Generate embedding
            params = {"model": model, "input": input_text}

            # Add dimensions if specified in config
            dimensions = embedding_config.get("dimensions")
            if dimensions:
                params["dimensions"] = dimensions

            response = client.embeddings.create(**params)

            embedding = response.data[0].embedding
            embeddings.append({"feed_id": feed["id"], "embedding": embedding})

        except Exception as e:
            log.error(f"Failed to generate embedding for feed {feed['id']}: {e}")
            continue

    return embeddings


@click.option(
    "--config", default="qbio/config.yml", help="Database configuration file."
)
@click.option("--count", default=500, help="Number of recent feeds to process.")
@click.option("--batch-size", default=100, help="Batch size for embedding generation.")
@click.option("--log-file", default=None, help="Log file.")
@click.option("-q", "--quiet", is_flag=True, help="Suppress log output.")
def main(config, count, batch_size, log_file, quiet):
    initialize_logging(task="predict", logfile=log_file, quiet=quiet)

    # Load configuration
    with open(config, "r") as f:
        config_data = yaml.safe_load(f)

    db_config = config_data["db"]

    # Initialize FeedDatabase for formatted item generation
    feeddb = FeedDatabase(config)

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

    # Get N most recent feeds by added time
    log.info(f"Fetching {count} most recent feeds...")
    cursor.execute(
        """
        SELECT f.*, e.embedding
        FROM feeds f
        LEFT JOIN embeddings e ON f.id = e.feed_id
        ORDER BY f.added DESC
        LIMIT %s
    """,
        (count,),
    )

    recent_feeds = cursor.fetchall()

    if not recent_feeds:
        log.info("No feeds found")
        return

    # Separate feeds with and without embeddings
    feeds_with_embeddings = []
    feeds_without_embeddings = []

    for feed in recent_feeds:
        if feed["embedding"] is None:
            feeds_without_embeddings.append(feed)
        else:
            feeds_with_embeddings.append(feed)

    log.info(
        f"Found {len(feeds_with_embeddings)} feeds with embeddings, {len(feeds_without_embeddings)} without"
    )

    # Generate embeddings for feeds that don't have them
    if feeds_without_embeddings:
        log.info(f"Generating embeddings for {len(feeds_without_embeddings)} feeds...")

        # Process in batches
        all_new_embeddings = []
        for i in range(0, len(feeds_without_embeddings), batch_size):
            batch = feeds_without_embeddings[i : i + batch_size]
            log.info(
                f"Processing batch {i // batch_size + 1}/{(len(feeds_without_embeddings) + batch_size - 1) // batch_size}"
            )

            new_embeddings = generate_embeddings(batch, config_data, feeddb)
            all_new_embeddings.extend(new_embeddings)

        # Store new embeddings in database
        if all_new_embeddings:
            log.info(f"Storing {len(all_new_embeddings)} new embeddings...")
            for emb_data in all_new_embeddings:
                cursor.execute(
                    """
                    INSERT INTO embeddings (feed_id, embedding)
                    VALUES (%s, %s)
                    ON CONFLICT (feed_id) DO UPDATE
                    SET embedding = EXCLUDED.embedding
                """,
                    (emb_data["feed_id"], emb_data["embedding"]),
                )

            db.commit()

            # Add newly embedded feeds to the list
            for feed in feeds_without_embeddings:
                for emb_data in all_new_embeddings:
                    if emb_data["feed_id"] == feed["id"]:
                        feed["embedding"] = emb_data["embedding"]
                        feeds_with_embeddings.append(feed)
                        break

    # Get all active models
    log.info("Loading active models...")
    cursor.execute("""
        SELECT m.*, c.name as channel_name
        FROM models m
        LEFT JOIN channels c ON m.id = c.model_id
        WHERE m.is_active = TRUE
        ORDER BY m.id
    """)

    active_models = cursor.fetchall()

    if not active_models:
        log.warning("No active models found")
        cursor.close()
        db.close()
        return

    log.info(f"Found {len(active_models)} active models")

    # Get model directory from config
    model_dir = config_data.get("models", {}).get("path", ".")

    # Prepare embeddings array
    feed_ids = [f["id"] for f in feeds_with_embeddings]
    embeddings = np.array(
        [f["embedding"] for f in feeds_with_embeddings], dtype=np.float64
    )

    # Process predictions for each model
    for model_info in active_models:
        model_id = model_info["id"]
        model_path = f"{model_dir}/model-{model_id}.pkl"
        channel_name = model_info["channel_name"] or f"Model {model_id}"

        log.info(f"Processing model {model_id} ({channel_name})...")

        # Find feeds that don't have predictions for this model
        cursor.execute(
            """
            SELECT feed_id
            FROM predicted_preferences
            WHERE model_id = %s AND feed_id = ANY(%s)
        """,
            (model_id, feed_ids),
        )

        already_predicted = {row["feed_id"] for row in cursor.fetchall()}
        feeds_to_predict = [fid for fid in feed_ids if fid not in already_predicted]

        if not feeds_to_predict:
            log.info(f"All feeds already have predictions for model {model_id}")
            continue

        log.info(
            f"Found {len(feeds_to_predict)} feeds without predictions for model {model_id}"
        )

        try:
            # Load model
            with open(model_path, "rb") as f:
                model_data = pickle.load(f)

            model = model_data["model"]
            scaler = model_data["scaler"]

            # Get embeddings for feeds that need predictions
            feed_idx_map = {fid: idx for idx, fid in enumerate(feed_ids)}
            predict_indices = [feed_idx_map[fid] for fid in feeds_to_predict]
            embeddings_to_predict = embeddings[predict_indices]

            # Scale embeddings
            embeddings_scaled = scaler.transform(embeddings_to_predict)

            # Create DMatrix for prediction
            dmatrix = xgb.DMatrix(embeddings_scaled)

            # Predict
            predictions = model.predict(dmatrix)

            # Store predictions in database
            log.info(f"Storing {len(predictions)} predictions for model {model_id}...")

            for feed_id, score in zip(feeds_to_predict, predictions):
                cursor.execute(
                    """
                    INSERT INTO predicted_preferences (feed_id, model_id, score)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (feed_id, model_id) DO UPDATE
                    SET score = EXCLUDED.score
                """,
                    (feed_id, model_id, float(score)),
                )

            db.commit()

            # Log summary statistics
            log.info(
                f"Model {model_id} predictions: min={predictions.min():.3f}, max={predictions.max():.3f}, mean={predictions.mean():.3f}"
            )

        except Exception as e:
            log.error(f"Failed to process model {model_id}: {e}")
            continue

    # Close database connection
    cursor.close()
    db.close()

    log.info("Prediction task completed")
