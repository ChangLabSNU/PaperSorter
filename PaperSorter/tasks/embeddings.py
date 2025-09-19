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

"""Embeddings management commands for PaperSorter."""

import argparse

from tabulate import tabulate

from ..config import get_config
from ..db import DatabaseManager, RealDictCursor

from ..log import log, initialize_logging
from ..cli.base import BaseCommand, registry
from ..data.schema import get_schema


class EmbeddingsCommand(BaseCommand):
    """Manage embeddings table and indices."""

    name = 'embeddings'
    help = 'Manage embeddings table and indices'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add embeddings-specific arguments."""
        subparsers = parser.add_subparsers(dest='subcommand', help='Embeddings management commands')
        subparsers.required = True

        # Clear subcommand
        clear_parser = subparsers.add_parser('clear', help='Remove all embeddings from database')
        clear_parser.add_argument('--force', action='store_true',
                                help='Skip confirmation prompt')

        # Reset subcommand
        reset_parser = subparsers.add_parser('reset',
                                            help='Drop and recreate embeddings table with updated dimensions')
        reset_parser.add_argument('--force', action='store_true',
                                help='Skip confirmation prompt')

        # Status subcommand
        status_parser = subparsers.add_parser('status',
                                             help='Show embeddings table status and statistics')
        status_parser.add_argument('--detailed', action='store_true',
                                  help='Show detailed statistics')

        # Index subcommand
        index_parser = subparsers.add_parser('index',
                                            help='Manage embeddings index')
        index_action = index_parser.add_subparsers(dest='action', help='Index actions')
        index_action.required = True

        # Index on
        index_on = index_action.add_parser('on', help='Create HNSW index for similarity search')
        index_on.add_argument('--m', type=int, default=16,
                            help='HNSW M parameter (default: 16)')
        index_on.add_argument('--ef-construction', type=int, default=64,
                            help='HNSW ef_construction parameter (default: 64)')

        # Index off
        index_off = index_action.add_parser('off', help='Drop HNSW index')
        index_off.add_argument('--force', action='store_true',
                             help='Skip confirmation prompt')

    def handle(self, args: argparse.Namespace, context) -> int:
        """Execute the embeddings command."""
        initialize_logging('embeddings', args.log_file, args.quiet)

        self.config = get_config(args.config).raw

        self.db_config = self.config['db']
        self.embedding_dimensions = self.config.get('embedding_api', {}).get('dimensions', 1536)
        self.schema = 'papersorter'

        self.db_manager = DatabaseManager.from_config(
            self.db_config,
            application_name="papersorter-cli-embeddings",
        )
        self.conn = None

        try:
            self.conn = self.db_manager.connect()
            self.conn.autocommit = False

            # Dispatch to appropriate subcommand handler
            subcommand = args.subcommand

            if subcommand == 'index':
                # Handle index subcommands
                if args.action == 'on':
                    return self.handle_index_on(args)
                elif args.action == 'off':
                    return self.handle_index_off(args)
            else:
                handler = getattr(self, f'handle_{subcommand}')
                return handler(args)
        finally:
            if self.conn is not None:
                self.conn.close()
            self.db_manager.close()

    def handle_clear(self, args: argparse.Namespace) -> int:
        """Clear all embeddings from the database."""
        cursor = self.conn.cursor()

        try:
            # Get current count
            cursor.execute(f"SELECT COUNT(*) FROM {self.schema}.embeddings")
            count = cursor.fetchone()[0]

            if count == 0:
                log.info("No embeddings to clear")
                return 0

            # Confirm action if not forced
            if not args.force:
                if not args.quiet:
                    response = input(f"This will delete {count:,} embeddings. Continue? [y/N]: ")
                    if response.lower() != 'y':
                        log.info("Operation cancelled")
                        return 0

            # Clear embeddings
            log.info(f"Clearing {count:,} embeddings...")
            cursor.execute(f"TRUNCATE TABLE {self.schema}.embeddings")
            self.conn.commit()

            log.info(f"Successfully cleared {count:,} embeddings")
            return 0

        except Exception as e:
            self.conn.rollback()
            log.error(f"Failed to clear embeddings: {e}")
            return 1

    def handle_reset(self, args: argparse.Namespace) -> int:
        """Reset embeddings table with updated dimensions."""
        cursor = self.conn.cursor()

        try:
            # Get current embeddings count
            cursor.execute(f"SELECT COUNT(*) FROM {self.schema}.embeddings")
            count = cursor.fetchone()[0]

            # Get current vector dimensions
            cursor.execute(f"""
                SELECT atttypmod
                FROM pg_attribute
                WHERE attrelid = '{self.schema}.embeddings'::regclass
                AND attname = 'embedding'
            """)
            result = cursor.fetchone()
            current_dim = result[0] if result else None

            if not args.quiet:
                log.info(f"Current embeddings: {count:,}")
                log.info(f"Current dimensions: {current_dim}")
                log.info(f"New dimensions from config: {self.embedding_dimensions}")

            # Confirm action if not forced
            if not args.force and count > 0:
                if not args.quiet:
                    response = input(f"This will delete {count:,} embeddings and recreate the table. Continue? [y/N]: ")
                    if response.lower() != 'y':
                        log.info("Operation cancelled")
                        return 0

            # Drop existing indexes
            log.info("Dropping existing indexes...")
            cursor.execute(f"""
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = '{self.schema}' AND tablename = 'embeddings'
            """)
            indexes = cursor.fetchall()

            for (index_name,) in indexes:
                log.info(f"  Dropping index {index_name}")
                cursor.execute(f"DROP INDEX IF EXISTS {self.schema}.{index_name}")

            # Drop and recreate table
            log.info("Dropping embeddings table...")
            cursor.execute(f"DROP TABLE IF EXISTS {self.schema}.embeddings CASCADE")

            log.info(f"Creating embeddings table with {self.embedding_dimensions} dimensions...")

            # Get schema definition
            schema = get_schema(self.embedding_dimensions)

            # Find embeddings table definition
            embeddings_table = None
            for table in schema['TABLES']:
                if table['name'] == 'embeddings':
                    embeddings_table = table
                    break

            if not embeddings_table:
                raise ValueError("Embeddings table definition not found in schema")

            # Create table with schema-aware column definitions
            columns = []
            for name, definition in embeddings_table['columns']:
                # Replace schema placeholder if present
                if '{schema}' in definition:
                    definition = definition.format(schema=self.schema)
                columns.append(f"{name} {definition}")
            columns_str = ", ".join(columns)
            cursor.execute(f"CREATE TABLE {self.schema}.embeddings ({columns_str})")

            # Recreate default HNSW index matching schema definition
            cursor.execute(f"""
                CREATE INDEX embeddings_embedding_idx
                ON {self.schema}.embeddings
                USING hnsw (embedding public.vector_cosine_ops)
            """)
            log.info("Created default HNSW index")

            self.conn.commit()
            log.info(f"Successfully reset embeddings table with {self.embedding_dimensions} dimensions")
            return 0

        except Exception as e:
            self.conn.rollback()
            log.error(f"Failed to reset embeddings table: {e}")
            return 1

    def handle_status(self, args: argparse.Namespace) -> int:
        """Show embeddings table status and statistics."""
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get embeddings count
            cursor.execute(f"SELECT COUNT(*) as count FROM {self.schema}.embeddings")
            embeddings_count = cursor.fetchone()['count']

            # Get feeds count
            cursor.execute(f"SELECT COUNT(*) as count FROM {self.schema}.feeds")
            feeds_count = cursor.fetchone()['count']

            # Calculate percentage
            percentage = (embeddings_count / feeds_count * 100) if feeds_count > 0 else 0

            # Get vector dimensions
            cursor.execute(f"""
                SELECT atttypmod
                FROM pg_attribute
                WHERE attrelid = '{self.schema}.embeddings'::regclass
                AND attname = 'embedding'
            """)
            result = cursor.fetchone()
            dimensions = result['atttypmod'] if result else 'Unknown'

            # Get table size
            cursor.execute(f"""
                SELECT pg_size_pretty(pg_total_relation_size('{self.schema}.embeddings')) as size
            """)
            table_size = cursor.fetchone()['size']

            # Get index information
            cursor.execute(f"""
                SELECT
                    i.indexname,
                    am.amname as index_type,
                    pg_size_pretty(pg_relation_size((i.schemaname || '.' || i.indexname)::regclass)) as size
                FROM pg_indexes i
                JOIN pg_class c ON c.relname = i.indexname
                JOIN pg_am am ON c.relam = am.oid
                WHERE i.schemaname = '{self.schema}' AND i.tablename = 'embeddings'
            """)
            indexes = cursor.fetchall()

            # Basic statistics
            stats = [
                ["Total Embeddings", f"{embeddings_count:,}"],
                ["Total Articles", f"{feeds_count:,}"],
                ["Coverage", f"{percentage:.1f}%"],
                ["Vector Dimensions", dimensions],
                ["Table Size", table_size],
            ]

            # Add index status
            if indexes:
                for idx in indexes:
                    stats.append([f"Index ({idx['index_type']})", f"{idx['indexname']} ({idx['size']})"])
            else:
                stats.append(["Index", "None"])

            if args.detailed:

                # Get articles without embeddings by source
                cursor.execute(f"""
                    SELECT
                        fs.name as source,
                        COUNT(f.id) as total,
                        COUNT(e.feed_id) as with_embeddings,
                        COUNT(f.id) - COUNT(e.feed_id) as without_embeddings
                    FROM {self.schema}.feeds f
                    LEFT JOIN {self.schema}.feed_sources fs ON f.origin = fs.name
                    LEFT JOIN {self.schema}.embeddings e ON f.id = e.feed_id
                    GROUP BY fs.name
                    ORDER BY without_embeddings DESC
                """)
                sources = cursor.fetchall()

                # Recent embedding activity
                cursor.execute(f"""
                    SELECT
                        DATE(f.added) as date,
                        COUNT(DISTINCT f.id) as articles_added,
                        COUNT(DISTINCT e.feed_id) as embeddings_created
                    FROM {self.schema}.feeds f
                    LEFT JOIN {self.schema}.embeddings e ON f.id = e.feed_id
                    WHERE f.added >= CURRENT_DATE - INTERVAL '7 days'
                    GROUP BY DATE(f.added)
                    ORDER BY date DESC
                """)
                recent_activity = cursor.fetchall()

            # Print basic statistics
            print("\n=== Embeddings Table Status ===\n")
            print(tabulate(stats, headers=["Metric", "Value"], tablefmt="simple"))

            if args.detailed:
                # Print index information
                if indexes:
                    print("\n=== Indexes ===\n")
                    index_data = [[idx['indexname'], idx['size']] for idx in indexes]
                    print(tabulate(index_data, headers=["Index Name", "Size"], tablefmt="simple"))

                # Print source statistics
                if sources:
                    print("\n=== Coverage by Source ===\n")
                    source_data = [
                        [
                            s['source'] or 'Unknown',
                            f"{s['total']:,}",
                            f"{s['with_embeddings']:,}",
                            f"{s['without_embeddings']:,}",
                            f"{(s['with_embeddings']/s['total']*100 if s['total'] > 0 else 0):.1f}%"
                        ]
                        for s in sources[:10]  # Show top 10
                    ]
                    print(tabulate(source_data,
                                 headers=["Source", "Total", "With Embeddings", "Without", "Coverage"],
                                 tablefmt="simple"))

                # Print recent activity
                if recent_activity:
                    print("\n=== Recent Activity (Last 7 Days) ===\n")
                    activity_data = [
                        [
                            a['date'].strftime('%Y-%m-%d'),
                            f"{a['articles_added']:,}",
                            f"{a['embeddings_created']:,}",
                            f"{(a['embeddings_created']/a['articles_added']*100 if a['articles_added'] > 0 else 0):.1f}%"
                        ]
                        for a in recent_activity
                    ]
                    print(tabulate(activity_data,
                                 headers=["Date", "Articles Added", "Embeddings Created", "Coverage"],
                                 tablefmt="simple"))

            return 0

        except Exception as e:
            log.error(f"Failed to get embeddings status: {e}")
            return 1

    def handle_index_on(self, args: argparse.Namespace) -> int:
        """Create HNSW index for similarity search."""
        cursor = self.conn.cursor()

        try:
            # Check if index already exists
            cursor.execute(f"""
                SELECT COUNT(*)
                FROM pg_indexes
                WHERE schemaname = '{self.schema}' AND tablename = 'embeddings'
                AND indexname = 'embeddings_embedding_idx'
            """)

            if cursor.fetchone()[0] > 0:
                log.info("HNSW index already exists (embeddings_embedding_idx)")
                return 0

            # Get embeddings count for progress info
            cursor.execute(f"SELECT COUNT(*) FROM {self.schema}.embeddings")
            count = cursor.fetchone()[0]

            log.info(f"Creating HNSW index on {count:,} embeddings...")
            log.info(f"Parameters: m={args.m}, ef_construction={args.ef_construction}")

            # Create index with specified parameters matching schema
            cursor.execute(f"""
                CREATE INDEX embeddings_embedding_idx
                ON {self.schema}.embeddings
                USING hnsw (embedding public.vector_cosine_ops)
                WITH (m = {args.m}, ef_construction = {args.ef_construction})
            """)

            self.conn.commit()

            # Get index size
            cursor.execute(f"""
                SELECT pg_size_pretty(pg_relation_size('{self.schema}.embeddings_embedding_idx'::regclass)) as size
            """)
            size = cursor.fetchone()[0]

            log.info(f"Successfully created HNSW index (size: {size})")
            return 0

        except Exception as e:
            self.conn.rollback()
            log.error(f"Failed to create index: {e}")
            return 1

    def handle_index_off(self, args: argparse.Namespace) -> int:
        """Drop HNSW index."""
        cursor = self.conn.cursor()

        try:
            # Check if index exists
            cursor.execute(f"""
                SELECT
                    indexname,
                    pg_size_pretty(pg_relation_size((schemaname || '.' || indexname)::regclass)) as size
                FROM pg_indexes
                WHERE schemaname = '{self.schema}' AND tablename = 'embeddings'
                AND indexname = 'embeddings_embedding_idx'
            """)

            result = cursor.fetchone()
            if not result:
                log.info("HNSW index does not exist")
                return 0

            index_name, index_size = result

            # Confirm action if not forced
            if not args.force:
                if not args.quiet:
                    response = input(f"This will drop the HNSW index ({index_size}). Continue? [y/N]: ")
                    if response.lower() != 'y':
                        log.info("Operation cancelled")
                        return 0

            log.info(f"Dropping HNSW index ({index_size})...")
            cursor.execute(f"DROP INDEX {self.schema}.{index_name}")
            self.conn.commit()

            log.info("Successfully dropped HNSW index")
            log.info("Note: Similarity searches will be slower without the index")
            return 0

        except Exception as e:
            self.conn.rollback()
            log.error(f"Failed to drop index: {e}")
            return 1


# Register the command
registry.register(EmbeddingsCommand)
