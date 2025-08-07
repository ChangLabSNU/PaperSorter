#!/usr/bin/env python3
"""
Temporary deduplication script for feeds table.
Finds duplicate items with identical titles where id >= 50000 has a duplicate with id < 50000.
Updates the older item's external_id to the newer item's and removes the newer item.
"""

import sys
import os
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
import yaml
import logging

# Add parent directory to path to import PaperSorter modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)


def load_config(config_path):
    """Load database configuration from YAML file."""
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config["db"]


def find_duplicates(conn, dry_run=True):
    """Find and process duplicate feed items."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Find all items with id >= 50000 that have potential duplicates with id < 50000
        query = """
            SELECT
                new.id as new_id,
                new.external_id as new_external_id,
                new.title,
                new.link,
                new.published as new_published,
                old.id as old_id,
                old.external_id as old_external_id,
                old.published as old_published
            FROM papersorter.feeds new
            INNER JOIN papersorter.feeds old ON new.title = old.title
            WHERE new.id >= 50000
              AND old.id < 50000
            ORDER BY new.id, old.id DESC
        """

        cur.execute(query)
        duplicates = cur.fetchall()

        if not duplicates:
            log.info("No duplicates found")
            return

        # Group by new_id to handle multiple old duplicates
        from collections import defaultdict

        grouped = defaultdict(list)
        for row in duplicates:
            grouped[row["new_id"]].append(row)

        log.info(f"Found {len(grouped)} items with potential duplicates")

        updates = []
        deletes = []
        skipped = 0

        for new_id, matches in grouped.items():
            # Skip items with >= 5 duplicates (likely generic titles like "Table of Contents")
            if len(matches) >= 6:
                log.info(
                    f"Skipping item {new_id} with generic title: '{matches[0]['title'][:80]}...' ({len(matches)} duplicates)"
                )
                skipped += 1
                continue

            # When multiple old duplicates exist, take the newest one (highest id < 50000)
            # Since we ordered by old.id DESC, the first match is the newest
            best_match = matches[0]

            log.info(
                f"Item {new_id} (external_id: {best_match['new_external_id'][:50]}...)"
            )
            log.info(f"  Title: {best_match['title'][:80]}...")
            log.info(
                f"  Matches old item {best_match['old_id']} (external_id: {best_match['old_external_id'][:50]}...)"
            )

            if len(matches) > 1:
                log.info(
                    f"  Note: {len(matches)} old duplicates found, using newest (id={best_match['old_id']})"
                )

            updates.append((best_match["new_external_id"], best_match["old_id"]))
            deletes.append(new_id)

        if skipped > 0:
            log.info(f"\nSkipped {skipped} items with generic titles (>= 6 duplicates)")

        if dry_run:
            log.info("\n=== DRY RUN - No changes made ===")
            log.info(f"Would update {len(updates)} old items with new external_ids")
            log.info(f"Would delete {len(deletes)} newer duplicate items")
        else:
            log.info("\n=== Applying changes ===")

            # First, check for any references to the items we're about to delete
            check_references(conn, deletes)

            # Process each duplicate pair
            # We need to delete the new item first due to unique constraint on external_id
            for (new_external_id, old_id), delete_id in zip(updates, deletes):
                # Step 1: Delete related records for the newer item
                delete_related_records(conn, delete_id)

                # Step 2: Delete the newer feed item
                cur.execute("DELETE FROM papersorter.feeds WHERE id = %s", (delete_id,))
                log.info(f"Deleted item {delete_id}")

                # Step 3: Update the older item with the new external_id
                cur.execute(
                    """
                    UPDATE papersorter.feeds
                    SET external_id = %s
                    WHERE id = %s
                """,
                    (new_external_id, old_id),
                )
                log.info(
                    f"Updated item {old_id} with external_id: {new_external_id[:50]}..."
                )

            conn.commit()
            log.info(
                f"\nSuccessfully updated {len(updates)} items and deleted {len(deletes)} duplicates"
            )


def check_references(conn, feed_ids):
    """Check for references to feeds that will be deleted."""
    with conn.cursor() as cur:
        # Check each related table
        tables = ["embeddings", "preferences", "predicted_preferences", "broadcasts"]

        for table in tables:
            cur.execute(
                f"""
                SELECT COUNT(*) FROM papersorter.{table}
                WHERE feed_id = ANY(%s)
            """,
                (feed_ids,),
            )
            count = cur.fetchone()[0]
            if count > 0:
                log.warning(f"Found {count} references in {table} table")


def delete_related_records(conn, feed_id):
    """Delete related records before deleting feed item."""
    with conn.cursor() as cur:
        tables = ["embeddings", "preferences", "predicted_preferences", "broadcasts"]

        for table in tables:
            cur.execute(
                f"DELETE FROM papersorter.{table} WHERE feed_id = %s", (feed_id,)
            )
            if cur.rowcount > 0:
                log.debug(
                    f"Deleted {cur.rowcount} records from {table} for feed_id {feed_id}"
                )


def main():
    parser = argparse.ArgumentParser(description="Deduplicate feed items by title")
    parser.add_argument(
        "--config", default="./config.yml", help="Path to config file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    args = parser.parse_args()

    # Load database configuration
    db_config = load_config(args.config)

    # Connect to database
    conn = psycopg2.connect(
        host=db_config["host"],
        database=db_config["database"],
        user=db_config["user"],
        password=db_config["password"],
    )

    try:
        find_duplicates(conn, dry_run=args.dry_run)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
