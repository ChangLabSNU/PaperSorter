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
from datetime import datetime
import requests
import pickle
import click
import time
import re
import os

def normalize_item_for_display(item, max_content_length):
    # XXX: Fix the source field for the aggregated items.
    if item['origin'] == 'QBio Feed Aggregation' and '  ' in item['content']:
        source, content = item['content'].split('  ', 1)
        item['origin'] = source
        item['content'] = normalize_text(content)

    # Truncate the content if it's too long.
    if len(item['content']) > max_content_length:
        item['content'] = item['content'][:max_content_length] + '…'

def send_slack_notification(config, item):
    url = config['WEBHOOK_PAPERSORTER_NEWSTEST']
    header = {'Content-type': 'application/json'}

    # Add title block
    title = normalize_text(item['title'])
    blocks = [
        {'type': 'divider'},
        {'type': 'header',
         'text': {'type': 'plain_text', 'text': title}},
    ]

    # Add predicted score block
    blocks.append(
        {'type': 'context',
         'elements': [
            {'type': 'mrkdwn',
              'text': f':heart_decoration: QBio Score: *{int(item["score"]*100)}*'}
         ]
        }
    )

    # Add source block
    origin = normalize_text(item['origin'])
    if origin:
        if item['link']:
            origin = f'<{item["link"]}|{origin}>'

        blocks.append(
            {'type': 'context',
             'elements': [{
                'type': 'mrkdwn',
                'text': f':inbox_tray: Source: *{origin}*'}
             ]
            }
        )

    # Add authors block
    authors = normalize_text(item['author'])
    if authors:
        blocks.append(
            {'type': 'context',
             'elements': [{
                'type': 'mrkdwn',
                'text': f':black_nib: *{authors}*'}
             ]
            }
        )

    if item['content'].strip():
        blocks.append(
            {
                'type': 'section',
                'text': {'type': 'mrkdwn', 'text': item['content'].strip()},
                'accessory': {
                    'type': 'button',
                    'text': {
                        'type': 'plain_text',
                        'text': 'Read',
                        'emoji': True
                    },
                    'value': 'read_0',
                    'url': item['link'],
                    'action_id': 'button-action'
                }
            },
        )

    data = {'blocks': blocks}

    return requests.post(url, headers=header, json=data)

def normalize_text(text):
    return re.sub(r'\s+', ' ', text).strip()

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

@click.option('--days', default=7, help='Number of days to look back.')
@click.option('--score-threshold', default=0.7, help='Threshold for the score.')
@click.option('--max-content-length', default=400, help='Maximum length of the content.')
def main(days, score_threshold, max_content_length):
    from dotenv import dotenv_values
    config = dotenv_values()

    since = time.time() - days * 86400

    feeddb = FeedDatabase('feeds.db')
    newitems = feeddb.get_new_interesting_items(score_threshold, since,
                                                remove_duplicated=since)
    for item_id, info in newitems.iterrows():
        normalize_item_for_display(info, max_content_length)
        send_slack_notification(config, info)
        feeddb.update_broadcasted(item_id, int(time.time()))
        feeddb.commit()