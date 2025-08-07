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

import psycopg2
import psycopg2.extras
import yaml


class BroadcastChannels:
    """Manages broadcast channel configurations."""

    def __init__(self, config_path="./config.yml"):
        # Load database configuration
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        db_config = config["db"]

        # Connect to PostgreSQL
        self.db = psycopg2.connect(
            host=db_config["host"],
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
        )
        self.db.autocommit = False
        self.cursor = self.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def __del__(self):
        if hasattr(self, "db"):
            self.db.close()

    def get_channel(self, channel_id):
        """Get a specific channel's configuration."""
        self.cursor.execute(
            """
            SELECT id, name, endpoint_url, score_threshold, model_id
            FROM channels
            WHERE id = %s
        """,
            (channel_id,),
        )
        return self.cursor.fetchone()

    def get_all_channels(self):
        """Get all channels with their settings."""
        self.cursor.execute("""
            SELECT id, name, endpoint_url, score_threshold, model_id
            FROM channels
            ORDER BY id
        """)
        return self.cursor.fetchall()

    def update_channel(self, channel_id, **kwargs):
        """Update channel settings."""
        allowed_fields = ["name", "endpoint_url", "score_threshold", "model_id"]
        updates = []
        values = []

        for field in allowed_fields:
            if field in kwargs:
                updates.append(f"{field} = %s")
                values.append(kwargs[field])

        if updates:
            values.append(channel_id)
            self.cursor.execute(
                f"""
                UPDATE channels
                SET {", ".join(updates)}
                WHERE id = %s
            """,
                values,
            )
            self.db.commit()

    def create_channel(self, name, endpoint_url, score_threshold=0.7, model_id=1):
        """Create a new broadcast channel."""
        self.cursor.execute(
            """
            INSERT INTO channels (name, endpoint_url, score_threshold, model_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """,
            (name, endpoint_url, score_threshold, model_id),
        )
        result = self.cursor.fetchone()
        self.db.commit()
        return result["id"]

    def delete_channel(self, channel_id):
        """Delete a channel."""
        self.cursor.execute("DELETE FROM channels WHERE id = %s", (channel_id,))
        self.db.commit()

    def commit(self):
        """Commit any pending transactions."""
        self.db.commit()
