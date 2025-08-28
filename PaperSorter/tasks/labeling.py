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

import numpy as np
import psycopg2
import argparse
import psycopg2.extras
from pgvector.psycopg2 import register_vector
import yaml
import sys
from datetime import datetime, timedelta
from ..log import log, initialize_logging
from ..cli.base import BaseCommand, registry
from ..cli.types import probability_float


# Module constants
MIN_INTERESTED_FEEDS = 5  # Minimum number of interested feeds required to create session


class LabelingCommand(BaseCommand):
    """Manage labeling sessions for training data."""

    name = 'labeling'
    help = 'Manage labeling sessions for training data'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add labeling subcommands."""
        subparsers = parser.add_subparsers(
            dest='subcommand',
            help='Available labeling commands'
        )

        # Add create subcommand
        create_parser = subparsers.add_parser(
            'create',
            help='Create a new labeling session with balanced sampling'
        )
        create_parser.add_argument(
            '--sample-size', '-n',
            type=int,
            default=1000,
            help='Total number of papers to include in the labeling session (default: 1000)'
        )
        create_parser.add_argument(
            '--bins', '-b',
            type=int,
            default=10,
            help='Number of distance/score bins for equal sampling (default: 10)'
        )
        create_parser.add_argument(
            '--score-threshold',
            type=probability_float,
            default=0.5,
            help='Preference score threshold for considering a paper as interested (default: 0.5)'
        )
        create_parser.add_argument(
            '--user-id', '-u',
            action='append',
            type=int,
            help='User ID(s) to filter preferences. Can be specified multiple times'
        )
        create_parser.add_argument(
            '--labeler-user-id',
            type=int,
            help='User ID to assign the labeling session to'
        )
        create_parser.add_argument(
            '--base-model',
            type=int,
            help='Model ID to use for score-based binning instead of distance-based'
        )
        create_parser.add_argument(
            '--max-age',
            type=int,
            default=0,
            help='Maximum age of papers in days. 0 means no limit (default: 0)'
        )
        create_parser.add_argument(
            '--max-reference-papers',
            type=int,
            default=20,
            help='Maximum number of reference papers for distance calculation (default: 20)'
        )
        create_parser.add_argument(
            '--max-scan-papers',
            type=int,
            default=100000,
            help='Maximum number of candidate papers to scan for distance calculation (default: 100000)'
        )

        # Add clear subcommand
        clear_parser = subparsers.add_parser(
            'clear',
            help='Clear labeling session for a specific user'
        )
        clear_parser.add_argument(
            '--labeler-user-id',
            type=int,
            required=True,
            help='User ID whose labeling session to clear'
        )

    def handle(self, args: argparse.Namespace, context) -> int:
        """Execute the labeling command."""
        initialize_logging('labeling', args.log_file, args.quiet)

        try:
            if args.subcommand == 'create':
                do_create_labeling_session(
                    config_path=args.config,
                    sample_size=args.sample_size,
                    bins=args.bins,
                    score_threshold=args.score_threshold,
                    user_id=tuple(args.user_id) if args.user_id else (),
                    labeler_user_id=args.labeler_user_id,
                    base_model=args.base_model,
                    max_age=args.max_age,
                    max_reference_papers=args.max_reference_papers,
                    max_scan_papers=args.max_scan_papers
                )
                return 0
            elif args.subcommand == 'clear':
                do_clear_labeling_session(args.config, args.labeler_user_id)
                return 0
            else:
                print("Please specify a subcommand: create, clear", file=sys.stderr)
                return 1
        except Exception as e:
            log.error(f"Labeling command failed: {e}")
            return 1

# Register the command
registry.register(LabelingCommand)


def check_prerequisites_for_distance_mode(cursor, user_ids, user_filter, user_params, score_threshold):
    """Check if we have enough preferences and interested feeds for distance-based mode.

    Returns:
        tuple: (success: bool, interested_count: int)
    """
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
            log.info("To create a labeling session, you need to first label some papers.")
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
        return False, 0

    # Check if we have enough interested papers
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
        user_filter_msg = f" (for user IDs: {', '.join(map(str, user_ids))})" if user_ids else ""
        log.error(f"No interested papers found (with score >= {score_threshold}){user_filter_msg}")
        log.info("")
        log.info(f"Found {total_preferences} total preference labels{user_filter_msg}, but none marked as interested.")
        log.info("Please label some feeds as 'Interested' in the web interface.")
        log.info("")
        log.info("You can also try:")
        log.info("  1. Lowering the score threshold: --score-threshold 0.3")
        if user_ids:
            log.info("  2. Using all users: omit the --user-id option")
        return False, 0

    if interested_count < MIN_INTERESTED_FEEDS:
        user_filter_msg = f" (for user IDs: {', '.join(map(str, user_ids))})" if user_ids else ""
        log.error(f"Not enough interested papers found{user_filter_msg}. Need at least {MIN_INTERESTED_FEEDS}, found {interested_count}")
        log.info("")
        log.info(f"Please label more papers as interested (score >= {score_threshold}) before creating a session.")
        log.info("You need to:")
        log.info(f"  1. Label {MIN_INTERESTED_FEEDS - interested_count} more papers as interested")
        log.info("")
        log.info("TIP: For best results, select papers from diverse topics within your field.")
        log.info("     A varied set of interests helps create a more balanced labeling dataset")
        log.info("     and ultimately trains a model that better captures your preferences.")
        if user_ids:
            log.info("  3. Use all users: omit the --user-id option")
        return False, 0

    user_filter_msg = f" (for user IDs: {', '.join(map(str, user_ids))})" if user_ids else ""
    log.info(f"Found {interested_count} interested papers{user_filter_msg}")
    return True, interested_count


def check_prerequisites_for_model_mode(cursor, base_model, sample_size):
    """Check if model exists and has enough predictions for model-based mode.

    Returns:
        tuple: (success: bool, model_info: dict or None)
    """
    # Check if the model exists
    cursor.execute("""
        SELECT id, name, is_active
        FROM models
        WHERE id = %s
    """, (base_model,))
    model_info = cursor.fetchone()

    if not model_info:
        log.error(f"Model ID {base_model} not found in the database")
        log.info("")
        log.info("Available models:")
        cursor.execute("SELECT id, name, is_active FROM models ORDER BY id")
        models = cursor.fetchall()
        for model in models:
            status = "active" if model["is_active"] else "inactive"
            log.info(f"  Model {model['id']}: {model['name']} ({status})")
        return False, None

    log.info(f"Using base model: {model_info['name']} (ID: {base_model})")

    # Check if we have enough predictions
    cursor.execute("""
        SELECT COUNT(DISTINCT pp.feed_id) as count
        FROM predicted_preferences pp
        JOIN embeddings e ON pp.feed_id = e.feed_id
        WHERE pp.model_id = %s
    """, (base_model,))

    predictions_count = cursor.fetchone()["count"]

    if predictions_count < sample_size:
        log.error(f"Not enough predictions for model {base_model}. Need at least {sample_size}, found {predictions_count}")
        log.info("")
        log.info("Please generate more predictions by running:")
        log.info(f"  papersorter predict --count {sample_size * 2}")
        return False, None

    log.info(f"Found {predictions_count} feeds with predictions from base model")
    return True, model_info


def get_feeds_for_model_mode(cursor, base_model, user_ids, max_age=0):
    """Get feeds with prediction scores for model-based sampling."""
    log.info("Fetching feeds with prediction scores...")

    # Build age filter
    age_filter = ""
    params = [base_model]

    if max_age > 0:
        cutoff_date = datetime.now() - timedelta(days=max_age)
        age_filter = "AND f.added >= %s"
        params.append(cutoff_date)
        log.info(f"Filtering to papers added after {cutoff_date.strftime('%Y-%m-%d')}")

    if user_ids:
        params.append(user_ids)
        cursor.execute(f"""
            SELECT
                f.id as feed_id,
                f.external_id,
                f.title,
                f.author,
                f.origin,
                f.published,
                f.added,
                pp.score as prediction_score
            FROM feeds f
            JOIN predicted_preferences pp ON f.id = pp.feed_id
            JOIN embeddings e ON f.id = e.feed_id
            WHERE pp.model_id = %s
            {age_filter}
            AND NOT EXISTS (
                -- Exclude feeds that already have preferences from the specified users
                SELECT 1 FROM preferences p WHERE p.feed_id = f.id AND p.user_id = ANY(%s)
            )
            ORDER BY pp.score DESC
        """, params)
    else:
        cursor.execute(f"""
            SELECT
                f.id as feed_id,
                f.external_id,
                f.title,
                f.author,
                f.origin,
                f.published,
                f.added,
                pp.score as prediction_score
            FROM feeds f
            JOIN predicted_preferences pp ON f.id = pp.feed_id
            JOIN embeddings e ON f.id = e.feed_id
            WHERE pp.model_id = %s
            {age_filter}
            AND NOT EXISTS (
                -- Exclude feeds that already have preferences
                SELECT 1 FROM preferences p WHERE p.feed_id = f.id
            )
            ORDER BY pp.score DESC
        """, params)

    return cursor.fetchall()


def count_interested_feeds(cursor, score_threshold, user_ids):
    """Count the number of interested feeds based on score threshold."""
    where_clause = "WHERE p.score >= %s"
    params = [score_threshold]

    if user_ids:
        where_clause += " AND p.user_id = ANY(%s)"
        params.append(user_ids)

    cursor.execute(f"""
        SELECT COUNT(DISTINCT f.id) as count
        FROM feeds f
        JOIN embeddings e ON f.id = e.feed_id
        JOIN preferences p ON f.id = p.feed_id
        {where_clause}
    """, params)

    return cursor.fetchone()["count"]


def count_unlabeled_papers(cursor, user_ids):
    """Count the number of unlabeled papers with embeddings."""
    not_exists_clause = "SELECT 1 FROM preferences p WHERE p.feed_id = f.id"
    params = []

    if user_ids:
        not_exists_clause += " AND p.user_id = ANY(%s)"
        params = [user_ids]

    cursor.execute(f"""
        SELECT COUNT(DISTINCT f.id) as count
        FROM feeds f
        JOIN embeddings e ON f.id = e.feed_id
        WHERE NOT EXISTS ({not_exists_clause})
    """, params)

    return cursor.fetchone()["count"]


def get_min_feed_id_for_limit(cursor, user_ids, max_scan_papers):
    """Get the minimum feed ID to limit candidate papers to most recent N."""
    # Build NOT EXISTS clause based on user_ids
    not_exists_clause = "SELECT 1 FROM preferences p WHERE p.feed_id = f.id"
    params = []

    if user_ids:
        not_exists_clause += " AND p.user_id = ANY(%s)"
        params.append(user_ids)

    params.append(max_scan_papers - 1)

    cursor.execute(f"""
        SELECT f.id
        FROM feeds f
        JOIN embeddings e ON f.id = e.feed_id
        WHERE NOT EXISTS ({not_exists_clause})
        ORDER BY f.id DESC
        LIMIT 1 OFFSET %s
    """, params)

    result = cursor.fetchone()
    return result["id"] if result else None


def get_feeds_for_distance_mode(cursor, score_threshold, user_ids, max_age=0, max_reference_papers=None, max_scan_papers=None):
    """Get feeds with distances to interested feeds for distance-based sampling."""
    # Use defaults if not specified
    if max_reference_papers is None:
        max_reference_papers = 20
    if max_scan_papers is None:
        max_scan_papers = 100000
    # Count and log interested feeds
    total_interested = count_interested_feeds(cursor, score_threshold, user_ids)

    if total_interested > max_reference_papers:
        log.info(f"Found {total_interested} interested papers. Using {max_reference_papers} most recent as references for performance.")
    else:
        log.info(f"Calculating distances to all {total_interested} interested feeds...")

    # Count target feeds and determine if limiting is needed
    total_target_feeds = count_unlabeled_papers(cursor, user_ids)

    # Determine minimum feed ID to limit target feeds
    min_feed_id_filter = ""
    min_feed_id = None
    if total_target_feeds > max_scan_papers:
        log.info(f"Found {total_target_feeds} unlabeled papers. Limiting to most recent {max_scan_papers} for performance.")
        min_feed_id = get_min_feed_id_for_limit(cursor, user_ids, max_scan_papers)
        if min_feed_id:
            min_feed_id_filter = "AND f.id >= %s"
            log.info(f"Using feeds with ID >= {min_feed_id}")
    else:
        log.info(f"Processing all {total_target_feeds} unlabeled papers.")

    # Build filters
    age_filter, cutoff_date = build_age_filter(max_age)

    # Execute distance calculation query
    query_params = build_distance_query_params(
        score_threshold, user_ids, max_reference_papers,
        min_feed_id, cutoff_date
    )

    distance_query = build_distance_calculation_query(
        user_ids, min_feed_id_filter, age_filter
    )

    cursor.execute(distance_query, query_params)
    return cursor.fetchall()


def build_age_filter(max_age):
    """Build age filter and return filter string and cutoff date."""
    if max_age > 0:
        cutoff_date = datetime.now() - timedelta(days=max_age)
        log.info(f"Filtering to papers added after {cutoff_date.strftime('%Y-%m-%d')}")
        return "AND f.added >= %s", cutoff_date
    return "", None


def build_distance_query_params(score_threshold, user_ids, max_reference_papers, min_feed_id, cutoff_date):
    """Build parameters for distance calculation query."""
    params = [score_threshold]

    if user_ids:
        params.append(user_ids)
        params.append(max_reference_papers)
        params.append(user_ids)  # For the NOT EXISTS clause
        if min_feed_id:
            params.append(min_feed_id)
        if cutoff_date:
            params.append(cutoff_date)
    else:
        params.append(max_reference_papers)
        if min_feed_id:
            params.append(min_feed_id)
        if cutoff_date:
            params.append(cutoff_date)

    return params


def build_distance_calculation_query(user_ids, min_feed_id_filter, age_filter):
    """Build the SQL query for distance calculation."""
    # Build the WHERE clause for interested feeds based on user_ids
    interested_where = "WHERE p.score >= %s"
    if user_ids:
        interested_where += " AND p.user_id = ANY(%s)"

    # Build the NOT EXISTS clause for excluding already-labeled papers
    exclude_clause = "SELECT 1 FROM preferences p WHERE p.feed_id = f.id"
    if user_ids:
        exclude_clause += " AND p.user_id = ANY(%s)"

    return f"""
        WITH interested_feeds AS (
            -- Get most recent N feeds labeled as interested
            SELECT DISTINCT f.id, e.embedding
            FROM feeds f
            JOIN embeddings e ON f.id = e.feed_id
            JOIN preferences p ON f.id = p.feed_id
            {interested_where}
            ORDER BY f.id DESC
            LIMIT %s
        ),
        feed_distances AS (
            -- Calculate minimum distance from each paper to any interested paper
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
                {exclude_clause}
            )
            {min_feed_id_filter}
            {age_filter}
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
    """


def sample_feeds_from_bins(all_feeds, sample_size, bins, base_model):
    """Sample papers from percentile-based bins with weighted distribution.

    Returns:
        tuple: (selected_feed_ids: list, metric_name: str, selected_values: list)
    """
    # Convert to numpy array for easier manipulation
    feed_ids = [f["feed_id"] for f in all_feeds]

    # Use prediction scores for model-based sampling, distances for distance-based
    if base_model:
        # For scores, we want to reverse the order for binning (higher scores = closer/better)
        values = np.array([f["prediction_score"] for f in all_feeds])
        # Reverse the array so higher scores are treated like smaller distances
        values = -values  # Negate so higher scores become lower values
        metric_name = "score"
    else:
        values = np.array([f["min_distance"] for f in all_feeds])
        metric_name = "distance"

    # Calculate percentile boundaries for equal-sized bins
    percentiles = np.linspace(0, 100, bins + 1)
    bin_edges = np.percentile(values, percentiles)

    # Ensure unique bin edges (in case of duplicate values)
    bin_edges = np.unique(bin_edges)
    actual_bins = len(bin_edges) - 1

    if actual_bins < bins:
        log.warning(f"Reduced to {actual_bins} bins due to duplicate {metric_name} values")

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

    # Format bin edges for display (convert back from negative for scores)
    display_edges = -bin_edges if base_model else bin_edges

    for i in range(min(5, actual_bins)):
        # Count feeds in this bin
        if i == actual_bins - 1:
            bin_mask = (values >= bin_edges[i]) & (values <= bin_edges[i + 1])
        else:
            bin_mask = (values >= bin_edges[i]) & (values < bin_edges[i + 1])
        feeds_in_bin = np.sum(bin_mask)
        log.info(f"  Bin {i+1} ({metric_name} {abs(display_edges[i]):.4f}-{abs(display_edges[i+1]):.4f}): "
                f"{samples_per_bin[i]} samples from {feeds_in_bin} papers")
    if actual_bins > 5:
        log.info(f"  ... ({actual_bins - 5} more bins)")
        # Count feeds in last bin
        bin_mask = (values >= bin_edges[-2]) & (values <= bin_edges[-1])
        feeds_in_bin = np.sum(bin_mask)
        log.info(f"  Bin {actual_bins} ({metric_name} {abs(display_edges[-2]):.4f}-{abs(display_edges[-1]):.4f}): "
                f"{samples_per_bin[-1]} samples from {feeds_in_bin} papers")

    log.info(f"Total samples to select: {samples_per_bin.sum()}")

    selected_feed_ids = []

    # Sample from each bin
    for i in range(actual_bins):
        if i == actual_bins - 1:
            # Last bin includes the maximum value
            bin_mask = (values >= bin_edges[i]) & (values <= bin_edges[i + 1])
        else:
            bin_mask = (values >= bin_edges[i]) & (values < bin_edges[i + 1])

        bin_feed_ids = np.array(feed_ids)[bin_mask]

        # Get the number of samples for this bin (already calculated above)
        n_samples = samples_per_bin[i]

        if len(bin_feed_ids) <= n_samples:
            # Take all feeds from this bin if we don't have enough
            selected = bin_feed_ids.tolist()
            log.info(f"Bin {i+1} ({metric_name} {abs(display_edges[i]):.4f}-{abs(display_edges[i+1]):.4f}): "
                    f"Selected all {len(selected)} papers (requested {n_samples})")
        else:
            # Random sample from this bin
            selected_indices = np.random.choice(len(bin_feed_ids), n_samples, replace=False)
            selected = bin_feed_ids[selected_indices].tolist()
            log.info(f"Bin {i+1} ({metric_name} {abs(display_edges[i]):.4f}-{abs(display_edges[i+1]):.4f}): "
                    f"Selected {len(selected)} papers from {len(bin_feed_ids)} available")

        selected_feed_ids.extend(selected)

    # Get actual values for selected feeds
    selected_values = []
    for feed_id in selected_feed_ids:
        feed_data = next((f for f in all_feeds if f["feed_id"] == feed_id), None)
        if feed_data:
            if base_model:
                selected_values.append(feed_data["prediction_score"])
            else:
                selected_values.append(feed_data["min_distance"])

    return selected_feed_ids, metric_name, selected_values


def determine_session_user(cursor, labeler_user_id, user_ids):
    """Determine which user should own the labeling session.

    Returns:
        int or None: User ID for the session, or None if no valid user found
    """
    if labeler_user_id:
        # Explicit labeler user ID provided - verify it exists
        cursor.execute("SELECT id, username FROM users WHERE id = %s", (labeler_user_id,))
        labeler_user = cursor.fetchone()

        if not labeler_user:
            log.error(f"User ID {labeler_user_id} not found in the database")
            log.info("")
            log.info("Please specify a valid user ID that exists in the database.")
            return None

        log.info(f"Using specified labeler user_id: {labeler_user_id} ({labeler_user['username']})")
        return labeler_user_id

    elif user_ids and len(user_ids) == 1:
        # Single user_id filter specified, use it as the labeler
        session_user_id = user_ids[0]
        # Get username for logging
        cursor.execute("SELECT username FROM users WHERE id = %s", (session_user_id,))
        user_result = cursor.fetchone()
        username = user_result['username'] if user_result else 'unknown'
        log.info(f"Using single filtered user_id as labeler: {session_user_id} ({username})")
        return session_user_id

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
            return None

        log.info(f"Using oldest admin user as labeler: {admin_user['id']} ({admin_user['username']})")
        return admin_user["id"]


def display_session_summary(stats, session_user_id, selected_values, metric_name, base_model, model_info, config_data, selected_feed_ids):
    """Display summary statistics for the created labeling session."""
    if selected_values:
        import statistics
        min_val = min(selected_values)
        max_val = max(selected_values)
        avg_val = statistics.mean(selected_values)
        std_val = statistics.stdev(selected_values) if len(selected_values) > 1 else 0

        log.info("="*60)
        log.info("Labeling session created successfully!")
        log.info("="*60)
        log.info(f"Total feeds in session: {stats['total_feeds']}")
        log.info(f"User ID: {session_user_id}")

        if base_model:
            log.info(f"Base model: {model_info['name']} (ID: {base_model})")
            log.info(f"Score range: {min_val:.4f} - {max_val:.4f}")
            log.info(f"Average score: {avg_val:.4f} (±{std_val:.4f})")
        else:
            log.info(f"Distance range: {min_val:.4f} - {max_val:.4f}")
            log.info(f"Average distance: {avg_val:.4f} (±{std_val:.4f})")
        log.info("")

        # Show distribution by quintiles
        log.info(f"Distribution by {metric_name} quintile:")
        sorted_values = sorted(zip(selected_feed_ids, selected_values),
                             key=lambda x: -x[1] if base_model else x[1])  # Reverse sort for scores
        quintile_size = len(sorted_values) // 5

        for q in range(5):
            start_idx = q * quintile_size
            end_idx = start_idx + quintile_size if q < 4 else len(sorted_values)
            quintile_data = sorted_values[start_idx:end_idx]

            if quintile_data:
                q_values = [d for _, d in quintile_data]
                log.info(f"  Q{q+1}: {len(quintile_data):4d} feeds "
                        f"({metric_name} {min(q_values):.4f}-{max(q_values):.4f})")
    else:
        log.info("="*60)
        log.info("Labeling session created successfully!")
        log.info(f"Total papers in session: {stats['total_feeds']}")
        log.info(f"User ID: {session_user_id}")

    # Show link to labeling interface
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

# Removed Click decorators - functions now called directly


def do_create_labeling_session(config_path, sample_size, bins, score_threshold, user_id, labeler_user_id, base_model, max_age, max_reference_papers, max_scan_papers):
    """Create a new labeling session with balanced sampling.

    This command supports two modes:

    1. Distance-based sampling (default):
       - Finds all papers labeled as interested (score >= threshold)
       - Calculates minimum cosine distance from each unlabeled paper to any interested paper
       - Divides papers into equal-sized bins based on distance
       - Samples with bias toward closer papers (4:1 ratio)

    2. Model-based sampling (--base-model):
       - Uses predicted preference scores from the specified model
       - Divides papers into equal-sized bins based on predicted scores
       - Samples with bias toward higher-scoring papers (4:1 ratio)
       - Does not require existing interested labels

    The labeling session is assigned to a user determined by:
    - --labeler-user-id if explicitly provided
    - --user-id if only one user_id is specified
    - The oldest admin user (lowest ID) otherwise
    """
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
        # Prepare user filter for queries - ensure user_ids is always a list for PostgreSQL ANY()
        if user_id:
            user_ids = list(user_id)  # Convert tuple to list if needed
        else:
            user_ids = None
        
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

        # Log max_age filter if specified
        if max_age > 0:
            log.info(f"Limiting to papers registered within the last {max_age} days")

        # Check if we have any feeds with embeddings first
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

        # Determine which user_id to use for the labeling session early
        session_user_id = determine_session_user(cursor, labeler_user_id, user_ids)
        if not session_user_id:
            cursor.close()
            db.close()
            return

        # Model-based sampling vs distance-based sampling
        model_info = None
        if base_model:
            # Check prerequisites for model-based mode
            success, model_info = check_prerequisites_for_model_mode(cursor, base_model, sample_size)
            if not success:
                cursor.close()
                db.close()
                return
        else:
            # Check prerequisites for distance-based mode
            success, interested_count = check_prerequisites_for_distance_mode(
                cursor, user_ids, user_filter, user_params, score_threshold
            )
            if not success:
                cursor.close()
                db.close()
                return

        # Clear existing labeling session for the specific user
        log.info(f"Clearing existing labeling session for user_id: {session_user_id}...")
        cursor.execute("DELETE FROM labeling_sessions WHERE user_id = %s", (session_user_id,))

        # Get feeds for sampling based on mode
        if base_model:
            all_feeds = get_feeds_for_model_mode(cursor, base_model, user_ids, max_age)
        else:
            all_feeds = get_feeds_for_distance_mode(cursor, score_threshold, user_ids, max_age, max_reference_papers, max_scan_papers)

        if not all_feeds:
            log.error("No unlabeled papers with embeddings found")
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
                log.info(f"All {total_with_embeddings} papers with embeddings have already been labeled{user_filter_msg}.")
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

        log.info(f"Found {len(all_feeds)} unlabeled papers with embeddings")

        # Sample feeds from percentile-based bins
        selected_feed_ids, metric_name, selected_values = sample_feeds_from_bins(
            all_feeds, sample_size, bins, base_model
        )

        # Insert selected feeds into labeling_sessions table
        log.info(f"Inserting {len(selected_feed_ids)} papers into labeling session for user_id: {session_user_id}...")

        # Insert selected feeds
        for feed_id in selected_feed_ids:
            cursor.execute("""
                INSERT INTO labeling_sessions (
                    feed_id, user_id, score, update_time
                ) VALUES (%s, %s, NULL, NULL)
            """, (feed_id, session_user_id))

        db.commit()

        # Get summary statistics
        cursor.execute("""
            SELECT COUNT(*) as total_feeds
            FROM labeling_sessions
            WHERE user_id = %s
        """, (session_user_id,))
        stats = cursor.fetchone()

        # Display session summary
        display_session_summary(
            stats, session_user_id, selected_values, metric_name,
            base_model, model_info, config_data, selected_feed_ids
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        log.error(f"Failed to create labeling session: {e}")
        db.rollback()
        raise
    finally:
        cursor.close()
        db.close()


def do_clear_labeling_session(config_path, labeler_user_id):
    """Clear labeling session for a specific user and show statistics.

    This command:
    1. Finds all labeling sessions for the specified user
    2. Shows statistics about labeled vs unlabeled items
    3. Removes all associated records from labeling_sessions table
    """
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

        response = input("Do you want to proceed with clearing this session? [y/N]: ")
        if response.lower() != 'y':
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
