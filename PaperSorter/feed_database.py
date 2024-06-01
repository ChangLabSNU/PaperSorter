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

import sqlite3
import pandas as pd
import re

class FeedDatabase:

    llm_input_format = (
        'Title: {item[2]}.\n'
        'Authors: {item[4]}.\n'
        'Source: {item[5]}.\n'
        'Abstract: {item[3]}.')

    dbfields = ['id', 'starred', 'title', 'content', 'author', 'origin',
                'published', 'link', 'mediaUrl', 'label', 'score', 'broadcasted']

    def __init__(self, filename):
        self.db = sqlite3.connect(filename)
        self.cursor = self.db.cursor()
        self.create_table_if_not_exists()
        self.update_idcache()

    def __del__(self):
        self.db.close()

    def __contains__(self, item):
        return item.item_id in self.idcache

    def __len__(self):
        self.cursor.execute('SELECT COUNT(*) FROM feeds')
        return self.cursor.fetchone()[0]

    def keys(self):
        return self.idcache

    def create_table_if_not_exists(self):
        self.cursor.execute('CREATE TABLE IF NOT EXISTS feeds (id TEXT UNIQUE, starred INTEGER, '
                            'title TEXT, content TEXT, author TEXT, origin TEXT, '
                            'published INTEGER, link TEXT, mediaUrl TEXT, '
                            'label INTEGER, score REAL, broadcasted INTEGER)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_id ON feeds(id)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_published ON feeds(published)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_starred ON feeds(starred)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_label ON feeds(label)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_score ON feeds(score)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_broadcasted ON feeds(broadcasted)')

    def update_idcache(self):
        self.cursor.execute('SELECT id FROM feeds')
        self.idcache = set([row[0] for row in self.cursor.fetchall()])

    def commit(self):
        self.db.commit()

    def insert_item(self, item, starred=0):
        content = remove_html_tags(item.content)
        self.cursor.execute('INSERT INTO feeds VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                            (item.item_id, starred, item.title, content, item.author,
                             item.origin, item.published, item.href, item.mediaUrl,
                             None, None, None))
        self.idcache.add(item.item_id)

    def get_formatted_item(self, item_id):
        self.cursor.execute('SELECT * FROM feeds WHERE id = ?', (item_id,))
        item = self.cursor.fetchone()
        return self.llm_input_format.format(item=item)

    def build_dataframe_from_results(self):
        return pd.DataFrame(self.cursor.fetchall(), columns=self.dbfields).set_index('id')

    def get_metadata(self):
        self.cursor.execute('SELECT * FROM feeds')
        return self.build_dataframe_from_results()

    def update_label(self, item_id, label):
        self.cursor.execute('UPDATE feeds SET label = ? WHERE id = ?', (label, item_id))

    def update_score(self, item_id, score):
        self.cursor.execute('UPDATE feeds SET score = ? WHERE id = ?', (float(score), item_id))

    def update_broadcasted(self, item_id, timemark):
        self.cursor.execute('UPDATE feeds SET broadcasted = ? WHERE id = ?', (timemark, item_id))

    def get_unscored_items(self):
        self.cursor.execute('SELECT id FROM feeds WHERE score IS NULL')
        return [row[0] for row in self.cursor.fetchall()]

    def get_new_interesting_items(self, threshold, since, remove_duplicated=None):
        self.cursor.execute('SELECT * FROM feeds WHERE score > ? AND '
                            'broadcasted IS NULL AND published >= ?',
                            (threshold, since))

        matches = self.build_dataframe_from_results()
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
        self.cursor.execute('SELECT * FROM feeds WHERE starred > 0 AND '
                            'published >= ? AND broadcasted IS NULL', (since,))
        matches = self.build_dataframe_from_results()
        return self.filter_duplicates(matches, remove_duplicated)

    def check_broadcasted(self, item_id, since):
        self.cursor.execute('SELECT COUNT(b.broadcasted) FROM feeds a, feeds b '
                            'WHERE a.id = ? AND b.published >= ? AND '
                            'a.id != b.id AND a.title = b.title AND '
                            'b.broadcasted > 0', (item_id, since))
        dup_broadcasted = self.cursor.fetchone()[0]
        if dup_broadcasted > 0:
            # Mark duplicates as blacklisted
            self.cursor.execute('UPDATE feeds SET broadcasted = 0 WHERE id = ?', (item_id,))
            self.commit()

        return dup_broadcasted > 0

    def get_star_status(self, since, till):
        self.cursor.execute('SELECT id, starred FROM feeds WHERE published >= ? '
                            'AND published <= ?', (since, till))
        return {item_id: bool(starred) for item_id, starred in self.cursor.fetchall()}

    def update_star_status(self, item_id, starred):
        self.cursor.execute('UPDATE feeds SET starred = ? WHERE id = ?',
                            (int(starred), item_id))

def remove_html_tags(text, pattern=re.compile('<.*?>')):
    return pattern.sub(' ', text)
