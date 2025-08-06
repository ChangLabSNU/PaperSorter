#!/usr/bin/env python3
#
# Copyright (c) 2024 Hyeshik Chang
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
import psycopg2
import yaml
from ..log import log
from ..data import schema as db_schema


@click.option("--config", "-c", default="qbio/config.yml", help="Config file")
@click.option("--schema", default="papersorter", help="Database schema name")
@click.option("--drop-existing", is_flag=True, help="Drop existing tables first")
@click.option("-q", "--quiet", is_flag=True, help="Suppress output messages")
def main(config, schema, drop_existing, quiet):
    """Initialize database tables and schema for PaperSorter."""
    
    if not quiet:
        log.info("Initializing PaperSorter database...")
    
    # Load database configuration
    with open(config, "r") as f:
        cfg = yaml.safe_load(f)
    
    db_config = cfg["db"]
    
    # Connect to PostgreSQL
    conn = psycopg2.connect(
        host=db_config["host"],
        database=db_config["database"],
        user=db_config["user"],
        password=db_config["password"],
    )
    conn.autocommit = True
    cursor = conn.cursor()
    
    try:
        # Create pgvector extension if not exists
        if not quiet:
            log.info("Checking pgvector extension...")
        try:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            if not quiet:
                log.info("pgvector extension is ready.")
        except psycopg2.errors.InsufficientPrivilege:
            # Check if extension already exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'vector'
                )
            """)
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
                log.error(f"   CREATE EXTENSION vector;")
                log.error("")
                log.error("After installing pgvector, run 'papersorter init' again.")
                return
        
        # Create schema if not exists
        if not quiet:
            log.info(f"Creating schema '{schema}'...")
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        cursor.execute(f"SET search_path TO {schema}, public")
        
        # Drop existing tables if requested
        if drop_existing:
            if not quiet:
                log.warning("Dropping existing tables...")
            for table in db_schema.DROP_ORDER:
                cursor.execute(f"DROP TABLE IF EXISTS {schema}.{table} CASCADE")
            
            # Drop custom types
            for type_name in db_schema.CUSTOM_TYPES:
                cursor.execute(f"DROP TYPE IF EXISTS {schema}.{type_name} CASCADE")
        
        # Create custom types
        if not quiet:
            log.info("Creating custom types...")
        for type_name, type_def in db_schema.CUSTOM_TYPES.items():
            if type_def["type"] == "ENUM":
                values_str = ", ".join([f"'{v}'" for v in type_def["values"]])
                cursor.execute(f"""
                    DO $$ BEGIN
                        CREATE TYPE {schema}.{type_name} AS ENUM ({values_str});
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$;
                """)
        
        # Create tables
        if not quiet:
            log.info("Creating tables...")
        
        for table_def in db_schema.TABLES:
            table_name = table_def["name"]
            
            # Build column definitions
            columns = []
            for col_name, col_type in table_def["columns"]:
                # Replace schema placeholder in column type
                col_type_formatted = col_type.format(schema=schema)
                columns.append(f"{col_name} {col_type_formatted}")
            
            # Add composite primary key if specified
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
                    log.error(f"   CREATE EXTENSION vector;")
                    log.error("")
                    log.error("After installing pgvector, run 'papersorter init' again.")
                    return
                else:
                    raise
        
        # Create indexes
        if not quiet:
            log.info("Creating indexes...")
        
        for index_def in db_schema.INDEXES:
            index_name = index_def["name"]
            table_name = index_def["table"]
            columns = ", ".join(index_def["columns"])
            
            if index_def.get("type") == "hnsw":
                # Special handling for HNSW vector index
                index_sql = f"""
                    CREATE INDEX IF NOT EXISTS {index_name}
                    ON {schema}.{table_name}
                    USING hnsw ({columns})
                """
            else:
                # Regular btree index
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
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()