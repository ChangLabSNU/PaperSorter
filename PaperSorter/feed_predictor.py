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

import numpy as np
import xgboost as xgb
import pickle
import os
import yaml
import openai
from .log import log


class FeedPredictor:
    """Common functionality for generating embeddings, predicting feed preferences and managing broadcast queues."""

    def __init__(self, feeddb, embeddingdb, config_path='qbio/config.yml'):
        self.feeddb = feeddb
        self.embeddingdb = embeddingdb
        self.config_path = config_path

        # Load configuration
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        # Set up OpenAI client for embeddings
        embedding_config = self.config.get('embedding_api', {})
        self.api_key = embedding_config.get('api_key')
        self.api_url = embedding_config.get('api_url', 'https://api.openai.com/v1')
        self.embedding_model = embedding_config.get('model', 'text-embedding-3-large')
        self.openai_client = openai.OpenAI(api_key=self.api_key, base_url=self.api_url) if self.api_key else None

    def generate_embeddings_batch(self, feed_ids, batch_size=100):
        """
        Generate embeddings for feeds that don't have them yet.

        Args:
            feed_ids: List of feed IDs to process
            batch_size: Size of batches for API calls

        Returns:
            List of feed IDs that successfully got embeddings
        """
        if not self.openai_client:
            log.error("OpenAI client not configured")
            return []

        # Ensure feed_ids is a list
        if not isinstance(feed_ids, list):
            feed_ids = [feed_ids]

        # Filter feeds that need embeddings
        feeds_needing_embeddings = []
        for feed_id in feed_ids:
            # Check if embedding exists by trying to get it
            try:
                self.embeddingdb.cursor.execute('SELECT 1 FROM embeddings WHERE feed_id = %s', (feed_id,))
                if not self.embeddingdb.cursor.fetchone():
                    feeds_needing_embeddings.append(feed_id)
            except Exception:
                feeds_needing_embeddings.append(feed_id)

        if not feeds_needing_embeddings:
            log.info("All feeds already have embeddings")
            return feed_ids

        log.info(f"Generating embeddings for {len(feeds_needing_embeddings)} feeds")

        successful_feeds = []

        # Process in batches
        for i in range(0, len(feeds_needing_embeddings), batch_size):
            batch = feeds_needing_embeddings[i:i + batch_size]

            # Get formatted items for this batch
            formatted_items = []
            feed_id_map = {}

            for idx, feed_id in enumerate(batch):
                formatted_item = self.feeddb.get_formatted_item(feed_id)
                if formatted_item:
                    formatted_items.append(formatted_item)
                    feed_id_map[idx] = feed_id
                else:
                    log.warning(f"Could not get formatted item for feed {feed_id}")

            if not formatted_items:
                continue

            try:
                # Generate embeddings for the batch
                response = self.openai_client.embeddings.create(
                    input=formatted_items,
                    model=self.embedding_model
                )

                # Store embeddings
                for idx, embedding_data in enumerate(response.data):
                    if idx in feed_id_map:
                        feed_id = feed_id_map[idx]
                        # Store embedding in database
                        self.embeddingdb.cursor.execute('''
                            INSERT INTO embeddings (feed_id, embedding)
                            VALUES (%s, %s)
                            ON CONFLICT (feed_id) DO UPDATE
                            SET embedding = EXCLUDED.embedding
                        ''', (feed_id, np.array(embedding_data.embedding)))
                        successful_feeds.append(feed_id)

                log.info(f"Generated embeddings for batch of {len(response.data)} items")

            except Exception as e:
                log.error(f"Failed to generate embeddings for batch: {e}")

        # Commit all embeddings
        if successful_feeds:
            self.embeddingdb.db.commit()

        return successful_feeds

    def predict_and_queue_feeds(self, feed_ids, model_dir, force_rescore=False, batch_size=100):
        """
        Predict preferences for feeds and add high-scoring ones to broadcast queues.
        Automatically generates embeddings for feeds that don't have them.

        Args:
            feed_ids: List of feed IDs to process (can be a single ID in a list)
            model_dir: Directory containing model files
            force_rescore: Whether to force re-scoring of already scored feeds
            batch_size: Size of batches for embedding generation
        """
        if not feed_ids:
            return

        # Ensure feed_ids is a list
        if not isinstance(feed_ids, list):
            feed_ids = [feed_ids]

        # Generate embeddings for feeds that don't have them
        feeds_with_embeddings = self.generate_embeddings_batch(feed_ids, batch_size)

        # Get active channels and their associated models
        self.feeddb.cursor.execute('''
            SELECT c.*, m.id as model_id, m.name as model_name
            FROM channels c
            LEFT JOIN models m ON c.model_id = m.id
            WHERE c.is_active = true
        ''')
        active_channels = self.feeddb.cursor.fetchall()

        if not active_channels:
            log.warning("No active channels found")
            return

        # Group channels by model
        channels_by_model = {}
        for channel in active_channels:
            model_id = channel['model_id'] or 1  # Default to model 1 if not specified
            if model_id not in channels_by_model:
                channels_by_model[model_id] = []
            channels_by_model[model_id].append(channel)

        # Get embeddings for feeds that have them
        embeddings_map = {}
        for feed_id in feeds_with_embeddings:
            self.embeddingdb.cursor.execute('SELECT embedding FROM embeddings WHERE feed_id = %s', (feed_id,))
            result = self.embeddingdb.cursor.fetchone()
            if result:
                embeddings_map[feed_id] = np.array(result['embedding'])
            else:
                log.warning(f"No embedding found for feed {feed_id} even after generation")

        if not embeddings_map:
            log.warning("No embeddings found for any of the provided feeds")
            return

        # Process each model
        for model_id, channels in channels_by_model.items():
            try:
                # Load model
                model_file = os.path.join(model_dir, f'model-{model_id}.pkl')
                if not os.path.exists(model_file):
                    log.warning(f"Model file not found: {model_file}")
                    continue

                with open(model_file, 'rb') as f:
                    model_data = pickle.load(f)

                model = model_data['model']
                scaler = model_data['scaler']

                # Check which feeds need predictions for this model
                feeds_to_predict = []
                if not force_rescore:
                    self.feeddb.cursor.execute('''
                        SELECT feed_id
                        FROM predicted_preferences
                        WHERE model_id = %s AND feed_id = ANY(%s)
                    ''', (model_id, list(embeddings_map.keys())))

                    already_predicted = {row['feed_id'] for row in self.feeddb.cursor.fetchall()}
                    feeds_to_predict = [fid for fid in embeddings_map.keys() if fid not in already_predicted]
                else:
                    feeds_to_predict = list(embeddings_map.keys())

                if not feeds_to_predict:
                    log.info(f"All feeds already have predictions for model {model_id}")
                    continue

                # Prepare embeddings for prediction
                embeddings_array = np.array([embeddings_map[fid] for fid in feeds_to_predict])
                embeddings_scaled = scaler.transform(embeddings_array)

                # Predict
                dmatrix = xgb.DMatrix(embeddings_scaled)
                predictions = model.predict(dmatrix)

                # Store predictions
                for feed_id, score in zip(feeds_to_predict, predictions):
                    self.feeddb.cursor.execute('''
                        INSERT INTO predicted_preferences (feed_id, model_id, score)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (feed_id, model_id) DO UPDATE
                        SET score = EXCLUDED.score
                    ''', (feed_id, model_id, float(score)))

                # Check each channel's threshold and add to broadcast queue
                for channel in channels:
                    score_threshold = channel['score_threshold'] or 0.7
                    channel_id = channel['id']

                    for feed_id, score in zip(feeds_to_predict, predictions):
                        if score >= score_threshold:
                            # Check if already broadcasted
                            self.feeddb.cursor.execute('''
                                SELECT 1 FROM broadcasts
                                WHERE feed_id = %s AND channel_id = %s
                            ''', (feed_id, channel_id))

                            if not self.feeddb.cursor.fetchone():
                                self.feeddb.add_to_broadcast_queue(feed_id, channel_id)

                                # Get feed info for logging
                                self.feeddb.cursor.execute('''
                                    SELECT title FROM feeds WHERE id = %s
                                ''', (feed_id,))
                                feed_info = self.feeddb.cursor.fetchone()
                                if feed_info:
                                    log.info(f'Added to channel {channel["name"]} queue: {feed_info["title"]}')

            except Exception as e:
                log.error(f"Failed to process model {model_id}: {e}")
                continue

        # Commit all changes
        self.feeddb.commit()

    def predict_for_external_ids(self, external_ids, model_dir, force_rescore=False):
        """
        Convenience method for predicting based on external IDs (used by update task).

        Args:
            external_ids: List of external IDs
            model_dir: Directory containing model files
            force_rescore: Whether to force re-scoring
        """
        if not external_ids:
            return

        # Convert external IDs to feed IDs
        feed_ids = []
        for ext_id in external_ids:
            self.feeddb.cursor.execute('SELECT id FROM feeds WHERE external_id = %s', (ext_id,))
            result = self.feeddb.cursor.fetchone()
            if result:
                feed_ids.append(result['id'])

        if feed_ids:
            self.predict_and_queue_feeds(feed_ids, model_dir, force_rescore)