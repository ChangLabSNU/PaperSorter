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

from ..providers.rss import RSSProvider
from ..providers.factory import ScholarlyDatabaseFactory
from ..feed_database import FeedDatabase
from ..embedding_database import EmbeddingDatabase
from ..broadcast_channels import BroadcastChannels
from ..feed_predictor import FeedPredictor
from ..cli.base import BaseCommand, registry
from ..log import log, initialize_logging
import xgboost as xgb
from datetime import datetime
import pickle
import argparse


FEED_EPOCH = (1980, 1, 1)

VENUE_UPDATE_BLACKLIST = {
    "Molecules and Cells",  # Molecular Cell (Cell Press) is incorrectly matched to this.
}

class UpdateCommand(BaseCommand):
    """Fetch new articles and queue for broadcast."""

    name = 'update'
    help = 'Fetch new articles from feed sources and queue for broadcast'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add update-specific arguments."""
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Batch size for processing'
        )
        parser.add_argument(
            '--limit-sources',
            type=int,
            help='Limit the number of sources to check (for testing)'
        )
        parser.add_argument(
            '--check-interval-hours',
            type=int,
            default=6,
            help='Only check sources updated more than N hours ago'
        )

    def handle(self, args: argparse.Namespace, context) -> int:
        """Execute the update command."""
        initialize_logging('update', args.log_file, args.quiet)
        try:
            main(
                config=args.config,
                batch_size=args.batch_size,
                limit_sources=args.limit_sources,
                check_interval_hours=args.check_interval_hours,
                log_file=args.log_file,
                quiet=args.quiet
            )
            return 0
        except Exception as e:
            log.error(f"Update failed: {e}")
            return 1

# Register the command
registry.register(UpdateCommand)


def batched(iterable, n):
    items = []
    for item in iterable:
        items.append(item)
        if len(items) == n:
            yield items
            items = []
    if items:
        yield items


def retrieve_items_into_db(db, items_iterator, date_cutoff):
    """Process items from provider and insert into database."""
    new_item_ids = []  # Track newly added items

    for page, items in enumerate(items_iterator):
        log.debug(f"Processing page {page + 1} with {len(items)} items")
        newitems = 0

        for item in items:
            # Check if item already exists
            if item.external_id in db:
                continue

            # Check date cutoff
            if item.published.timestamp() < date_cutoff:
                log.debug(
                    f"Skipping item {item.external_id} due to date cutoff {item.published}."
                )
                continue

            date_formatted = item.published.strftime("%Y-%m-%d %H:%M:%S")
            log.debug(f"Retrieved: [{date_formatted}] {item.title}")

            # Insert into database
            db.insert_feed_item(
                external_id=item.external_id,
                title=item.title,
                content=item.content,
                author=item.author,
                origin=item.origin,
                link=item.link,
                published=item.published.timestamp(),
            )

            new_item_ids.append(item.external_id)
            newitems += 1

        if newitems == 0:
            log.debug(f"Stopping at page {page + 1} due to no new items.")
            break

        db.commit()

    return new_item_ids


def update_feeds(
    feeddb, date_cutoff, config, limit_sources=None, check_interval_hours=24
):
    """Update feeds from all configured sources."""
    log.info("Updating feeds...")
    log.debug(f"Papers in database: {len(feeddb)}")

    # Initialize RSS provider
    provider = RSSProvider(config)

    # Get sources that need updating
    sources = provider.get_sources(
        source_type="rss", check_interval_hours=check_interval_hours
    )
    log.info(f"Found {len(sources)} RSS feeds to update")

    # Apply source limit if specified
    if limit_sources and limit_sources < len(sources):
        sources = sources[:limit_sources]
        log.info(f"Limiting to {limit_sources} feeds")

    all_new_items = []

    for source in sources:
        log.info(f"Processing feed: {source['name']}")

        # Validate source
        if not provider.validate_source(source):
            log.warning(f"Invalid source configuration for {source['name']}")
            continue

        # Get items from source
        since_date = datetime.fromtimestamp(
            date_cutoff, tz=datetime.now().astimezone().tzinfo
        )
        items_iterator = provider.get_items(source, since=since_date)

        # Process items
        new_items = retrieve_items_into_db(
            feeddb, items_iterator, date_cutoff=date_cutoff
        )

        all_new_items.extend(new_items)

        # Update source timestamps
        provider.update_source_timestamp(source["id"], has_new_items=len(new_items) > 0)

    return all_new_items


def update_embeddings(feeddb, embeddingdb, config_path, batch_size):
    """Update embeddings using the unified FeedPredictor implementation."""
    # Get items that need embeddings
    keystoupdate = feeddb.keys().copy()
    keystoupdate -= embeddingdb.keys()

    log.info(
        f"Items: feed_db:{len(feeddb)} "
        f"embedding_db:{len(embeddingdb)} "
        f"to_update:{len(keystoupdate)}"
    )
    if len(keystoupdate) == 0:
        return 0

    log.info("Updating embeddings...")

    # Convert external_ids to feed_ids
    feed_ids_to_update = []
    for external_id in keystoupdate:
        feeddb.cursor.execute(
            "SELECT id FROM feeds WHERE external_id = %s", (external_id,)
        )
        result = feeddb.cursor.fetchone()
        if result:
            feed_ids_to_update.append(result["id"])

    # Use FeedPredictor to generate embeddings
    predictor = FeedPredictor(feeddb, embeddingdb, config_path)
    successful_feeds = predictor.generate_embeddings_batch(feed_ids_to_update, batch_size)

    return len(successful_feeds)


def update_scholarly_info(feeddb, provider, new_item_ids, dateoffset=60):
    """Update article information from scholarly database provider."""
    if not new_item_ids or not provider:
        return

    log.info(
        f"Retrieving {provider.name} information for {len(new_item_ids)} new items..."
    )

    # Convert external_ids to feed_ids with their info
    feed_infos = []
    for external_id in new_item_ids:
        feeddb.cursor.execute(
            "SELECT id, title, published FROM feeds WHERE external_id = %s",
            (external_id,)
        )
        result = feeddb.cursor.fetchone()
        if result:
            feed_infos.append(result)

    for feed_info in feed_infos:
        feed_id = feed_info["id"]
        title = feed_info["title"]
        # Handle both datetime objects and timestamps for backward compatibility
        published = feed_info["published"]
        if isinstance(published, datetime):
            pubdate = published
        else:
            pubdate = datetime.fromtimestamp(published)

        # Search for matching article
        article = provider.match_by_title(
            title,
            publication_date=pubdate,
            date_tolerance_days=dateoffset
        )

        if not article:
            continue

        # Update feed information
        if article.tldr:
            feeddb.update_tldr(feed_id, article.tldr)

        # Update abstract/content if available (especially important for OpenAlex)
        if article.abstract:
            feeddb.update_content(feed_id, article.abstract)

        if article.authors:
            feeddb.update_author(feed_id, article.format_authors())

        if (
            article.venue is not None
            and article.venue.strip()
            and article.venue not in VENUE_UPDATE_BLACKLIST
        ):
            feeddb.update_origin(feed_id, article.venue)

        feeddb.commit()


def _load_model(model_id, model_dir):
    """Load a model from disk.

    Args:
        model_id: The ID of the model to load
        model_dir: Directory containing model files

    Returns:
        Loaded model dictionary or None if loading fails
    """
    model_file_path = f"{model_dir}/model-{model_id}.pkl"
    try:
        with open(model_file_path, "rb") as f:
            model = pickle.load(f)
        log.info(f"Loaded model {model_id} from {model_file_path}")
        return model
    except FileNotFoundError:
        log.error(f"Model file not found: {model_file_path}")
        return None


def _collect_unique_models(channels_list):
    """Extract unique model IDs from channels configuration.

    Args:
        channels_list: List of channel configurations

    Returns:
        Set of unique model IDs that are assigned to channels
    """
    unique_model_ids = set()

    for channel in channels_list:
        model_id = channel.get("model_id")
        if model_id is None:
            log.warning(
                f"Channel '{channel['name']}' (ID: {channel['id']}) "
                f"has no model assigned, skipping"
            )
        else:
            unique_model_ids.add(model_id)

    return unique_model_ids


def _score_items_for_model(model_id, model, feeddb, embeddingdb, batch_size=100):
    """Score all unscored items for a specific model.

    Args:
        model_id: ID of the model
        model: Loaded model dictionary
        feeddb: FeedDatabase instance
        embeddingdb: EmbeddingDatabase instance
        batch_size: Number of items to process in each batch

    Returns:
        Number of items scored
    """
    unscored = feeddb.get_unscored_items(model_id=model_id)

    if not unscored:
        log.debug(f"No items to score for model {model_id}")
        return 0

    log.info(f"Scoring {len(unscored)} papers for model {model_id}")

    for batch_num, batch in enumerate(batched(unscored, batch_size), 1):
        log.debug(f"Model {model_id} - Scoring batch: {batch_num}")

        # Get embeddings for batch
        embeddings = embeddingdb[batch]

        # Transform and predict
        embeddings_transformed = model["scaler"].transform(embeddings)
        dmtx_pred = xgb.DMatrix(embeddings_transformed)
        scores = model["model"].predict(dmtx_pred)

        # Update scores in database
        for item_id, score in zip(batch, scores):
            feeddb.update_score(item_id, score, model_id)
            item_info = feeddb[item_id]
            log.info(
                f"New paper (model {model_id}): [{score:.2f}] "
                f"{item_info['origin']} / {item_info['title']}"
            )

    return len(unscored)


def _queue_high_scoring_items(channel, feeddb, lookback_hours=24):
    """Add high-scoring recent items to broadcast queue for a channel.

    Args:
        channel: Channel configuration dictionary
        feeddb: FeedDatabase instance
        lookback_hours: How many hours back to check for new items

    Returns:
        Number of items added to queue
    """
    model_id = channel.get("model_id")
    if model_id is None:
        return 0

    score_threshold = channel.get("score_threshold", 0.7)
    channel_id = channel["id"]
    channel_name = channel["name"]

    # Query for high-scoring items not already in queue
    feeddb.cursor.execute(
        """
        SELECT f.id as feed_id, f.external_id, pp.score
        FROM feeds f
        JOIN predicted_preferences pp ON f.id = pp.feed_id
        LEFT JOIN broadcasts b ON f.id = b.feed_id AND b.channel_id = %s
        WHERE pp.model_id = %s
            AND pp.score >= %s
            AND b.feed_id IS NULL  -- Not already in broadcast queue
            AND f.added >= CURRENT_TIMESTAMP - INTERVAL '%s hours'
        ORDER BY pp.score DESC
        """,
        (channel_id, model_id, score_threshold, lookback_hours)
    )

    items_to_broadcast = feeddb.cursor.fetchall()

    for item in items_to_broadcast:
        feed_id = item["feed_id"]
        feeddb.add_to_broadcast_queue(feed_id, channel_id)
        log.info(
            f"Added to channel {channel_name} queue: "
            f"score={item['score']:.2f}"
        )

    return len(items_to_broadcast)


def score_new_feeds(feeddb, embeddingdb, channels, model_dir):
    """Score new feeds using active models and queue high-scoring items.

    This function:
    1. Identifies unique models across all channels
    2. Scores unscored items for each model
    3. Queues high-scoring items for broadcast to appropriate channels

    Args:
        feeddb: FeedDatabase instance
        embeddingdb: EmbeddingDatabase instance
        channels: Channels configuration manager
        model_dir: Directory containing model files
    """
    log.info("Scoring new papers...")

    # Get channel configurations
    all_channels = channels.get_all_channels()
    if not all_channels:
        log.warning("No channels configured")
        return

    # Identify unique models needed
    unique_model_ids = _collect_unique_models(all_channels)
    if not unique_model_ids:
        log.error("No channels have valid models assigned. Cannot score feeds.")
        return

    # Score items for each unique model
    total_scored = 0
    for model_id in unique_model_ids:
        model = _load_model(model_id, model_dir)
        if model:
            scored_count = _score_items_for_model(
                model_id, model, feeddb, embeddingdb
            )
            total_scored += scored_count

    if total_scored > 0:
        log.info(f"Scored {total_scored} total items across all models")

    # Queue high-scoring items for each channel
    total_queued = 0
    for channel in all_channels:
        queued_count = _queue_high_scoring_items(channel, feeddb)
        total_queued += queued_count

    if total_queued > 0:
        log.info(f"Queued {total_queued} total items for broadcast")

    feeddb.commit()


def main(config, batch_size, limit_sources, check_interval_hours, log_file, quiet):
    """Fetch new papers from configured RSS/Atom feeds and generate embeddings.

    Updates the database with new articles from all configured feed sources,
    generates embeddings, and queues high-scoring items for broadcast.
    """

    # Load configuration
    import yaml

    with open(config, "r") as f:
        full_config = yaml.safe_load(f)

    date_cutoff = datetime(*FEED_EPOCH).timestamp()
    feeddb = FeedDatabase(config)
    embeddingdb = EmbeddingDatabase(config)
    channels = BroadcastChannels(config)

    # Update feeds from RSS feeds
    new_item_ids = update_feeds(
        feeddb,
        date_cutoff,
        config=full_config,
        limit_sources=limit_sources,
        check_interval_hours=check_interval_hours,
    )

    # Update scholarly database info if configured
    scholarly_config = full_config.get("scholarly_database", {})

    # Backward compatibility: use semanticscholar config if new config doesn't exist
    if not scholarly_config and "semanticscholar" in full_config:
        scholarly_config = {
            "provider": "semantic_scholar",
            "semantic_scholar": full_config["semanticscholar"]
        }

    if scholarly_config:
        provider_name = scholarly_config.get("provider", "semantic_scholar")
        provider_config = scholarly_config.get(provider_name, {})

        # Get date tolerance for automatic matching (default to 60 days)
        # This only affects the update task's automatic metadata enrichment,
        # NOT the web interface search functionality
        match_date_tolerance = scholarly_config.get("match_date_tolerance_days", 60)

        # Create provider
        provider = ScholarlyDatabaseFactory.create_provider(provider_name, provider_config)

        if provider:
            try:
                update_scholarly_info(feeddb, provider, new_item_ids, dateoffset=match_date_tolerance)
            except Exception as e:
                log.error(f"Failed to update {provider.name} info: {e}")
        else:
            log.warning(f"Failed to create {provider_name} provider - skipping scholarly database updates")
    else:
        log.debug("No scholarly database configured - skipping metadata enrichment")

    num_updates = update_embeddings(feeddb, embeddingdb, config, batch_size)

    if num_updates > 0:
        model_dir = full_config.get("models", {}).get("path", ".")
        score_new_feeds(feeddb, embeddingdb, channels, model_dir)

    log.info("Update completed.")
