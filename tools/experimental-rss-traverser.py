#!/usr/bin/env python3
"""
Experimental RSS feed traverser that checks feed sources and generates SQL inserts.

This script:
1. Queries feed_sources table for RSS sources not checked recently
2. Fetches RSS/ATOM feeds from their URLs
3. Parses the feed entries
4. Generates SQL INSERT statements for the feeds table
"""

import argparse
import feedparser
import psycopg2
import psycopg2.extras
import sys
import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import uuid


def load_config(config_file: str) -> dict:
    """Load database configuration from YAML file."""
    config_path = Path(config_file)
    if not config_path.exists():
        print(f"Error: Configuration file '{config_file}' not found.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML configuration: {e}", file=sys.stderr)
        sys.exit(1)

    if "db" not in config:
        print("Error: No 'db' section found in configuration file.", file=sys.stderr)
        sys.exit(1)

    return config["db"]


def connect_db(db_config: dict):
    """Connect to PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host=db_config["host"],
            database=db_config["database"],
            user=db_config["user"],
            password=db_config.get("password", ""),
            port=db_config.get("port", 5432),
        )
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to database: {e}", file=sys.stderr)
        sys.exit(1)


def ensure_temp_table_exists(conn):
    """Create the temporary duplicate check table if it doesn't exist."""
    create_table_query = """
        CREATE TABLE IF NOT EXISTS papersorter.migrtmp_rss_dup_check (
            external_id TEXT PRIMARY KEY,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """
    with conn.cursor() as cur:
        cur.execute(create_table_query)
        conn.commit()


def check_duplicate_ids(conn, external_ids: List[str]) -> set:
    """Check which external IDs already exist in feeds table or temp table."""
    if not external_ids:
        return set()

    # Create placeholders for the query
    placeholders = ",".join(["%s"] * len(external_ids))

    query = f"""
        SELECT external_id
        FROM (
            SELECT external_id FROM papersorter.feeds WHERE external_id IN ({placeholders})
            UNION
            SELECT external_id FROM papersorter.migrtmp_rss_dup_check WHERE external_id IN ({placeholders})
        ) AS combined
    """

    with conn.cursor() as cur:
        # Pass the external_ids list twice (for both IN clauses)
        cur.execute(query, external_ids + external_ids)
        return {row[0] for row in cur.fetchall()}


def insert_ids_to_temp_table(conn, external_ids: List[str]):
    """Insert new external IDs into the temporary duplicate check table."""
    if not external_ids:
        return

    # Use INSERT ... ON CONFLICT DO NOTHING to handle any race conditions
    query = """
        INSERT INTO papersorter.migrtmp_rss_dup_check (external_id)
        VALUES %s
        ON CONFLICT (external_id) DO NOTHING
    """

    with conn.cursor() as cur:
        values = [(id,) for id in external_ids]
        psycopg2.extras.execute_values(cur, query, values)
        conn.commit()


def get_unchecked_sources(conn, check_interval_hours: int) -> List[Dict]:
    """Get RSS sources that haven't been checked in the specified interval."""
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=check_interval_hours)

    query = """
        SELECT id, name, url, last_updated
        FROM papersorter.feed_sources
        WHERE source_type = 'rss'
          AND (last_updated IS NULL OR last_updated < %s)
        ORDER BY last_updated ASC NULLS FIRST
    """

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(query, (cutoff_time,))
        return [dict(row) for row in cur.fetchall()]


def parse_feed(url: str) -> Optional[feedparser.FeedParserDict]:
    """Parse RSS/ATOM feed from URL."""
    try:
        feed = feedparser.parse(url)
        if feed.bozo and feed.bozo_exception:
            print(
                f"Warning: Feed parsing error for {url}: {feed.bozo_exception}",
                file=sys.stderr,
            )
        return feed
    except Exception as e:
        print(f"Error fetching feed from {url}: {e}", file=sys.stderr)
        return None


def generate_external_id(entry: dict) -> str:
    """Generate a unique external ID for the feed entry."""
    # Generate UUID v5 (namespace-based) using URL namespace
    # Use the entry's link as the name, fallback to title if no link
    entry_url = entry.get("link", "") or entry.get("title", "")
    if entry_url:
        # UUID namespace for URLs (standard UUID namespace)
        url_namespace = uuid.NAMESPACE_URL
        return str(uuid.uuid5(url_namespace, entry_url))
    else:
        # Fallback to random UUID if no identifying information
        return str(uuid.uuid4())


def parse_published_date(entry: dict) -> datetime:
    """Parse published date from feed entry."""
    # Try different date fields
    date_fields = ["published_parsed", "updated_parsed", "created_parsed"]

    for field in date_fields:
        if hasattr(entry, field) and getattr(entry, field):
            try:
                time_tuple = getattr(entry, field)
                return datetime.fromtimestamp(
                    feedparser._parse_date(str(time_tuple)).timestamp(), tz=timezone.utc
                )
            except Exception:
                pass

    # Default to current time if no date found
    return datetime.now(timezone.utc)


def escape_sql_string(value: Optional[str]) -> str:
    """Escape string for SQL insertion."""
    if value is None:
        return "NULL"
    # Escape single quotes by doubling them
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def generate_insert_sql(
    conn, source: Dict, entries: List[dict]
) -> Tuple[List[str], List[str]]:
    """Generate SQL INSERT statements for feed entries.

    Returns:
        Tuple of (sql_statements, new_external_ids)
    """
    sql_statements = []

    # First, collect all external IDs
    entry_data = []
    for entry in entries:
        external_id = generate_external_id(entry)
        entry_data.append(
            {
                "external_id": external_id,
                "title": entry.get("title", "Untitled"),
                "content": entry.get("summary", entry.get("description", "")),
                "author": entry.get("author", ""),
                "origin": source["name"],
                "link": entry.get("link", ""),
                "published": parse_published_date(entry),
            }
        )

    # Check for duplicates
    all_ids = [e["external_id"] for e in entry_data]
    duplicate_ids = check_duplicate_ids(conn, all_ids)

    # Filter out duplicates and collect new IDs
    new_ids = []
    for data in entry_data:
        if data["external_id"] not in duplicate_ids:
            new_ids.append(data["external_id"])

            # Build SQL INSERT statement
            sql = f"""INSERT INTO papersorter.feeds (external_id, title, content, author, origin, link, published)
VALUES (
    {escape_sql_string(data["external_id"])},
    {escape_sql_string(data["title"])},
    {escape_sql_string(data["content"])},
    {escape_sql_string(data["author"])},
    {escape_sql_string(data["origin"])},
    {escape_sql_string(data["link"])},
    '{data["published"].isoformat()}'
)
ON CONFLICT (external_id) DO NOTHING;"""

            sql_statements.append(sql)

    return sql_statements, new_ids


def update_source_timestamp(conn, source_id: int):
    """Update the last_updated timestamp for a feed source."""
    query = """
        UPDATE papersorter.feed_sources
        SET last_updated = %s
        WHERE id = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (datetime.now(timezone.utc), source_id))
        conn.commit()


def main():
    parser = argparse.ArgumentParser(
        description="Experimental RSS feed traverser for PaperSorter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check feeds not updated in last 24 hours
  %(prog)s

  # Check feeds not updated in last 6 hours
  %(prog)s --check-interval 6

  # Use custom config and limit entries
  %(prog)s -c custom/config.yml --max-entries 10

  # Dry run without updating timestamps
  %(prog)s --dry-run
""",
    )

    parser.add_argument(
        "-c",
        "--config",
        default="qbio/config.yml",
        help="Path to configuration file (default: qbio/config.yml)",
    )

    parser.add_argument(
        "--check-interval",
        type=int,
        default=24,
        help="Hours since last check (default: 24)",
    )

    parser.add_argument(
        "--max-entries",
        type=int,
        default=50,
        help="Maximum entries per feed (default: 50)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't update timestamps, just output SQL",
    )

    parser.add_argument("-o", "--output", help="Output SQL to file instead of stdout")

    args = parser.parse_args()

    # Load configuration and connect to database
    db_config = load_config(args.config)
    conn = connect_db(db_config)

    try:
        # Ensure temporary table exists
        ensure_temp_table_exists(conn)

        # Get sources to check
        sources = get_unchecked_sources(conn, args.check_interval)

        if not sources:
            print(
                f"No RSS sources need checking (interval: {args.check_interval} hours)",
                file=sys.stderr,
            )
            return

        print(f"Found {len(sources)} RSS sources to check", file=sys.stderr)

        all_sql_statements = []
        all_new_ids = []

        # Process each source
        for source in sources:
            print(f"\nProcessing: {source['name']} - {source['url']}", file=sys.stderr)

            # Parse feed
            feed = parse_feed(source["url"])
            if not feed:
                continue

            # Extract entries (limited by max_entries)
            entries = feed.entries[: args.max_entries]
            print(f"  Found {len(entries)} entries", file=sys.stderr)

            # Generate SQL statements and get new IDs
            sql_statements, new_ids = generate_insert_sql(conn, source, entries)
            all_sql_statements.extend(sql_statements)
            all_new_ids.extend(new_ids)

            print(
                f"  {len(new_ids)} new entries, {len(entries) - len(new_ids)} duplicates skipped",
                file=sys.stderr,
            )

            # Update timestamp unless dry run
            if not args.dry_run:
                update_source_timestamp(conn, source["id"])
                print("  Updated last_checked timestamp", file=sys.stderr)

        # Insert new IDs to temp table unless dry run
        if not args.dry_run and all_new_ids:
            insert_ids_to_temp_table(conn, all_new_ids)
            print(
                f"\nInserted {len(all_new_ids)} new IDs to temporary duplicate check table",
                file=sys.stderr,
            )

        # Output SQL statements
        output_sql = "\n\n".join(all_sql_statements)

        if args.output:
            with open(args.output, "w") as f:
                f.write(output_sql)
            print(
                f"\nWrote {len(all_sql_statements)} SQL statements to {args.output}",
                file=sys.stderr,
            )
        else:
            print("\n-- Generated SQL INSERT statements:")
            print(output_sql)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
