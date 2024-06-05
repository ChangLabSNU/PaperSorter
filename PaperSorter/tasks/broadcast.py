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
from ..log import log, initialize_logging
import requests
import pandas as pd
import click
import time
import re
import os

SLACK_ENDPOINT_KEY = 'PAPERSORTER_WEBHOOK_URL'
SLACK_HEADER_MAX_LENGTH = 150

class SlackNotificationError(Exception):
    pass

def normalize_item_for_display(item, max_content_length):
    # XXX: Fix the source field for the aggregated items.
    if item['origin'] == 'QBio Feed Aggregation' and '  ' in item['content']:
        source, content = item['content'].split('  ', 1)
        item['origin'] = source
        item['content'] = normalize_text(content)

    # Truncate the content if it's too long.
    if len(item['content']) > max_content_length:
        item['content'] = limit_text_length(item['content'], max_content_length)

def limit_text_length(text, limit):
    if len(text) > limit:
        return text[:limit-3] + '…'
    return text

def send_slack_notification(endpoint_url, item, msgopts):
    header = {'Content-type': 'application/json'}

    # Add title block
    title = normalize_text(item['title'])
    blocks = [
        {'type': 'header',
         'text': {'type': 'plain_text',
                  'text': limit_text_length(title, SLACK_HEADER_MAX_LENGTH)}},
    ]

    # Add predicted score block
    blocks.append(
        {'type': 'context',
         'elements': [
            {'type': 'mrkdwn',
              'text': f':heart_decoration: {msgopts["model_name"]} '
                      f'Score: *{int(item["score"]*100)}*'}
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

    data = {
        'blocks': blocks,
        'unfurl_links': False,
        'unfurl_media': False,
    }

    response = requests.post(endpoint_url, headers=header, json=data)

    if response.status_code == 200:
        pass
    elif response.status_code in (400, 500):
        import pprint
        log.error('There was an error in Slack webhook. '
                  f'status:{response.status_code} reason:{response.text}\n' +
                  pprint.pformat(data))

        raise SlackNotificationError(response.status_code)
    else:
        log.error('There was an unexpected error in the Slack webhook. Status code: '
                  f'{response.status_code}')
        raise SlackNotificationError

def normalize_text(text):
    return re.sub(r'\s+', ' ', text).strip()

@click.option('--feed-database', default='feeds.db', help='Feed database file.')
@click.option('--days', default=7, help='Number of days to look back.')
@click.option('--score-threshold', default=0.7, help='Threshold for the score.')
@click.option('--score-model-name', default='QBio', help='Name of the scoring model.')
@click.option('--max-content-length', default=400, help='Maximum length of the content.')
@click.option('--log-file', default=None, help='Log file.')
@click.option('-q', '--quiet', is_flag=True, help='Suppress log output.')
def main(feed_database, days, score_threshold, score_model_name,
         max_content_length, log_file, quiet):

    initialize_logging(task='broadcast', logfile=log_file, quiet=quiet)

    from dotenv import load_dotenv
    load_dotenv()

    since = time.time() - days * 86400
    message_options = {
        'model_name': score_model_name,
    }

    endpoint = os.environ[SLACK_ENDPOINT_KEY]
    feeddb = FeedDatabase(feed_database)

    newitems = feeddb.get_new_interesting_items(score_threshold, since,
                                                remove_duplicated=since)
    newstars = feeddb.get_newly_starred_items(since=0, remove_duplicated=since)
    if len(newstars) > 0:
        newitems = (
            pd.concat([newitems, newstars]) if len(newitems) > 0 else newstars)
    log.info(f'Found {len(newitems)} new items to broadcast.')

    for item_id, info in newitems.iterrows():
        log.info(f'Sending notification to Slack for "{info["title"]}"')
        normalize_item_for_display(info, max_content_length)
        try:
            send_slack_notification(endpoint, info, message_options)
        except SlackNotificationError:
            pass
        else:
            feeddb.update_broadcasted(item_id, int(time.time()))
            feeddb.commit()
