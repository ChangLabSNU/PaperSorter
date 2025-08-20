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

import click
import numpy as np
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
import yaml
from ..log import log, initialize_logging

# Module constants
MIN_INTERESTED_FEEDS = 5  # Minimum number of interested feeds required to create session

@click.group()
@click.option("--config", default="./config.yml", help="Path to configuration file")
@click.option("--log-file", help="Log file path")
@click.option("-q", "--quiet", is_flag=True, help="Suppress output")
@click.pass_context
def main(ctx, config, log_file, quiet):
    """Manage labeling sessions for training data preparation."""
    initialize_logging("labeling", log_file, quiet)
    ctx.ensure_object(dict)
    ctx.obj["config"] = config


@main.command("create")
@click.option(
    "--sample-size", "-n", default=1000, type=int,
    help="Total number of feeds to include in the labeling session (default: 1000)"
)
@click.option(
    "--bins", "-b", default=10, type=int,
    help="Number of distance bins for equal sampling (default: 10)"
)
@click.option(
    "--score-threshold", default=0.5, type=float,
    help="Preference score threshold for considering a feed as interested (default: 0.5)"
)
@click.option(
    "--user-id", "-u", multiple=True, type=int,
    help="User ID(s) to filter preferences. Can be specified multiple times. If omitted, uses all users."
)
@click.option(
    "--labeler-user-id", type=int,
    help="User ID to assign the labeling session to. If omitted with single --user-id, uses that user. Otherwise uses oldest admin."
)
@click.pass_context
def create_labeling_session(ctx, sample_size, bins, score_threshold, user_id, labeler_user_id):
    """Create a new labeling session with balanced sampling based on distance to interested feeds.

    This command:
    1. Finds all feeds labeled as interested (score >= threshold)
    2. Calculates minimum cosine distance from each unlabeled feed to any interested feed
    3. Divides feeds into equal-sized bins based on distance
    4. Samples equal number of feeds from each bin
    5. Stores the selected feeds in labeling_sessions table

    The labeling session is assigned to a user determined by:
    - --labeler-user-id if explicitly provided
    - --user-id if only one user_id is specified
    - The oldest admin user (lowest ID) otherwise
    """
    config_path = ctx.obj["config"]

    # Load database configuration
    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f)

    db_config = config_data["db"]

    # Connect to PostgreSQL
    log.info("Connecting to PostgreSQL database...")
    try:
        db = psycopg2.connect(
            host=db_config["host"],
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
        )
        cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    except psycopg2.OperationalError as e:
        log.error(f"Failed to connect to database: {e}")
        log.info("")
        log.info("Please check your database configuration in config.yml")
        log.info("Make sure the PostgreSQL server is running and accessible.")
        return

    # Register pgvector extension
    register_vector(db)

    try:
        # Prepare user filter for queries
        user_ids = list(user_id) if user_id else None
        user_filter_msg = ""

        if user_ids:
            user_filter = "AND p.user_id = ANY(%s)"
            user_params = (user_ids,)
            user_filter_msg = f" (for user IDs: {', '.join(map(str, user_ids))})"
            log.info(f"Filtering preferences by user IDs: {', '.join(map(str, user_ids))}")
        else:
            user_filter = ""
            user_params = ()
            log.info("Using preferences from all users")

        # First check if any preferences exist at all
        query = f"SELECT COUNT(*) as count FROM preferences p WHERE p.score IS NOT NULL {user_filter}"
        cursor.execute(query, user_params)
        total_preferences = cursor.fetchone()["count"]

        if total_preferences == 0:
            if user_ids:
                log.error(f"No preference labels found for user ID(s): {', '.join(map(str, user_ids))}")
                # Check if these users exist at all
                cursor.execute("SELECT COUNT(DISTINCT user_id) as count FROM preferences WHERE user_id = ANY(%s)", (user_ids,))
                users_with_any_prefs = cursor.fetchone()["count"]
                if users_with_any_prefs == 0:
                    log.info("")
                    log.info("These user IDs have no preferences in the database.")
                    log.info("Please check the user IDs or omit --user-id to use all users.")
                else:
                    log.info("")
                    log.info("User(s) exist but have no scored preferences.")
            else:
                log.error("No preference labels found in the database")
                log.info("")
                log.info("To create a labeling session, you need to first label some feeds.")
                log.info("You can do this by:")
                log.info("  1. Running: papersorter serve")
                log.info("  2. Opening the web interface")
                log.info("  3. Marking some papers as 'Interested'")
                log.info("")
                log.info("TIP: A diverse set of 'interested' papers across different topics and subtopics")
                log.info("     produces a more efficient labeling dataset and yields better performing models.")
                log.info("     Consider marking papers from various aspects of your research interests.")
                log.info("")
                log.info(f"After labeling at least {MIN_INTERESTED_FEEDS} papers as interested, run this command again.")
            cursor.close()
            db.close()
            return

        # Check if we have any feeds with embeddings
        cursor.execute("SELECT COUNT(*) as count FROM embeddings")
        total_embeddings = cursor.fetchone()["count"]

        if total_embeddings == 0:
            log.error("No embeddings found in the database")
            log.info("")
            log.info("Please generate embeddings first by running:")
            log.info("  papersorter predict --count 1000")
            cursor.close()
            db.close()
            return

        # Check if we have enough interested feeds
        if user_ids:
            cursor.execute("""
                SELECT COUNT(DISTINCT p.feed_id) as count
                FROM preferences p
                JOIN embeddings e ON p.feed_id = e.feed_id
                WHERE p.score >= %s AND p.user_id = ANY(%s)
            """, (score_threshold, user_ids))
        else:
            cursor.execute("""
                SELECT COUNT(DISTINCT p.feed_id) as count
                FROM preferences p
                JOIN embeddings e ON p.feed_id = e.feed_id
                WHERE p.score >= %s
            """, (score_threshold,))

        interested_count = cursor.fetchone()["count"]

        if interested_count == 0:
            log.error(f"No interested feeds found (with score >= {score_threshold}){user_filter_msg}")
            log.info("")
            log.info(f"Found {total_preferences} total preference labels{user_filter_msg}, but none marked as interested.")
            log.info("Please label some feeds as 'Interested' in the web interface.")
            log.info("")
            log.info("You can also try:")
            log.info("  1. Lowering the score threshold: --score-threshold 0.3")
            if user_ids:
                log.info("  2. Using all users: omit the --user-id option")
            cursor.close()
            db.close()
            return

        if interested_count < MIN_INTERESTED_FEEDS:
            log.error(f"Not enough interested feeds found{user_filter_msg}. Need at least {MIN_INTERESTED_FEEDS}, found {interested_count}")
            log.info("")
            log.info(f"Please label more feeds as interested (score >= {score_threshold}) before creating a session.")
            log.info("You need to:")
            log.info(f"  1. Label {MIN_INTERESTED_FEEDS - interested_count} more papers as interested")
            log.info("")
            log.info("TIP: For best results, select papers from diverse topics within your field.")
            log.info("     A varied set of interests helps create a more balanced labeling dataset")
            log.info("     and ultimately trains a model that better captures your preferences.")
            if user_ids:
                log.info("  3. Use all users: omit the --user-id option")
            cursor.close()
            db.close()
            return

        log.info(f"Found {interested_count} interested feeds{user_filter_msg}")

        # Clear existing labeling session
        log.info("Clearing existing labeling session...")
        cursor.execute("TRUNCATE TABLE labeling_sessions")

        # Calculate minimum distance for each unlabeled feed to any interested feed
        log.info("Calculating distances to interested feeds...")

        # Using the optimized query with proper distance calculation
        if user_ids:
            cursor.execute("""
                WITH interested_feeds AS (
                    -- Get all feeds labeled as interested by specified users
                    SELECT DISTINCT f.id, e.embedding
                    FROM feeds f
                    JOIN embeddings e ON f.id = e.feed_id
                    JOIN preferences p ON f.id = p.feed_id
                    WHERE p.score >= %s AND p.user_id = ANY(%s)
                ),
                feed_distances AS (
                    -- Calculate minimum distance from each feed to any interested feed
                    SELECT
                        f.id,
                        f.external_id,
                        f.title,
                        f.author,
                        f.origin,
                        f.published,
                        f.added,
                        MIN(e.embedding <=> i.embedding) as min_distance
                    FROM feeds f
                    JOIN embeddings e ON f.id = e.feed_id
                    CROSS JOIN interested_feeds i
                    WHERE NOT EXISTS (
                        -- Exclude feeds that already have preferences from the specified users
                        SELECT 1 FROM preferences p WHERE p.feed_id = f.id AND p.user_id = ANY(%s)
                    )
                    GROUP BY f.id, f.external_id, f.title, f.author, f.origin, f.published, f.added
                )
                SELECT
                    id as feed_id,
                    external_id,
                    title,
                    author,
                    origin,
                    published,
                    added,
                    min_distance
                FROM feed_distances
                WHERE min_distance IS NOT NULL
                ORDER BY min_distance ASC
            """, (score_threshold, user_ids, user_ids))
        else:
            cursor.execute("""
                WITH interested_feeds AS (
                    -- Get all feeds labeled as interested
                    SELECT DISTINCT f.id, e.embedding
                    FROM feeds f
                    JOIN embeddings e ON f.id = e.feed_id
                    JOIN preferences p ON f.id = p.feed_id
                    WHERE p.score >= %s
                ),
                feed_distances AS (
                    -- Calculate minimum distance from each feed to any interested feed
                    SELECT
                        f.id,
                        f.external_id,
                        f.title,
                        f.author,
                        f.origin,
                        f.published,
                        f.added,
                        MIN(e.embedding <=> i.embedding) as min_distance
                    FROM feeds f
                    JOIN embeddings e ON f.id = e.feed_id
                    CROSS JOIN interested_feeds i
                    WHERE NOT EXISTS (
                        -- Exclude feeds that already have preferences
                        SELECT 1 FROM preferences p WHERE p.feed_id = f.id
                    )
                    GROUP BY f.id, f.external_id, f.title, f.author, f.origin, f.published, f.added
                )
                SELECT
                    id as feed_id,
                    external_id,
                    title,
                    author,
                    origin,
                    published,
                    added,
                    min_distance
                FROM feed_distances
                WHERE min_distance IS NOT NULL
                ORDER BY min_distance ASC
            """, (score_threshold,))

        all_feeds = cursor.fetchall()

        if not all_feeds:
            log.error("No unlabeled feeds with embeddings found")
            log.info("")

            # Check if all feeds are already labeled
            cursor.execute("SELECT COUNT(*) as total FROM feeds WHERE id IN (SELECT feed_id FROM embeddings)")
            total_with_embeddings = cursor.fetchone()["total"]

            if user_ids:
                cursor.execute("SELECT COUNT(DISTINCT feed_id) as labeled FROM preferences WHERE user_id = ANY(%s)", (user_ids,))
            else:
                cursor.execute("SELECT COUNT(DISTINCT feed_id) as labeled FROM preferences")
            labeled_count = cursor.fetchone()["labeled"]

            if labeled_count >= total_with_embeddings and total_with_embeddings > 0:
                log.info(f"All {total_with_embeddings} feeds with embeddings have already been labeled{user_filter_msg}.")
                log.info("To create a new labeling session, you can:")
                log.info("  1. Import more articles: papersorter import pubmed")
                log.info("  2. Update from RSS feeds: papersorter update")
                log.info("  3. Generate embeddings for new articles: papersorter predict")
            else:
                log.info("This might happen if:")
                log.info("  1. All feeds have been labeled already")
                log.info("  2. No feeds have embeddings generated")
                log.info("")
                log.info("Try running: papersorter predict --count 1000")
            cursor.close()
            db.close()
            return

        log.info(f"Found {len(all_feeds)} unlabeled feeds with embeddings")

        # Convert to numpy array for easier manipulation
        feed_ids = [f["feed_id"] for f in all_feeds]
        distances = np.array([f["min_distance"] for f in all_feeds])

        # Create percentile-based (quantile) bins to ensure equal number of feeds per bin
        # This prevents having too few feeds in extreme bins
        # Bins with smaller distances (closer to interested) get more samples
        # First bin gets 4x more samples than last bin, with linear gradient

        # Calculate percentile boundaries for equal-sized bins
        percentiles = np.linspace(0, 100, bins + 1)
        bin_edges = np.percentile(distances, percentiles)

        # Ensure unique bin edges (in case of duplicate distances)
        bin_edges = np.unique(bin_edges)
        actual_bins = len(bin_edges) - 1

        if actual_bins < bins:
            log.warning(f"Reduced to {actual_bins} bins due to duplicate distance values")

        # Adjust the last edge slightly to include the maximum value
        bin_edges[-1] = bin_edges[-1] + 1e-10

        # Calculate sample weights for each bin
        # First bin (closest): weight = 4, Last bin (farthest): weight = 1
        sample_weights = np.linspace(4.0, 1.0, actual_bins)

        # Normalize weights to sum to total sample size
        samples_per_bin = (sample_weights / sample_weights.sum() * sample_size).astype(int)

        # Distribute any remaining samples due to rounding
        remaining_samples = sample_size - samples_per_bin.sum()
        if remaining_samples > 0:
            # Add remaining samples to the bins with highest weights (closest distances)
            for i in range(remaining_samples):
                samples_per_bin[i] += 1

        log.info(f"Created {actual_bins} percentile-based bins with weighted sampling (4:1 ratio)")
        log.info("Sample distribution across bins:")
        for i in range(min(5, actual_bins)):
            # Count feeds in this bin
            if i == actual_bins - 1:
                bin_mask = (distances >= bin_edges[i]) & (distances <= bin_edges[i + 1])
            else:
                bin_mask = (distances >= bin_edges[i]) & (distances < bin_edges[i + 1])
            feeds_in_bin = np.sum(bin_mask)
            log.info(f"  Bin {i+1} (distance {bin_edges[i]:.4f}-{bin_edges[i+1]:.4f}): "
                    f"{samples_per_bin[i]} samples from {feeds_in_bin} feeds")
        if actual_bins > 5:
            log.info(f"  ... ({actual_bins - 5} more bins)")
            # Count feeds in last bin
            bin_mask = (distances >= bin_edges[-2]) & (distances <= bin_edges[-1])
            feeds_in_bin = np.sum(bin_mask)
            log.info(f"  Bin {actual_bins} (distance {bin_edges[-2]:.4f}-{bin_edges[-1]:.4f}): "
                    f"{samples_per_bin[-1]} samples from {feeds_in_bin} feeds")

        log.info(f"Total samples to select: {samples_per_bin.sum()}")

        selected_feed_ids = []

        # Sample from each bin
        for i in range(actual_bins):
            if i == actual_bins - 1:
                # Last bin includes the maximum value
                bin_mask = (distances >= bin_edges[i]) & (distances <= bin_edges[i + 1])
            else:
                bin_mask = (distances >= bin_edges[i]) & (distances < bin_edges[i + 1])

            bin_feed_ids = np.array(feed_ids)[bin_mask]

            # Get the number of samples for this bin (already calculated above)
            n_samples = samples_per_bin[i]

            if len(bin_feed_ids) <= n_samples:
                # Take all feeds from this bin if we don't have enough
                selected = bin_feed_ids.tolist()
                log.info(f"Bin {i+1} (distance {bin_edges[i]:.4f}-{bin_edges[i+1]:.4f}): "
                        f"Selected all {len(selected)} feeds (requested {n_samples})")
            else:
                # Random sample from this bin
                selected_indices = np.random.choice(len(bin_feed_ids), n_samples, replace=False)
                selected = bin_feed_ids[selected_indices].tolist()
                log.info(f"Bin {i+1} (distance {bin_edges[i]:.4f}-{bin_edges[i+1]:.4f}): "
                        f"Selected {len(selected)} feeds from {len(bin_feed_ids)} available")

            selected_feed_ids.extend(selected)

        # Insert selected feeds into labeling_sessions table
        log.info(f"Inserting {len(selected_feed_ids)} feeds into labeling session...")

        # Determine which user_id to use for the labeling session
        if labeler_user_id:
            # Explicit labeler user ID provided - verify it exists
            cursor.execute("SELECT id, username FROM users WHERE id = %s", (labeler_user_id,))
            labeler_user = cursor.fetchone()

            if not labeler_user:
                log.error(f"User ID {labeler_user_id} not found in the database")
                log.info("")
                log.info("Please specify a valid user ID that exists in the database.")
                cursor.close()
                db.close()
                return

            session_user_id = labeler_user_id
            log.info(f"Using specified labeler user_id: {session_user_id} ({labeler_user['username']})")
        elif user_ids and len(user_ids) == 1:
            # Single user_id filter specified, use it as the labeler
            session_user_id = user_ids[0]
            # Get username for logging
            cursor.execute("SELECT username FROM users WHERE id = %s", (session_user_id,))
            user_result = cursor.fetchone()
            username = user_result['username'] if user_result else 'unknown'
            log.info(f"Using single filtered user_id as labeler: {session_user_id} ({username})")
        else:
            # Multiple user_ids or no user_id specified - find oldest admin
            cursor.execute("""
                SELECT id, username
                FROM users
                WHERE is_admin = true
                ORDER BY id ASC
                LIMIT 1
            """)
            admin_user = cursor.fetchone()

            if not admin_user:
                log.error("No admin users found in the database")
                log.info("")
                log.info("To create a labeling session without explicit --labeler-user-id:")
                log.info("  1. Ensure at least one admin user exists")
                log.info("  2. Or specify --labeler-user-id explicitly")
                log.info("  3. Or use a single --user-id to assign the session to that user")
                cursor.close()
                db.close()
                return

            session_user_id = admin_user["id"]
            log.info(f"Using oldest admin user as labeler: {session_user_id} ({admin_user['username']})")

        log.info(f"Creating labeling session for user_id: {session_user_id}")

        # Insert selected feeds
        for feed_id in selected_feed_ids:
            cursor.execute("""
                INSERT INTO labeling_sessions (
                    feed_id, user_id, score, update_time
                ) VALUES (%s, %s, NULL, NULL)
            """, (feed_id, session_user_id))

        db.commit()

        # Summary statistics - we need to recalculate distances since we don't store them
        cursor.execute("""
            SELECT COUNT(*) as total_feeds
            FROM labeling_sessions
            WHERE user_id = %s
        """, (session_user_id,))

        stats = cursor.fetchone()

        # Calculate distance statistics from the selected feeds
        if selected_feed_ids:
            # Get min/max/avg distances from our selection
            selected_distances = []
            for feed_id in selected_feed_ids:
                feed_data = next((f for f in all_feeds if f["feed_id"] == feed_id), None)
                if feed_data:
                    selected_distances.append(feed_data["min_distance"])

            if selected_distances:
                import statistics
                min_dist = min(selected_distances)
                max_dist = max(selected_distances)
                avg_dist = statistics.mean(selected_distances)
                std_dist = statistics.stdev(selected_distances) if len(selected_distances) > 1 else 0

                log.info("="*60)
                log.info("Labeling session created successfully!")
                log.info("="*60)
                log.info(f"Total feeds in session: {stats['total_feeds']}")
                log.info(f"User ID: {session_user_id}")
                log.info(f"Distance range: {min_dist:.4f} - {max_dist:.4f}")
                log.info(f"Average distance: {avg_dist:.4f} (±{std_dist:.4f})")
                log.info("")

                # Show distribution by quintiles
                log.info("Distribution by distance quintile:")
                sorted_distances = sorted(zip(selected_feed_ids, selected_distances), key=lambda x: x[1])
                quintile_size = len(sorted_distances) // 5

                for q in range(5):
                    start_idx = q * quintile_size
                    end_idx = start_idx + quintile_size if q < 4 else len(sorted_distances)
                    quintile_data = sorted_distances[start_idx:end_idx]

                    if quintile_data:
                        q_distances = [d for _, d in quintile_data]
                        log.info(f"  Q{q+1}: {len(quintile_data):4d} feeds "
                                f"(distance {min(q_distances):.4f}-{max(q_distances):.4f})")
        else:
            log.info("="*60)
            log.info("Labeling session created successfully!")
            log.info(f"Total feeds in session: {stats['total_feeds']}")
            log.info(f"User ID: {session_user_id}")

        # Show link to labeling interface (common for both branches)
        log.info("")
        log.info("="*60)
        log.info("Ready to start labeling!")
        log.info("")
        if "web" in config_data and "base_url" in config_data["web"]:
            base_url = config_data["web"]["base_url"].rstrip('/')
            log.info(f"Open the labeling interface at: {base_url}/labeling")
        else:
            log.info("Open the labeling interface at: http://localhost:5001/labeling")
            log.info("(Or use: papersorter serve --skip-authentication <username>)")
        log.info("="*60)

    except Exception as e:
        log.error(f"Failed to create labeling session: {e}")
        db.rollback()
        raise
    finally:
        cursor.close()
        db.close()


@main.command("clear")
@click.option(
    "--labeler-user-id", type=int, required=True,
    help="User ID whose labeling session to clear"
)
@click.pass_context
def clear_labeling_session(ctx, labeler_user_id):
    """Clear labeling session for a specific user and show statistics.

    This command:
    1. Finds all labeling sessions for the specified user
    2. Shows statistics about labeled vs unlabeled items
    3. Removes all associated records from labeling_sessions table
    """
    config_path = ctx.parent.params["config"]

    # Load database configuration
    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f)

    db_config = config_data.get("db", {})

    try:
        # Connect to database
        db = psycopg2.connect(
            host=db_config["host"],
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
        )
        cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # First, get statistics about the current session
        cursor.execute("""
            SELECT
                COUNT(*) as total_items,
                COUNT(CASE WHEN score IS NOT NULL THEN 1 END) as labeled_items,
                COUNT(CASE WHEN score IS NULL THEN 1 END) as unlabeled_items,
                COUNT(CASE WHEN score >= 0.5 THEN 1 END) as interested_items,
                COUNT(CASE WHEN score < 0.5 THEN 1 END) as not_interested_items,
                MIN(update_time) as first_label_time,
                MAX(update_time) as last_label_time
            FROM labeling_sessions
            WHERE user_id = %s
        """, (labeler_user_id,))

        stats = cursor.fetchone()

        if not stats or stats["total_items"] == 0:
            log.info(f"No labeling session found for user ID {labeler_user_id}")
            cursor.close()
            db.close()
            return

        # Get user information
        cursor.execute("""
            SELECT username
            FROM users
            WHERE id = %s
        """, (labeler_user_id,))

        user_info = cursor.fetchone()
        username = user_info["username"] if user_info else f"User {labeler_user_id}"

        # Display statistics before deletion
        log.info("="*60)
        log.info("Labeling Session Statistics")
        log.info("="*60)
        log.info(f"User: {username} (ID: {labeler_user_id})")
        log.info(f"Total items in session: {stats['total_items']}")
        log.info(f"Labeled items: {stats['labeled_items']} ({stats['labeled_items']*100/stats['total_items']:.1f}%)")
        log.info(f"Unlabeled items: {stats['unlabeled_items']} ({stats['unlabeled_items']*100/stats['total_items']:.1f}%)")

        if stats['labeled_items'] > 0:
            log.info("")
            log.info("Label distribution:")
            log.info(f"  Interested: {stats['interested_items']} ({stats['interested_items']*100/stats['labeled_items']:.1f}% of labeled)")
            log.info(f"  Not interested: {stats['not_interested_items']} ({stats['not_interested_items']*100/stats['labeled_items']:.1f}% of labeled)")

            if stats['first_label_time'] and stats['last_label_time']:
                log.info("")
                log.info(f"First label: {stats['first_label_time']}")
                log.info(f"Last label: {stats['last_label_time']}")

                # Calculate session duration if both timestamps exist
                if stats['first_label_time'] != stats['last_label_time']:
                    duration = stats['last_label_time'] - stats['first_label_time']
                    hours = duration.total_seconds() / 3600
                    if hours >= 1:
                        log.info(f"Session duration: {hours:.1f} hours")
                    else:
                        minutes = duration.total_seconds() / 60
                        log.info(f"Session duration: {minutes:.0f} minutes")

        # Get a sample of labeled items for reference
        if stats['labeled_items'] > 0:
            cursor.execute("""
                SELECT
                    f.title,
                    ls.score
                FROM labeling_sessions ls
                JOIN feeds f ON ls.feed_id = f.id
                WHERE ls.user_id = %s AND ls.score IS NOT NULL
                ORDER BY ls.update_time DESC
                LIMIT 5
            """, (labeler_user_id,))

            recent_labels = cursor.fetchall()
            if recent_labels:
                log.info("")
                log.info("Last 5 labeled items:")
                for item in recent_labels:
                    label = "Interested" if item["score"] >= 0.5 else "Not interested"
                    title = item["title"][:80] + "..." if len(item["title"]) > 80 else item["title"]
                    log.info(f"  [{label:15s}] {title}")

        # Ask for confirmation
        log.info("")
        log.info("="*60)
        log.warning(f"This will permanently delete {stats['total_items']} items from the labeling session.")
        log.warning("Note: Labels already saved to preferences table will be preserved.")

        if not click.confirm("Do you want to proceed with clearing this session?"):
            log.info("Operation cancelled.")
            cursor.close()
            db.close()
            return

        # Delete the labeling session
        cursor.execute("""
            DELETE FROM labeling_sessions
            WHERE user_id = %s
        """, (labeler_user_id,))

        deleted_count = cursor.rowcount
        db.commit()

        log.info("")
        log.info("="*60)
        log.info(f"Successfully cleared labeling session for {username}")
        log.info(f"Deleted {deleted_count} items from labeling_sessions table")
        log.info("="*60)

        cursor.close()
        db.close()

    except Exception as e:
        log.error(f"Failed to clear labeling session: {e}")
        if 'db' in locals():
            db.rollback()
            cursor.close()
            db.close()
        raise