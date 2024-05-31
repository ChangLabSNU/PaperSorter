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

from ..feed_database import FeedDatabase
from ..providers.theoldreader import Connection, ItemsSearch
import click
from datetime import datetime
import pickle
import time
import os

def get_starred_or_liked(conn, num_items):
    searcher = ItemsSearch(conn)

    starred = next(searcher.get_starred_only(num_items))
    liked = next(searcher.get_liked_only(num_items))

    return starred + liked

def broadcast_item(item, slack_endpoint, dry_run):
    print("Broadcasting:", item.title)
    message = f'{item.title}\n{item.href}'
    if not dry_run:
        send_slack_message(slack_endpoint, message)

def send_slack_message(endpoint, message):
    import requests
    requests.post(endpoint, json={'text': message})

@click.option('--days', default=7, help='Number of days to look back.')
@click.option('--score-threshold', default=0.7, help='Threshold for the score.')
@click.option('-d', '--dry-run', is_flag=True, help='Do not actually send messages.')
def main(days, score_threshold, dry_run):
    from dotenv import dotenv_values
    config = dotenv_values()

    since = time.time() - days * 86400

    feeddb = FeedDatabase('feeds.db')
    newitems = feeddb.get_new_interesting_items(score_threshold, since)
    print(newitems[['title', 'score']])
    return




    history_filename = history
    history = (
        pickle.load(open(history_filename, 'rb'))
        if os.path.exists(history) else [])

    #items = get_starred_or_liked(conn, num_items)
    #pickle.dump(items, open('items.pkl', 'wb'))
    recent_items = pickle.load(open('items.pkl', 'rb'))
    new_items = set(recent_items) - set(history)
    print("Recent items:", len(recent_items))
    print("New items:", len(new_items))

    for item in new_items:
        broadcast_item(item, dry_run)
        history.append((item, time.time()))

    # Remove old items from history
    cutoff = time.time() - ttl * 86400
    history = [(i, t) for i, t in history if t < cutoff]
    pickle.dump(history, open(history_filename, 'wb'))
