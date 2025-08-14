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

from ..feed_database import FeedDatabase
from ..log import log, initialize_logging
from ..notification import create_notification_provider, NotificationError
import click
import re
import yaml


def normalize_item_for_display(item, max_content_length):
    # XXX: Fix the source field for the aggregated items.
    if item["origin"] == "QBio Feed Aggregation" and "  " in item["content"]:
        source, content = item["content"].split("  ", 1)
        item["origin"] = source
        item["content"] = normalize_text(content)

    # Replace the abstract content with the TLDR if it's available.
    if item["tldr"] and len(item["tldr"]) >= 5:
        item["content"] = "(tl;dr) " + item["tldr"]

    # Truncate the content if it's too long.
    if len(item["content"]) > max_content_length:
        item["content"] = limit_text_length(item["content"], max_content_length)


def limit_text_length(text, limit):
    if len(text) > limit:
        return text[: limit - 3] + "…"
    return text


def normalize_text(text):
    return re.sub(r"\s+", " ", text).strip()


@click.option("--config", default="./config.yml", help="Database configuration file.")
@click.option(
    "--max-content-length", default=400, help="Maximum length of the content."
)
@click.option(
    "--clear-old-days",
    default=30,
    help="Clear processed items older than this many days.",
)
@click.option("--log-file", default=None, help="Log file.")
@click.option("-q", "--quiet", is_flag=True, help="Suppress log output.")
def main(config, max_content_length, clear_old_days, log_file, quiet):
    initialize_logging(task="broadcast", logfile=log_file, quiet=quiet)

    # Load configuration to get base URL
    with open(config, "r") as f:
        config_data = yaml.safe_load(f)

    base_url = config_data.get("web", {}).get("base_url", None)
    if base_url:
        log.info(f"Using base URL for More Like This links: {base_url}")
    else:
        log.info("No base URL configured - More Like This buttons will not be shown")

    feeddb = FeedDatabase(config)

    # Clear old processed items from the queue
    feeddb.clear_old_broadcast_queue(clear_old_days)
    feeddb.commit()

    # Get all active channels
    feeddb.cursor.execute("""
        SELECT c.id, c.name, c.endpoint_url, c.model_id, c.broadcast_limit,
               m.name as model_name
        FROM channels c
        LEFT JOIN models m ON c.model_id = m.id
        WHERE c.is_active = TRUE AND c.endpoint_url IS NOT NULL
        ORDER BY c.id
    """)
    channels = feeddb.cursor.fetchall()

    if not channels:
        log.info("No active channels found.")
        return

    log.info(f"Processing broadcast queue for {len(channels)} active channels.")

    # Process each channel
    for channel in channels:
        channel_id = channel["id"]
        channel_name = channel["name"]
        endpoint = channel["endpoint_url"]
        model_id = channel["model_id"]
        model_name = channel["model_name"] or "Default"

        message_options = {
            "model_name": model_name,
            "channel_name": channel_name,
        }

        # Check and remove duplicates from the broadcast queue for this channel
        duplicates_removed = feeddb.check_and_remove_duplicate_broadcasts(
            channel_id=channel_id, lookback_months=3
        )
        if duplicates_removed > 0:
            feeddb.commit()
            log.info(
                f'Removed {duplicates_removed} duplicate(s) from queue for channel "{channel_name}" (id={channel_id}).'
            )

        # Get items from the broadcast queue for this channel
        # Use channel-specific broadcast_limit
        channel_limit = channel.get("broadcast_limit", 20)  # Default to 20 if not set
        queue_items = feeddb.get_broadcast_queue_items(
            channel_id=channel_id, limit=channel_limit, model_id=model_id
        )

        if len(queue_items) == 0:
            log.info(
                f'No items in broadcast queue for channel "{channel_name}" (id={channel_id}).'
            )
            continue

        log.info(
            f'Found {len(queue_items)} items in broadcast queue for channel "{channel_name}" (id={channel_id}).'
        )

        # Create notification provider based on webhook URL
        try:
            provider = create_notification_provider(endpoint)
        except ValueError as e:
            log.error(f'Invalid webhook URL for channel "{channel_name}": {e}')
            continue

        for feed_id, info in queue_items.iterrows():
            log.info(
                f'Sending notification to channel "{channel_name}": "{info["title"]}"'
            )
            # Add the feed_id to info dict for the More Like This button
            info["id"] = feed_id
            normalize_item_for_display(info, max_content_length)
            try:
                provider.send_notification(info, message_options, base_url)
            except NotificationError as e:
                log.error(f"Failed to send notification: {e}")
            else:
                # Mark as processed in the merged broadcasts table
                feeddb.mark_broadcast_queue_processed(feed_id, channel_id)
                feeddb.commit()

    log.info("Broadcast completed for all channels.")
