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
from ..utils.broadcast_hours import is_broadcast_allowed
from ..cli.base import BaseCommand, registry
import re
import yaml
import argparse
from datetime import datetime


class BroadcastCommand(BaseCommand):
    """Process broadcast queue and send notifications."""

    name = 'broadcast'
    help = 'Process broadcast queue and send notifications'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add broadcast-specific arguments."""
        parser.add_argument(
            '--limit-per-channel',
            type=int,
            default=20,
            help='Maximum number of items to process per channel'
        )
        parser.add_argument(
            '--max-content-length',
            type=int,
            default=1000,
            help='Maximum length of content in characters'
        )
        parser.add_argument(
            '--clear-old-days',
            type=int,
            default=30,
            help='Clear broadcast queue items older than this many days'
        )

    def handle(self, args: argparse.Namespace, context) -> int:
        """Execute the broadcast command."""
        initialize_logging('broadcast', args.log_file, args.quiet)
        try:
            main(
                config=args.config,
                limit_per_channel=args.limit_per_channel,
                max_content_length=args.max_content_length,
                clear_old_days=args.clear_old_days,
                log_file=args.log_file,
                quiet=args.quiet
            )
            return 0
        except Exception as e:
            log.error(f"Broadcast failed: {e}")
            return 1

# Register the command
registry.register(BroadcastCommand)


def normalize_item_for_display(item, max_content_length):
    # XXX: Fix the source field for the aggregated items.
    if item.get("origin_source") == "QBio Feed Aggregation" and "  " in item["content"]:
        source, content = item["content"].split("  ", 1)
        item["origin"] = source  # Override journal display with parsed source
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


def main(config, limit_per_channel, max_content_length, clear_old_days, log_file, quiet):
    """Send notifications for high-scoring papers to configured channels.

    Processes the broadcast queue and sends notifications to Slack/Discord channels
    based on their score thresholds and broadcast hours.
    """

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
               c.broadcast_hours, c.show_other_scores, m.name as model_name, m.score_name
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

    # Get current time for checking broadcast hours
    current_time = datetime.now()

    # Process each channel
    for channel in channels:
        channel_id = channel["id"]
        channel_name = channel["name"]
        endpoint = channel["endpoint_url"]
        model_id = channel["model_id"]
        model_name = channel["model_name"] or "Default"
        score_name = channel.get("score_name", "Score")  # Default to "Score" if not set
        broadcast_hours = channel.get("broadcast_hours")

        # Check if broadcasting is allowed at current time
        if not is_broadcast_allowed(broadcast_hours, current_time):
            log.info(
                f'Skipping channel "{channel_name}" (id={channel_id}) - '
                f'broadcasting not allowed at hour {current_time.hour}'
            )
            continue

        message_options = {
            "model_name": model_name,
            "channel_name": channel_name,
            "score_name": score_name,
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
        channel_limit = channel.get("broadcast_limit", limit_per_channel)  # Default to limit_per_channel arg if not set
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
            provider = create_notification_provider(endpoint, config_path=config)
        except ValueError as e:
            log.error(f'Invalid webhook URL for channel "{channel_name}": {e}')
            continue

        # Prepare items for batch sending
        items_to_send = []

        # If show_other_scores is enabled, fetch scores from all active models
        other_model_scores = {}
        if channel.get("show_other_scores", False):
            # Get all active models except the channel's primary model
            feeddb.cursor.execute("""
                SELECT id, name, score_name
                FROM models
                WHERE is_active = TRUE AND id != %s
                ORDER BY id DESC
            """, (model_id,))
            other_models = feeddb.cursor.fetchall()

            if other_models:
                # Get feed IDs from queue items
                feed_ids = [feed_id for feed_id, _ in queue_items.iterrows()]

                # Fetch scores for all other models
                for other_model in other_models:
                    feeddb.cursor.execute("""
                        SELECT feed_id, score
                        FROM predicted_preferences
                        WHERE model_id = %s AND feed_id = ANY(%s)
                    """, (other_model["id"], feed_ids))

                    for row in feeddb.cursor.fetchall():
                        if row["feed_id"] not in other_model_scores:
                            other_model_scores[row["feed_id"]] = []
                        other_model_scores[row["feed_id"]].append({
                            "model_id": other_model["id"],
                            "model_name": other_model["name"] or f"Model {other_model['id']}",
                            "score_name": other_model["score_name"] or "Score",
                            "score": row["score"]
                        })

        for feed_id, info in queue_items.iterrows():
            # Add the feed_id to info dict for the More Like This button
            info["id"] = feed_id
            normalize_item_for_display(info, max_content_length)
            item_dict = info.to_dict()

            # Add other model scores if available
            if feed_id in other_model_scores:
                item_dict["other_scores"] = other_model_scores[feed_id]

            items_to_send.append(item_dict)

        log.info(
            f'Sending {len(items_to_send)} notifications to channel "{channel_name}"'
        )

        try:
            # Send all items as a batch
            results = provider.send_notifications(items_to_send, message_options, base_url)

            # Process results and mark successful items as processed
            for item_id, success in results:
                if success:
                    feeddb.mark_broadcast_queue_processed(item_id, channel_id)
                else:
                    log.warning(f"Failed to send item {item_id} to channel {channel_name}")

            feeddb.commit()

            successful_count = sum(1 for _, success in results if success)
            log.info(
                f'Successfully sent {successful_count}/{len(items_to_send)} items to channel "{channel_name}"'
            )

        except NotificationError as e:
            log.error(f"Failed to send notifications to channel {channel_name}: {e}")

    log.info("Broadcast completed for all channels.")
