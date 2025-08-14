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

"""Create an admin user for PaperSorter."""

import click
import psycopg2
import yaml
import sys
from pathlib import Path


@click.command()
@click.option("--config", "-c", default="./config.yml", help="Config file path")
@click.option("--email", "-e", required=True, help="Email address for the admin user")
@click.option("--schema", default="papersorter", help="Database schema name")
def main(config, email, schema):
    """Create an admin user for PaperSorter."""

    # Load configuration
    config_path = Path(config)
    if not config_path.exists():
        click.echo(f"Error: Config file not found: {config_path}", err=True)
        sys.exit(1)

    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f)

    db_config = config_data["db"]

    # Connect to database
    try:
        conn = psycopg2.connect(
            host=db_config["host"],
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
        )
        cursor = conn.cursor()
    except Exception as e:
        click.echo(f"Error connecting to database: {e}", err=True)
        sys.exit(1)

    try:
        # Check if user already exists
        cursor.execute(
            f"SELECT id, is_admin FROM {schema}.users WHERE username = %s",
            (email,)
        )
        existing_user = cursor.fetchone()

        if existing_user:
            user_id, is_admin = existing_user
            if is_admin:
                click.echo(f"User {email} already exists and is already an admin (ID: {user_id})")
            else:
                # Update existing user to be admin
                cursor.execute(
                    f"UPDATE {schema}.users SET is_admin = true WHERE id = %s",
                    (user_id,)
                )
                conn.commit()
                click.echo(f"Updated user {email} to admin status (ID: {user_id})")
        else:
            # Create new admin user
            cursor.execute(
                f"""
                INSERT INTO {schema}.users (username, password, created, is_admin, timezone)
                VALUES (%s, %s, CURRENT_TIMESTAMP, true, 'Asia/Seoul')
                RETURNING id
                """,
                (email, "oauth")
            )
            user_id = cursor.fetchone()[0]
            conn.commit()
            click.echo(f"Created admin user {email} (ID: {user_id})")

        click.echo("\nNext steps:")
        click.echo("1. Start the web interface: papersorter serve")
        click.echo("2. Navigate to http://localhost:5001")
        click.echo("3. Log in with Google OAuth using the email address you just configured")
        click.echo("4. You should now have access to the Settings tab")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        conn.rollback()
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
