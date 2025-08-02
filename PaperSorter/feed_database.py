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
import pandas as pd
import re
import yaml

class FeedDatabase:

    dbfields = ['id', 'starred', 'title', 'content', 'author', 'origin',
                'published', 'link', 'mediaUrl', 'label', 'score', 'broadcasted',
                'tldr']

    def __init__(self, config_path='qbio/config.yml'):
        # Load database configuration
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        db_config = config['db']

        # Connect to PostgreSQL
        self.db = psycopg2.connect(
            host=db_config['host'],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )
        self.db.autocommit = False
        self.cursor = self.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        self.update_idcache()

    def __del__(self):
        if hasattr(self, 'db'):
            self.db.close()

    def __contains__(self, item):
        return item.item_id in self.idcache

    def __len__(self):
        self.cursor.execute('SELECT COUNT(*) FROM feeds')
        return self.cursor.fetchone()['count']

    def __getitem__(self, item_id):
        if isinstance(item_id, str):
            self.cursor.execute('SELECT * FROM feeds WHERE external_id = %s', (item_id,))
        else:
            self.cursor.execute('SELECT * FROM feeds WHERE id = %s', (item_id,))
        result = self.cursor.fetchone()
        if result:
            # Map to old field names for compatibility
            return {
                'id': result['external_id'],
                'starred': result.get('starred', 0),
                'title': result['title'],
                'content': result['content'],
                'author': result['author'],
                'origin': result['origin'],
                'published': int(result['published'].timestamp()) if result['published'] else None,
                'link': result['link'],
                'mediaUrl': result['mediaurl'],
                'label': result.get('label'),
                'score': result.get('score'),
                'broadcasted': result.get('broadcasted'),
                'tldr': result['tldr']
            }
        return None

    def keys(self):
        return self.idcache

    def update_idcache(self):
        self.cursor.execute('SELECT external_id FROM feeds WHERE external_id IS NOT NULL')
        self.idcache = set([row['external_id'] for row in self.cursor.fetchall()])

    def commit(self):
        self.db.commit()

    def insert_item(self, item, starred=0, broadcasted=None, tldr=None):
        content = remove_html_tags(item.content)

        # Get user_id from preferences table or use default
        user_id = 1  # Default user

        # Insert into feeds table
        self.cursor.execute('''
            INSERT INTO feeds (external_id, title, content, author, origin, published, link, mediaurl, tldr)
            VALUES (%s, %s, %s, %s, %s, to_timestamp(%s), %s, %s, %s)
            ON CONFLICT (external_id) DO NOTHING
            RETURNING id
        ''', (item.item_id, item.title, content, item.author,
              item.origin, item.published, item.href, item.mediaUrl, tldr))

        result = self.cursor.fetchone()
        if result:
            feed_id = result['id']

            # Insert starred status as preference if starred
            if starred:
                # Check if preference already exists before inserting
                self.cursor.execute('''
                    SELECT id FROM preferences
                    WHERE feed_id = %s AND user_id = %s AND source = 'feed-star'
                ''', (feed_id, user_id))

                if not self.cursor.fetchone():
                    self.cursor.execute('''
                        INSERT INTO preferences (feed_id, user_id, time, score, source)
                        VALUES (%s, %s, CURRENT_TIMESTAMP, 1.0, 'feed-star')
                    ''', (feed_id, user_id))

            # Insert broadcast log if broadcasted
            if broadcasted is not None:
                channel_id = 1  # Default channel
                self.cursor.execute('''
                    INSERT INTO broadcasts (feed_id, channel_id, broadcasted_time)
                    VALUES (%s, %s, to_timestamp(%s))
                    ON CONFLICT DO NOTHING
                ''', (feed_id, channel_id, broadcasted))

            self.idcache.add(item.item_id)
            return feed_id

    def get_formatted_item(self, item_id):
        if isinstance(item_id, str):
            self.cursor.execute('SELECT * FROM feeds WHERE external_id = %s', (item_id,))
        else:
            self.cursor.execute('SELECT * FROM feeds WHERE id = %s', (item_id,))
        item = self.cursor.fetchone()
        if item:
            parts = []
            
            if item['title']:
                parts.append(f"Title: {item['title']}")
            
            if item['author']:
                parts.append(f"Authors: {item['author']}")
            
            if item['origin']:
                parts.append(f"Journal/Source: {item['origin']}")
            
            if item['content']:
                parts.append(f"Abstract: {item['content']}")
            
            return "\n\n".join(parts)
        return None

    def build_dataframe_from_results(self, results):
        if not results:
            return pd.DataFrame(columns=self.dbfields).set_index('id')

        # Convert results to DataFrame with old field names for compatibility
        data = []
        for row in results:
            data.append({
                'id': row['external_id'],
                'starred': row.get('starred', 0),
                'title': row['title'],
                'content': row['content'],
                'author': row['author'],
                'origin': row['origin'],
                'published': int(row['published'].timestamp()) if row['published'] else None,
                'link': row['link'],
                'mediaUrl': row['mediaurl'],
                'label': row.get('label'),
                'score': row.get('score'),
                'broadcasted': row.get('broadcasted'),
                'tldr': row['tldr']
            })

        return pd.DataFrame(data).set_index('id')

    def get_metadata(self):
        self.cursor.execute('''
            SELECT f.*,
                   CASE WHEN p.score > 0 THEN 1 ELSE 0 END as starred,
                   p.score as label,
                   pp.score as score,
                   CASE WHEN bl.broadcasted_time IS NOT NULL THEN EXTRACT(EPOCH FROM bl.broadcasted_time)::integer ELSE NULL END as broadcasted
            FROM feeds f
            LEFT JOIN preferences p ON f.id = p.feed_id AND p.source = 'feed-star'
            LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id
            LEFT JOIN broadcasts bl ON f.id = bl.feed_id
            WHERE f.external_id IS NOT NULL
        ''')
        return self.build_dataframe_from_results(self.cursor.fetchall())

    def update_label(self, item_id, label):
        user_id = 1  # Default user

        # Get feed_id based on item_id type
        if isinstance(item_id, str):
            self.cursor.execute('SELECT id FROM feeds WHERE external_id = %s', (item_id,))
        else:
            self.cursor.execute('SELECT id FROM feeds WHERE id = %s', (item_id,))
        result = self.cursor.fetchone()
        if result:
            feed_id = result['id']
            # First check if a preference already exists
            self.cursor.execute('''
                SELECT id FROM preferences
                WHERE feed_id = %s AND user_id = %s AND source = 'interactive'
            ''', (feed_id, user_id))

            existing = self.cursor.fetchone()

            if existing:
                # Update existing preference
                self.cursor.execute('''
                    UPDATE preferences
                    SET score = %s, time = CURRENT_TIMESTAMP
                    WHERE feed_id = %s AND user_id = %s AND source = 'interactive'
                ''', (float(label), feed_id, user_id))
            else:
                # Insert new preference
                self.cursor.execute('''
                    INSERT INTO preferences (feed_id, user_id, time, score, source)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, %s, 'interactive')
                ''', (feed_id, user_id, float(label)))

    def update_score(self, item_id, score, model_id=1):
        # Get feed_id based on item_id type
        if isinstance(item_id, str):
            self.cursor.execute('SELECT id FROM feeds WHERE external_id = %s', (item_id,))
        else:
            self.cursor.execute('SELECT id FROM feeds WHERE id = %s', (item_id,))
        result = self.cursor.fetchone()
        if result:
            feed_id = result['id']
            self.cursor.execute('''
                INSERT INTO predicted_preferences (feed_id, model_id, score)
                VALUES (%s, %s, %s)
                ON CONFLICT (feed_id, model_id) DO UPDATE SET score = %s
            ''', (feed_id, model_id, float(score), float(score)))

    def update_broadcasted(self, item_id, timemark):
        channel_id = 1  # Default channel

        # Get feed_id based on item_id type
        if isinstance(item_id, str):
            self.cursor.execute('SELECT id FROM feeds WHERE external_id = %s', (item_id,))
        else:
            self.cursor.execute('SELECT id FROM feeds WHERE id = %s', (item_id,))
        result = self.cursor.fetchone()
        if result:
            feed_id = result['id']
            self.cursor.execute('''
                INSERT INTO broadcasts (feed_id, channel_id, broadcasted_time)
                VALUES (%s, %s, to_timestamp(%s))
                ON CONFLICT DO NOTHING
            ''', (feed_id, channel_id, timemark))

    def update_tldr(self, item_id, tldr):
        if isinstance(item_id, str):
            self.cursor.execute('UPDATE feeds SET tldr = %s WHERE external_id = %s', (tldr, item_id))
        else:
            self.cursor.execute('UPDATE feeds SET tldr = %s WHERE id = %s', (tldr, item_id))

    def update_author(self, item_id, author):
        if isinstance(item_id, str):
            self.cursor.execute('UPDATE feeds SET author = %s WHERE external_id = %s', (author, item_id))
        else:
            self.cursor.execute('UPDATE feeds SET author = %s WHERE id = %s', (author, item_id))

    def update_origin(self, item_id, origin):
        if isinstance(item_id, str):
            self.cursor.execute('UPDATE feeds SET origin = %s WHERE external_id = %s', (origin, item_id))
        else:
            self.cursor.execute('UPDATE feeds SET origin = %s WHERE id = %s', (origin, item_id))

    def get_unscored_items(self):
        model_id = 1  # Default model
        self.cursor.execute('''
            SELECT f.external_id
            FROM feeds f
            LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = %s
            WHERE pp.score IS NULL AND f.external_id IS NOT NULL
        ''', (model_id,))
        return [row['external_id'] for row in self.cursor.fetchall()]

    def get_new_interesting_items(self, threshold, since, remove_duplicated=None):
        model_id = 1  # Default model
        self.cursor.execute('''
            SELECT f.*, pp.score as score,
                   CASE WHEN bl.broadcasted_time IS NOT NULL THEN EXTRACT(EPOCH FROM bl.broadcasted_time)::integer ELSE NULL END as broadcasted
            FROM feeds f
            JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = %s
            LEFT JOIN broadcasts bl ON f.id = bl.feed_id
            WHERE pp.score > %s AND bl.broadcasted_time IS NULL AND f.published >= to_timestamp(%s)
                  AND f.external_id IS NOT NULL
        ''', (model_id, threshold, since))

        matches = self.build_dataframe_from_results(self.cursor.fetchall())
        return self.filter_duplicates(matches, remove_duplicated)

    def filter_duplicates(self, matches, remove_duplicated):
        if len(matches) == 0:
            return matches

        blacklisted = set()
        if remove_duplicated is not None:
            for item_id in matches.index:
                if self.check_broadcasted(item_id, remove_duplicated):
                    blacklisted.add(item_id)

        if len(blacklisted) > 0:
            matches = matches.drop(blacklisted)

        return matches

    def get_newly_starred_items(self, since, remove_duplicated=None):
        self.cursor.execute('''
            SELECT f.*,
                   1 as starred,
                   CASE WHEN bl.broadcasted_time IS NOT NULL THEN EXTRACT(EPOCH FROM bl.broadcasted_time)::integer ELSE NULL END as broadcasted
            FROM feeds f
            JOIN preferences p ON f.id = p.feed_id AND p.source = 'feed-star' AND p.score > 0
            LEFT JOIN broadcasts bl ON f.id = bl.feed_id
            WHERE f.published >= to_timestamp(%s) AND bl.broadcasted_time IS NULL
                  AND f.external_id IS NOT NULL
        ''', (since,))
        matches = self.build_dataframe_from_results(self.cursor.fetchall())
        return self.filter_duplicates(matches, remove_duplicated)

    def check_broadcasted(self, item_id, since):
        if isinstance(item_id, str):
            where_clause = "a.external_id = %s"
        else:
            where_clause = "a.id = %s"

        self.cursor.execute(f'''
            SELECT COUNT(*) as count
            FROM feeds a
            JOIN feeds b ON a.title = b.title AND a.id != b.id
            JOIN broadcasts bl ON b.id = bl.feed_id
            WHERE {where_clause} AND b.published >= to_timestamp(%s)
                  AND bl.broadcasted_time IS NOT NULL
        ''', (item_id, since))
        dup_broadcasted = self.cursor.fetchone()['count']

        if dup_broadcasted > 0:
            # Mark duplicates as blacklisted
            channel_id = 1  # Default channel
            if isinstance(item_id, str):
                self.cursor.execute('SELECT id FROM feeds WHERE external_id = %s', (item_id,))
            else:
                self.cursor.execute('SELECT id FROM feeds WHERE id = %s', (item_id,))
            result = self.cursor.fetchone()
            if result:
                feed_id = result['id']
                self.cursor.execute('''
                    INSERT INTO broadcasts (feed_id, channel_id, broadcasted_time)
                    VALUES (%s, %s, to_timestamp(0))
                    ON CONFLICT DO NOTHING
                ''', (feed_id, channel_id))
                self.commit()

        return dup_broadcasted > 0

    def get_star_status(self, since, till):
        self.cursor.execute('''
            SELECT f.external_id, CASE WHEN p.score > 0 THEN true ELSE false END as starred
            FROM feeds f
            LEFT JOIN preferences p ON f.id = p.feed_id AND p.source = 'feed-star'
            WHERE f.published >= to_timestamp(%s) AND f.published <= to_timestamp(%s)
                  AND f.external_id IS NOT NULL
        ''', (since, till))
        return {row['external_id']: row['starred'] for row in self.cursor.fetchall()}

    def update_star_status(self, item_id, starred):
        user_id = 1  # Default user

        # Get feed_id based on item_id type
        if isinstance(item_id, str):
            self.cursor.execute('SELECT id FROM feeds WHERE external_id = %s', (item_id,))
        else:
            self.cursor.execute('SELECT id FROM feeds WHERE id = %s', (item_id,))
        result = self.cursor.fetchone()
        if result:
            feed_id = result['id']
            score = 1.0 if starred else 0.0
            # First check if a preference already exists
            self.cursor.execute('''
                SELECT id FROM preferences
                WHERE feed_id = %s AND user_id = %s AND source = 'feed-star'
            ''', (feed_id, user_id))

            existing = self.cursor.fetchone()

            if existing:
                # Update existing preference
                self.cursor.execute('''
                    UPDATE preferences
                    SET score = %s, time = CURRENT_TIMESTAMP
                    WHERE feed_id = %s AND user_id = %s AND source = 'feed-star'
                ''', (score, feed_id, user_id))
            else:
                # Insert new preference
                self.cursor.execute('''
                    INSERT INTO preferences (feed_id, user_id, time, score, source)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, %s, 'feed-star')
                ''', (feed_id, user_id, score))

    def add_to_broadcast_queue(self, feed_id, channel_id=1):
        """Add an item to the broadcast queue (using merged broadcasts table)."""
        self.cursor.execute('''
            INSERT INTO broadcasts (feed_id, channel_id, broadcasted_time)
            VALUES (%s, %s, NULL)
            ON CONFLICT (feed_id, channel_id) DO NOTHING
        ''', (feed_id, channel_id))

    def get_broadcast_queue_items(self, channel_id=1, limit=None, model_id=None):
        """Get unprocessed items from the broadcast queue (using merged broadcasts table)."""
        # If no model_id provided, get the most recent active model
        if model_id is None:
            self.cursor.execute("""
                SELECT id FROM models
                WHERE is_active = TRUE
                ORDER BY id DESC
                LIMIT 1
            """)
            result = self.cursor.fetchone()
            model_id = result['id'] if result else 1

        query = '''
            SELECT f.*, pp.score, bl.feed_id as queue_feed_id
            FROM broadcasts bl
            JOIN feeds f ON bl.feed_id = f.id
            LEFT JOIN predicted_preferences pp ON f.id = pp.feed_id AND pp.model_id = %s
            WHERE bl.channel_id = %s AND bl.broadcasted_time IS NULL
            ORDER BY f.published DESC
        '''
        if limit:
            query += f' LIMIT {limit}'

        self.cursor.execute(query, (model_id, channel_id))
        items = []
        for row in self.cursor.fetchall():
            item = dict(row)
            items.append(item)

        # Convert to DataFrame to match the existing broadcast.py interface
        import pandas as pd
        if items:
            df = pd.DataFrame(items)
            df.set_index('queue_feed_id', inplace=True)
            return df
        else:
            return pd.DataFrame()

    def mark_broadcast_queue_processed(self, feed_id, channel_id=1):
        """Mark an item in the broadcast queue as processed (using merged broadcasts table)."""
        self.cursor.execute('''
            UPDATE broadcasts
            SET broadcasted_time = CURRENT_TIMESTAMP
            WHERE feed_id = %s AND channel_id = %s
        ''', (feed_id, channel_id))

    def clear_old_broadcast_queue(self, days=30):
        """Clear old processed items from the broadcast queue (using merged broadcasts table)."""
        self.cursor.execute('''
            DELETE FROM broadcasts
            WHERE broadcasted_time < CURRENT_TIMESTAMP - INTERVAL '%s days'
        ''', (days,))

def remove_html_tags(text, pattern=re.compile('<.*?>')):
    return pattern.sub(' ', text)