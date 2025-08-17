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
import os
import random
from datetime import datetime
import pandas as pd
from ..feed_database import FeedDatabase
from ..log import log, initialize_logging
from ..utils.pubmed_sync import (
    parse_pubmed_directory_chunked,
    sync_and_parse_pubmed
)

def upsert_articles_from_dataframe(db: FeedDatabase, df: pd.DataFrame) -> tuple[int, int]:
    """Insert or update articles from a DataFrame into the database."""
    inserted = 0
    updated = 0

    for _, row in df.iterrows():
        # Convert PMID to our external_id format
        external_id = f"pubmed:{row['pmid']}"

        # Parse publication date
        if pd.notna(row['pub_date']) and row['pub_date']:
            try:
                pub_date = pd.to_datetime(row['pub_date'])
            except:
                pub_date = datetime.now()
        else:
            pub_date = datetime.now()

        # Check if article exists
        db.cursor.execute(
            "SELECT id FROM feeds WHERE external_id = %s", (external_id,)
        )
        existing = db.cursor.fetchone()

        if existing:
            # Update existing article
            db.cursor.execute(
                """
                UPDATE feeds
                SET title = %s, content = %s, author = %s, origin = %s,
                    link = %s, published = to_timestamp(%s)
                WHERE external_id = %s
                """,
                (
                    row['title'] if pd.notna(row['title']) else '',
                    row['abstract'] if pd.notna(row['abstract']) else '',
                    row['authors'] if pd.notna(row['authors']) else '',
                    row['journal'] if pd.notna(row['journal']) else '',
                    row['url'] if pd.notna(row['url']) else f"https://pubmed.ncbi.nlm.nih.gov/{row['pmid']}/",
                    pub_date.timestamp(),
                    external_id,
                ),
            )
            updated += 1
            log.debug(f"Updated: {external_id}")
        else:
            # Insert new article
            db.insert_feed_item(
                external_id=external_id,
                title=row['title'] if pd.notna(row['title']) else '',
                content=row['abstract'] if pd.notna(row['abstract']) else '',
                author=row['authors'] if pd.notna(row['authors']) else '',
                origin=row['journal'] if pd.notna(row['journal']) else '',
                link=row['url'] if pd.notna(row['url']) else f"https://pubmed.ncbi.nlm.nih.gov/{row['pmid']}/",
                published=pub_date.timestamp(),
            )
            inserted += 1
            log.debug(f"Inserted: {external_id}")

    return inserted, updated


@click.group()
@click.option("--config", default="./config.yml", help="Path to configuration file")
@click.option("--log-file", help="Log file path")
@click.option("-q", "--quiet", is_flag=True, help="Suppress output")
@click.pass_context
def main(ctx, config, log_file, quiet):
    """Import feeds from various sources."""
    initialize_logging("import", log_file, quiet)
    ctx.ensure_object(dict)
    ctx.obj["config"] = config


@main.command("pubmed")
@click.option(
    "--files", "-n", default=10, type=int, help="Number of recent update files to download (default: 10)"
)
@click.option(
    "--chunksize", "-c", default=2000, type=int, help="Number of articles per processing chunk (default: 2000)"
)
@click.option(
    "--tmpdir", "-t", help="Directory for downloaded files (default: $TMPDIR or ./tmp)"
)
@click.option(
    "--parse-only", "-p", help="Parse existing files in directory instead of downloading"
)
@click.option(
    "--limit", "-l", type=int, help="Maximum number of articles to import"
)
@click.option(
    "--sample-rate", "-s", default=0.1, type=float, help="Random sampling rate (0.0-1.0) to reduce total count while maintaining diversity (default: 0.1)"
)
@click.option(
    "--seed", type=int, help="Random seed for reproducible sampling"
)
@click.pass_context
def import_pubmed(ctx, files, chunksize, tmpdir, parse_only, limit, sample_rate, seed):
    """Download recent PubMed update files and import to database.

    This command downloads the most recent PubMed update files from NCBI FTP
    and imports them into the database. Articles are processed in chronological
    order, and existing articles are updated if they already exist.

    The --sample-rate option allows random subsampling to reduce the total
    number of articles while maintaining diversity across the entire dataset.
    This is useful for testing or when you want a representative subset
    of the data without importing everything.
    """
    config_path = ctx.obj["config"]

    log.info("Starting PubMed import")

    # Validate sampling rate
    if sample_rate is not None:
        if not 0.0 < sample_rate <= 1.0:
            raise click.BadParameter("Sample rate must be between 0.0 and 1.0")
        log.info(f"Using random sampling rate: {sample_rate}")
        if seed is not None:
            random.seed(seed)
            log.info(f"Using random seed: {seed}")

    # Initialize database
    feeddb = FeedDatabase(config_path)

    try:
        total_inserted = 0
        total_updated = 0
        total_processed = 0
        total_skipped = 0  # Track articles skipped due to sampling
        total_no_abstract = 0  # Track articles without abstracts

        if parse_only:
            # Parse existing files in directory
            log.info(f"Parsing existing files in {parse_only}")
            chunk_generator = parse_pubmed_directory_chunked(
                parse_only, chunksize=chunksize
            )
        else:
            # Download and parse new files
            log.info(f"Downloading {files} most recent PubMed update files")
            if tmpdir:
                log.info(f"Using directory: {tmpdir}")

            # Set tmpdir environment variable if specified
            if tmpdir:
                os.environ['TMPDIR'] = tmpdir

            chunk_generator = sync_and_parse_pubmed(
                n_files=files, chunksize=chunksize
            )

        # Process chunks
        for chunk_df in chunk_generator:
            if len(chunk_df) == 0:
                continue

            original_size = len(chunk_df)

            # Filter out articles without abstracts
            # Check for non-empty abstracts (abstract field contains the content)
            has_abstract = chunk_df['abstract'].notna() & (chunk_df['abstract'].str.strip() != '')
            n_no_abstract = (~has_abstract).sum()
            total_no_abstract += n_no_abstract

            if n_no_abstract > 0:
                chunk_df = chunk_df[has_abstract].copy()
                log.debug(f"Filtered out {n_no_abstract} articles without abstracts from chunk of {original_size}")

            # Check if any articles remain after filtering
            if len(chunk_df) == 0:
                log.debug(f"Skipping chunk - all {original_size} articles lacked abstracts")
                continue

            size_after_filter = len(chunk_df)
            n_skipped = 0  # Initialize for logging

            # Apply random sampling if specified
            if sample_rate is not None and sample_rate < 1.0:
                # Sample the chunk to maintain diversity
                n_samples = int(size_after_filter * sample_rate)
                if n_samples > 0:
                    chunk_df = chunk_df.sample(n=n_samples, replace=False)
                    n_skipped = size_after_filter - n_samples
                    total_skipped += n_skipped
                    log.debug(f"Sampled {n_samples} articles from {size_after_filter} with abstracts (skipped {n_skipped})")
                else:
                    total_skipped += size_after_filter
                    continue

            # Apply limit if specified
            if limit and total_processed >= limit:
                log.info(f"Reached limit of {limit} articles")
                break

            if limit and total_processed + len(chunk_df) > limit:
                # Trim chunk to fit within limit
                remaining = limit - total_processed
                chunk_df = chunk_df.iloc[:remaining]

            # Sort by publication date (oldest first)
            chunk_df['pub_date_parsed'] = pd.to_datetime(chunk_df['pub_date'], errors='coerce')
            chunk_df = chunk_df.sort_values('pub_date_parsed', na_position='last')
            chunk_df = chunk_df.drop('pub_date_parsed', axis=1)

            # Upsert articles to database
            inserted, updated = upsert_articles_from_dataframe(feeddb, chunk_df)
            total_inserted += inserted
            total_updated += updated
            total_processed += len(chunk_df)

            # Commit after each chunk
            feeddb.commit()

            # Log with filtering and sampling information if applicable
            if sample_rate is not None and sample_rate < 1.0:
                log.info(f"Processed chunk: {len(chunk_df)} articles from {original_size} "
                        f"(Total: {total_processed}, Inserted: {total_inserted}, Updated: {total_updated}, "
                        f"No abstract: {n_no_abstract}, Skipped by sampling: {n_skipped})")
            elif n_no_abstract > 0:
                log.info(f"Processed chunk: {len(chunk_df)} articles from {original_size} "
                        f"(Total: {total_processed}, Inserted: {total_inserted}, Updated: {total_updated}, "
                        f"No abstract: {n_no_abstract})")
            else:
                log.info(f"Processed chunk: {len(chunk_df)} articles "
                        f"(Total: {total_processed}, Inserted: {total_inserted}, Updated: {total_updated})")

        # Final summary
        summary_parts = [f"{total_inserted} inserted", f"{total_updated} updated",
                        f"{total_processed} total processed"]

        if total_no_abstract > 0:
            summary_parts.append(f"{total_no_abstract} filtered (no abstract)")

        if sample_rate is not None and sample_rate < 1.0:
            summary_parts.append(f"{total_skipped} skipped by sampling (rate: {sample_rate:.1%})")

        log.info(f"Import complete: {', '.join(summary_parts)}")

    except Exception as e:
        log.error(f"Import failed: {e}")
        feeddb.db.rollback()
        raise
    finally:
        del feeddb