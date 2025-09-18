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

import psycopg2
from ..config import get_config
from ..db import DatabaseManager
import argparse
from ..log import log
from ..data.schema import get_schema
from ..cli.base import BaseCommand, registry


class InitCommand(BaseCommand):
    """Initialize database tables and schema for PaperSorter."""

    name = 'init'
    help = 'Initialize database tables and schema for PaperSorter'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add init-specific arguments."""
        parser.add_argument(
            '--schema',
            default='papersorter',
            help='Database schema name'
        )
        parser.add_argument(
            '--drop-existing',
            action='store_true',
            help='Drop existing tables first'
        )

    def handle(self, args: argparse.Namespace, context) -> int:
        """Execute the init command."""
        # Delegate to the existing main function
        try:
            main(
                config=args.config,
                schema=args.schema,
                drop_existing=args.drop_existing,
                quiet=args.quiet
            )
            return 0
        except Exception:
            return 1

# Register the command
registry.register(InitCommand)


def main(config, schema, drop_existing, quiet):
    """Initialize database tables and schema for PaperSorter."""

    if not quiet:
        log.info("Initializing PaperSorter database...")

    cfg = get_config(config).raw

    db_config = cfg["db"]

    # Get embedding dimensions from config (default to 1536)
    embedding_dimensions = cfg.get("embedding_api", {}).get("dimensions", 1536)

    # Get schema with configured embedding dimensions
    db_schema = get_schema(embedding_dimensions)

    if not quiet:
        log.info(f"Using embedding dimensions: {embedding_dimensions}")

    db_manager = DatabaseManager.from_config(
        db_config,
        application_name="papersorter-cli-init",
    )

    try:
        with db_manager.session(autocommit=True) as session:
            cursor = session.cursor()

            if not quiet:
                log.info("Checking pgvector extension...")
            try:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                if not quiet:
                    log.info("pgvector extension is ready.")
            except psycopg2.errors.InsufficientPrivilege:
                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_extension WHERE extname = 'vector'
                    )
                """
                )
                extension_exists = cursor.fetchone()[0]

                if extension_exists:
                    if not quiet:
                        log.info("pgvector extension is already installed.")
                else:
                    log.error("Cannot create pgvector extension due to insufficient privileges.")
                    log.error("")
                    log.error("The pgvector extension is required but not installed.")
                    log.error("Please install it using one of these methods:")
                    log.error("")
                    log.error("1. As PostgreSQL superuser:")
                    log.error(f"   sudo -u postgres psql -d {db_config['database']} -c 'CREATE EXTENSION vector;'")
                    log.error("")
                    log.error("2. Ask your database administrator to run:")
                    log.error("   CREATE EXTENSION vector;")
                    log.error("")
                    log.error("After installing pgvector, run 'papersorter init' again.")
                    return
                # Continue even if we lacked privilege but extension exists

            if not quiet:
                log.info(f"Creating schema '{schema}'...")
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            cursor.execute(f"SET search_path TO {schema}, public")

            if drop_existing:
                if not quiet:
                    log.warning("Dropping existing tables...")
                for table in db_schema["DROP_ORDER"]:
                    cursor.execute(f"DROP TABLE IF EXISTS {schema}.{table} CASCADE")

                for type_name in db_schema["CUSTOM_TYPES"]:
                    cursor.execute(f"DROP TYPE IF EXISTS {schema}.{type_name} CASCADE")

            if not quiet:
                log.info("Creating custom types...")
            for type_name, type_def in db_schema["CUSTOM_TYPES"].items():
                if type_def["type"] == "ENUM":
                    values_str = ", ".join([f"'{v}'" for v in type_def["values"]])
                    cursor.execute(
                        f"""
                            DO $$ BEGIN
                                CREATE TYPE {schema}.{type_name} AS ENUM ({values_str});
                            EXCEPTION
                                WHEN duplicate_object THEN null;
                            END $$;
                        """
                    )

            if not quiet:
                log.info("Creating tables...")

            for table_def in db_schema["TABLES"]:
                table_name = table_def["name"]

                columns = []
                for col_name, col_type in table_def["columns"]:
                    col_type_formatted = col_type.format(schema=schema)
                    columns.append(f"{col_name} {col_type_formatted}")

                if "primary_key" in table_def:
                    pk_cols = ", ".join(table_def["primary_key"])
                    columns.append(f"PRIMARY KEY ({pk_cols})")

                columns_str = ",\n    ".join(columns)

                create_sql = f"""
                    CREATE TABLE IF NOT EXISTS {schema}.{table_name} (
                        {columns_str}
                    )
                """

                try:
                    cursor.execute(create_sql)
                    if not quiet:
                        log.debug(f"Created table: {table_name}")
                except psycopg2.errors.UndefinedObject as e:
                    if "type \"public.vector\" does not exist" in str(e) or "type \"vector\" does not exist" in str(e):
                        log.error(f"Failed to create table {table_name}: pgvector extension is not installed.")
                        log.error("")
                        log.error("The pgvector extension must be installed first.")
                        log.error("Please install it using one of these methods:")
                        log.error("")
                        log.error("1. As PostgreSQL superuser:")
                        log.error(f"   sudo -u postgres psql -d {db_config['database']} -c 'CREATE EXTENSION vector;'")
                        log.error("")
                        log.error("2. Ask your database administrator to run:")
                        log.error("   CREATE EXTENSION vector;")
                        log.error("")
                        log.error("After installing pgvector, run 'papersorter init' again.")
                        return
                    else:
                        raise

            if not quiet:
                log.info("Creating indexes...")

            for index_def in db_schema["INDEXES"]:
                index_name = index_def["name"]
                table_name = index_def["table"]
                columns = ", ".join(index_def["columns"])

                if index_def.get("type") == "hnsw":
                    index_sql = f"""
                        CREATE INDEX IF NOT EXISTS {index_name}
                        ON {schema}.{table_name}
                        USING hnsw ({columns})
                    """
                else:
                    index_sql = f"""
                        CREATE INDEX IF NOT EXISTS {index_name}
                        ON {schema}.{table_name} ({columns})
                    """

                cursor.execute(index_sql)

                if not quiet:
                    log.debug(f"Created index: {index_name}")

            if not quiet:
                log.info("Database initialization complete!")
                log.info(f"Tables created successfully in schema: {schema}")

    except Exception as e:
        log.error(f"Error initializing database: {e}")
        raise
    finally:
        db_manager.close()
