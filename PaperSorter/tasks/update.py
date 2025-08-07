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
from ..feed_database import FeedDatabase
from ..embedding_database import EmbeddingDatabase
from ..broadcast_channels import BroadcastChannels
from ..feed_predictor import FeedPredictor
from ..log import log, initialize_logging
import xgboost as xgb
from datetime import datetime, timedelta
import time
import requests
import pickle
import click

FEED_EPOCH = (1980, 1, 1)

S2_VENUE_UPDATE_BLACKLIST = {
    "Molecules and Cells",  # Molecular Cell (Cell Press) is incorrectly matched to this.
}


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
    log.debug(f"Items in database: {len(feeddb)}")

    # Initialize RSS provider
    provider = RSSProvider(config)

    # Get sources that need updating
    sources = provider.get_sources(
        source_type="rss", check_interval_hours=check_interval_hours
    )
    log.info(f"Found {len(sources)} RSS sources to update")

    # Apply source limit if specified
    if limit_sources and limit_sources < len(sources):
        sources = sources[:limit_sources]
        log.info(f"Limiting to {limit_sources} sources")

    all_new_items = []

    for source in sources:
        log.info(f"Processing source: {source['name']}")

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


def update_s2_info(feeddb, s2_config, new_item_ids, dateoffset=60):
    if not new_item_ids:
        return

    api_headers = {"X-API-KEY": s2_config["S2_API_KEY"]}
    api_base_url = s2_config.get(
        "S2_API_URL", "https://api.semanticscholar.org/graph/v1/paper"
    )
    api_url = f"{api_base_url}/search/match"

    log.info(
        f"Retrieving Semantic Scholar information for {len(new_item_ids)} new items..."
    )

    # Convert external_ids to feed_ids
    feed_ids = []
    for external_id in new_item_ids:
        feeddb.cursor.execute(
            "SELECT id FROM feeds WHERE external_id = %s", (external_id,)
        )
        result = feeddb.cursor.fetchone()
        if result:
            feed_ids.append(result["id"])

    for feed_id in feed_ids:
        time.sleep(s2_config["S2_THROTTLE"])

        feedinfo = feeddb[feed_id]
        if not feedinfo:
            continue

        pubdate = datetime.fromtimestamp(feedinfo["published"])

        date_from = pubdate - timedelta(days=dateoffset)
        date_to = pubdate + timedelta(days=dateoffset)
        date_range = (
            f"{date_from.year}-{date_from.month:02d}-{date_from.day:02d}:"
            f"{date_to.year}-{date_to.month:02d}-{date_to.day:02d}"
        )

        search_query = {
            "query": feedinfo["title"],
            "publicationDateOrYear": date_range,
            "fields": "title,url,authors,venue,publicationDate,tldr",
        }
        r = requests.get(api_url, headers=api_headers, params=search_query).json()
        if "data" not in r or not r["data"]:
            continue

        s2feed = r["data"][0]
        if s2feed["tldr"] and s2feed["tldr"].get("text"):
            feeddb.update_tldr(feed_id, s2feed["tldr"]["text"])
        if s2feed["authors"]:
            feeddb.update_author(feed_id, format_authors(s2feed["authors"]))
        if (
            s2feed.get("venue") is not None
            and s2feed["venue"].strip()
            and s2feed["venue"] not in S2_VENUE_UPDATE_BLACKLIST
        ):
            feeddb.update_origin(feed_id, s2feed["venue"])

        feeddb.commit()


def format_authors(authors, max_authors=4):
    assert max_authors >= 3

    if len(authors) <= max_authors:
        return ", ".join(author["name"] for author in authors)
    else:
        first_authors = ", ".join(a["name"] for a in authors[: max_authors - 2])
        last_authors = ", ".join(a["name"] for a in authors[-2:])
        return first_authors + ", ..., " + last_authors


def score_new_feeds(feeddb, embeddingdb, channels, model_dir):
    unscored = feeddb.get_unscored_items()

    log.info("Scoring new feeds...")
    log.debug(f"Items to score: {len(unscored)}")

    if not unscored:
        return

    # Get all channels to process items for each channel with its own settings
    all_channels = channels.get_all_channels()
    if not all_channels:
        log.warning("No channels configured")
        return

    # Load models for each channel
    channel_models = {}
    for channel in all_channels:
        model_id = channel["model_id"] or 1  # Default to model 1
        if model_id not in channel_models:
            model_file_path = f"{model_dir}/model-{model_id}.pkl"
            try:
                channel_models[model_id] = pickle.load(open(model_file_path, "rb"))
                log.info(f"Loaded model {model_id} from {model_file_path}")
            except FileNotFoundError:
                log.error(f"Model file not found: {model_file_path}")
                channel_models[model_id] = None
    batchsize = 100

    for bid, batch in enumerate(batched(unscored, batchsize)):
        log.debug(f"Scoring batch: {bid + 1}")
        emb = embeddingdb[batch]

        # KNOWN ISSUE: The current implementation has a problem where if ANY model lacks
        # a score for an item, ALL models will re-score that item. This happens because
        # get_unscored_items() returns items missing scores from ANY active model, not
        # items that are completely unscored. This can lead to unnecessary re-computation
        # when new models are added or activated.
        # TODO: Consider tracking which specific models need scoring for each item.

        # Track which models have been processed to avoid duplicate scoring
        processed_models = set()

        # Score with each channel's model and add to appropriate queues
        for channel in all_channels:
            model_id = channel["model_id"] or 1
            predmodel = channel_models.get(model_id)
            if not predmodel:
                continue

            score_threshold = channel["score_threshold"] or 0.7
            channel_id = channel["id"]

            # Score items if this model hasn't been processed yet
            if model_id not in processed_models:
                emb_xrm = predmodel["scaler"].transform(emb)
                dmtx_pred = xgb.DMatrix(emb_xrm)
                scores = predmodel["model"].predict(dmtx_pred)

                # Update scores and log new items for this model
                for item_id, score in zip(batch, scores):
                    feeddb.update_score(item_id, score, model_id)
                    iteminfo = feeddb[item_id]
                    log.info(
                        f"New item: [{score:.2f}] {iteminfo['origin']} / "
                        f"{iteminfo['title']}"
                    )

                processed_models.add(model_id)
            else:
                # Retrieve already computed scores for this model
                scores = []
                for item_id in batch:
                    feeddb.cursor.execute(
                        """
                        SELECT pp.score
                        FROM feeds f
                        JOIN predicted_preferences pp ON f.id = pp.feed_id
                        WHERE f.external_id = %s AND pp.model_id = %s
                    """,
                        (item_id, model_id),
                    )
                    result = feeddb.cursor.fetchone()
                    scores.append(result["score"] if result else 0.0)

            # Add high-scoring items to this channel's broadcast queue
            for item_id, score in zip(batch, scores):
                if score >= score_threshold:
                    # Get feed_id from external_id
                    feeddb.cursor.execute(
                        "SELECT id FROM feeds WHERE external_id = %s", (item_id,)
                    )
                    result = feeddb.cursor.fetchone()
                    if result:
                        feed_id = result["id"]
                        # Check if already broadcasted
                        feeddb.cursor.execute(
                            """
                            SELECT 1 FROM broadcasts
                            WHERE feed_id = %s AND channel_id = %s
                        """,
                            (feed_id, channel_id),
                        )
                        if not feeddb.cursor.fetchone():
                            feeddb.add_to_broadcast_queue(feed_id, channel_id)
                            iteminfo = feeddb[item_id]
                            log.info(
                                f"Added to channel {channel['name']} queue: {iteminfo['title']}"
                            )

        feeddb.commit()


@click.option(
    "--config", default="./config.yml", help="Database configuration file."
)
@click.option("--batch-size", default=100, help="Batch size for processing.")
@click.option(
    "--limit-sources",
    type=int,
    default=20,
    help="Maximum number of feed sources to scan.",
)
@click.option(
    "--check-interval-hours",
    type=int,
    default=6,
    help="Only check sources not updated within this many hours.",
)
@click.option("--log-file", default=None, help="Log file.")
@click.option("-q", "--quiet", is_flag=True, help="Suppress log output.")
def main(config, batch_size, limit_sources, check_interval_hours, log_file, quiet):
    initialize_logging(task="update", logfile=log_file, quiet=quiet)

    # Load configuration
    import yaml

    with open(config, "r") as f:
        full_config = yaml.safe_load(f)

    date_cutoff = datetime(*FEED_EPOCH).timestamp()
    feeddb = FeedDatabase(config)
    embeddingdb = EmbeddingDatabase(config)
    channels = BroadcastChannels(config)

    # Update feeds from RSS sources
    new_item_ids = update_feeds(
        feeddb,
        date_cutoff,
        config=full_config,
        limit_sources=limit_sources,
        check_interval_hours=check_interval_hours,
    )

    # Update Semantic Scholar info if configured
    if "semanticscholar" in full_config and full_config["semanticscholar"].get(
        "api_key"
    ):
        s2_config = {
            "S2_API_KEY": full_config["semanticscholar"]["api_key"],
            "S2_API_URL": full_config["semanticscholar"].get("api_url"),
            "S2_THROTTLE": full_config["semanticscholar"].get("throttle", 1),
        }
        try:
            update_s2_info(feeddb, s2_config, new_item_ids)
        except requests.exceptions.ConnectionError:
            import traceback

            traceback.print_exc()
            # Show the exception but proceed to the next job.

    num_updates = update_embeddings(feeddb, embeddingdb, config, batch_size)

    if num_updates > 0:
        model_dir = full_config.get("models", {}).get("path", ".")
        score_new_feeds(feeddb, embeddingdb, channels, model_dir)

    log.info("Update completed.")
