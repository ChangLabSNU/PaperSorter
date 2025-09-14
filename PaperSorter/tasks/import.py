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

import os
import random
import sys
from datetime import datetime
import pandas as pd
import argparse
from ..cli.base import BaseCommand, registry
from ..cli.types import probability_float
from ..feed_database import FeedDatabase
from ..log import log, initialize_logging
from ..utils.pubmed_sync import (
    parse_pubmed_directory_chunked,
    sync_and_parse_pubmed
)


class ImportCommand(BaseCommand):
    """Import feeds from various sources."""

    name = 'import'
    help = 'Import feeds from various sources'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add import subcommands."""
        subparsers = parser.add_subparsers(
            dest='subcommand',
            help='Available import sources'
        )

        # Add pubmed subcommand
        pubmed_parser = subparsers.add_parser(
            'pubmed',
            help='Download recent PubMed update files and import to database'
        )
        pubmed_parser.add_argument(
            '--files', '-n',
            type=int,
            default=10,
            help='Number of recent update files to download (default: 10)'
        )
        pubmed_parser.add_argument(
            '--chunksize', '-c',
            type=int,
            default=2000,
            help='Number of articles per processing chunk (default: 2000)'
        )
        pubmed_parser.add_argument(
            '--tmpdir', '-t',
            help='Directory for downloaded files (default: $TMPDIR or ./tmp)'
        )
        pubmed_parser.add_argument(
            '--parse-only', '-p',
            help='Parse existing files in directory instead of downloading'
        )
        pubmed_parser.add_argument(
            '--limit', '-l',
            type=int,
            help='Maximum number of articles to import'
        )
        pubmed_parser.add_argument(
            '--sample-rate', '-s',
            type=probability_float,
            default=0.1,
            help='Random sampling rate (0.0-1.0) to reduce total count while maintaining diversity (default: 0.1)'
        )
        pubmed_parser.add_argument(
            '--seed',
            type=int,
            help='Random seed for reproducible sampling'
        )
        pubmed_parser.add_argument(
            '--issn',
            action='append',
            help='Filter by ISSN (can specify multiple times)'
        )

    def handle(self, args: argparse.Namespace, context) -> int:
        """Execute the import command."""
        initialize_logging('import', args.log_file, args.quiet)

        if args.subcommand == 'pubmed':
            try:
                do_import_pubmed(
                    config_path=args.config,
                    files=args.files,
                    chunksize=args.chunksize,
                    tmpdir=args.tmpdir,
                    parse_only=args.parse_only,
                    limit=args.limit,
                    sample_rate=args.sample_rate,
                    seed=args.seed,
                    issn=tuple(args.issn) if args.issn else ()
                )
                return 0
            except Exception as e:
                log.error(f"Import failed: {e}")
                return 1
        else:
            print("Please specify a subcommand: pubmed", file=sys.stderr)
            return 1

# Register the command
registry.register(ImportCommand)


def upsert_articles_from_dataframe(db: FeedDatabase, df: pd.DataFrame) -> tuple[int, int]:
    """Insert articles from a DataFrame into the database, skipping existing ones."""
    inserted = 0
    skipped = 0

    for _, row in df.iterrows():
        # Convert PMID to our external_id format
        external_id = f"pubmed:{row['pmid']}"

        # Parse publication date
        if pd.notna(row['pub_date']) and row['pub_date']:
            try:
                pub_date = pd.to_datetime(row['pub_date'])
            except (ValueError, TypeError):
                pub_date = datetime.now()
        else:
            pub_date = datetime.now()

        # Check if article exists
        db.cursor.execute(
            "SELECT id FROM feeds WHERE external_id = %s", (external_id,)
        )
        existing = db.cursor.fetchone()

        if existing:
            # Skip update - keep the newest (first processed) version
            skipped += 1
            log.debug(f"Skipped (already exists): {external_id}")
        else:
            # Insert new article
            db.insert_feed_item(
                external_id=external_id,
                title=row['title'] if pd.notna(row['title']) else '',
                content=row['abstract'] if pd.notna(row['abstract']) else '',
                author=row['authors'] if pd.notna(row['authors']) else '',
                origin='PubMed',
                journal=row['journal'] if pd.notna(row['journal']) else '',
                link=row['url'] if pd.notna(row['url']) else f"https://pubmed.ncbi.nlm.nih.gov/{row['pmid']}/",
                published=pub_date.timestamp(),
            )
            inserted += 1
            log.debug(f"Inserted: {external_id}")

    return inserted, skipped


def do_import_pubmed(config_path, files, chunksize, tmpdir, parse_only, limit, sample_rate, seed, issn):
    """Download recent PubMed update files and import to database.

    This command downloads the most recent PubMed update files from NCBI FTP
    and imports them into the database. Articles are processed from newest to
    oldest, and existing articles are skipped to preserve the most recent version.

    The --sample-rate option allows random subsampling to reduce the total
    number of articles while maintaining diversity across the entire dataset.
    This is useful for testing or when you want a representative subset
    of the data without importing everything.

    The --issn option filters articles by journal ISSN. You can specify multiple
    ISSNs, and articles from any matching journal will be included. Each article
    can have multiple ISSNs (print and electronic), and matching any ISSN to any
    of the specified filters will include the article.
    """
    log.info("Starting PubMed import")

    # Validate sampling rate
    if sample_rate is not None:
        if not 0.0 < sample_rate <= 1.0:
            raise ValueError("Sample rate must be between 0.0 and 1.0")
        log.info(f"Using random sampling rate: {sample_rate}")
        if seed is not None:
            random.seed(seed)
            log.info(f"Using random seed: {seed}")

    # Initialize database
    feeddb = FeedDatabase(config_path)

    # Convert ISSN filter to set for efficient lookup
    issn_filter = set(issn) if issn else None
    if issn_filter:
        log.info(f"Filtering by ISSNs: {', '.join(sorted(issn_filter))}")

    try:
        total_inserted = 0
        total_skipped_existing = 0  # Track articles skipped because they already exist
        total_processed = 0
        total_skipped_sampling = 0  # Track articles skipped due to sampling
        total_no_abstract = 0  # Track articles without abstracts
        total_no_matching_issn = 0  # Track articles filtered by ISSN

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
            n_no_match = 0  # Track ISSN filter removals for this chunk

            # Apply ISSN filter if specified
            if issn_filter:
                # Check if any article ISSN matches any filter ISSN
                def has_matching_issn(article_issns):
                    if not article_issns or (isinstance(article_issns, list) and len(article_issns) == 0):
                        return False
                    if isinstance(article_issns, list):
                        return any(issn in issn_filter for issn in article_issns)
                    return False

                has_match = chunk_df['issns'].apply(has_matching_issn)
                n_no_match = (~has_match).sum()
                total_no_matching_issn += n_no_match

                if n_no_match > 0:
                    chunk_df = chunk_df[has_match].copy()
                    log.debug(f"Filtered out {n_no_match} articles not matching ISSN filter from chunk of {original_size}")

                # Check if any articles remain after ISSN filtering
                if len(chunk_df) == 0:
                    log.debug("Skipping chunk - no articles matched ISSN filter")
                    continue

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
                    total_skipped_sampling += n_skipped
                    log.debug(f"Sampled {n_samples} articles from {size_after_filter} with abstracts (skipped {n_skipped})")
                else:
                    total_skipped_sampling += size_after_filter
                    continue

            # Apply limit if specified
            if limit and total_processed >= limit:
                log.info(f"Reached limit of {limit} articles")
                break

            if limit and total_processed + len(chunk_df) > limit:
                # Trim chunk to fit within limit
                remaining = limit - total_processed
                chunk_df = chunk_df.iloc[:remaining]

            # Sort by publication date (newest first)
            chunk_df['pub_date_parsed'] = pd.to_datetime(chunk_df['pub_date'], errors='coerce')
            chunk_df = chunk_df.sort_values('pub_date_parsed', ascending=False, na_position='last')
            chunk_df = chunk_df.drop('pub_date_parsed', axis=1)

            # Insert articles to database (skip existing ones)
            inserted, skipped = upsert_articles_from_dataframe(feeddb, chunk_df)
            total_inserted += inserted
            total_skipped_existing += skipped
            total_processed += len(chunk_df)

            # Commit after each chunk
            feeddb.commit()

            # Log with filtering and sampling information if applicable
            log_parts = [f"Processed chunk: {len(chunk_df)} articles"]
            if original_size != len(chunk_df):
                log_parts.append(f" from {original_size}")
            log_parts.append(f" (Total: {total_processed}, Inserted: {total_inserted}, Skipped existing: {total_skipped_existing}")

            if n_no_abstract > 0:
                log_parts.append(f", No abstract: {n_no_abstract}")
            if issn_filter and n_no_match > 0:
                log_parts.append(f", No ISSN match: {n_no_match}")
            if sample_rate is not None and sample_rate < 1.0 and n_skipped > 0:
                log_parts.append(f", Skipped by sampling: {n_skipped}")
            log_parts.append(")")

            log.info(''.join(log_parts))

        # Final summary
        summary_parts = [f"{total_inserted} inserted"]

        if total_skipped_existing > 0:
            summary_parts.append(f"{total_skipped_existing} skipped (already exist)")

        summary_parts.append(f"{total_processed} total processed")

        if total_no_abstract > 0:
            summary_parts.append(f"{total_no_abstract} filtered (no abstract)")

        if sample_rate is not None and sample_rate < 1.0:
            summary_parts.append(f"{total_skipped_sampling} skipped by sampling (rate: {sample_rate:.1%})")

        if issn_filter and total_no_matching_issn > 0:
            summary_parts.append(f"{total_no_matching_issn} filtered (no ISSN match)")

        log.info(f"Import complete: {', '.join(summary_parts)}")

        # Show guidance for next steps
        log.info("\n" + "="*60)
        log.info("Next steps to set up your paper recommendation system:")
        log.info("="*60)
        log.info("1. Generate embeddings for the imported articles:")
        log.info(f"   papersorter predict --count {total_inserted}")
        log.info("")
        log.info("2. Start the web interface to label papers:")
        log.info("   papersorter serve --skip-authentication your@email.com")
        log.info("")
        log.info("3. Use semantic search to find papers in your field")
        log.info("   and mark them as 'Interested' (at least 10-20 papers)")
        log.info("")
        log.info("4. Train your first model:")
        log.info("   papersorter train --name \"Initial Model\"")
        log.info("")
        log.info("5. Generate predictions:")
        log.info("   papersorter predict")
        log.info("="*60)

    except Exception as e:
        log.error(f"Import failed: {e}")
        feeddb.db.rollback()
        raise
    finally:
        del feeddb
