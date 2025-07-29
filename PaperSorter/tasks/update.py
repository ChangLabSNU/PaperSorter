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

from ..providers.theoldreader import Connection, ItemsSearch
from ..feed_database import FeedDatabase
from ..embedding_database import EmbeddingDatabase
from ..broadcast_channels import BroadcastChannels
from ..log import log, initialize_logging
from openai import OpenAI
import xgboost as xgb
from datetime import datetime, timedelta
import time
import requests
import pickle
import click
import os

FEED_UPDATE_LIMIT_REGULAR = 200
FEED_UPDATE_LIMIT_FULL = 1000
FEED_EPOCH = 2020, 1, 1

OPENAI_API_URL = 'https://api.openai.com/v1'
OPENAI_EMBEDDING_MODEL = 'text-embedding-3-large'

S2_VENUE_UPDATE_BLACKLIST = {
    'Molecules and Cells', # Molecular Cell (Cell Press) is incorrectly matched to this.
}

def batched(iterable, n):
    items = []
    for item in iterable:
        items.append(item)
        if len(items) == n:
            yield items
            items = []
    if items:
        yield items

def update_star_status(db, items):
    time_begin = min(it.published for it in items) - 1
    time_end = max(it.published for it in items) + 1

    current_status = db.get_star_status(time_begin, time_end)
    changes = 0

    for item in items:
        if item.starred is None or item.item_id not in current_status:
            continue

        if item.starred != current_status[item.item_id]:
            if item.starred:
                log.info(f'New star: {item.title}')
            else:
                log.info(f'Dropped star: {item.title}')

            db.update_star_status(item.item_id, item.starred)
            changes += 1

    if changes > 0:
        db.commit()

def retrieve_items_into_db(db, iterator, starred, date_cutoff, stop_at_no_new_items=False,
                           bulk_loading=False):
    default_broadcasted = 0 if bulk_loading else None
    progress_log = log.info if bulk_loading else log.debug
    new_item_ids = []  # Track newly added items

    for page, items in enumerate(iterator):
        progress_log(f'Processing page {page+1}')
        if page == 0 and len(items) > 0:
            # Update starred status for the latest items only
            update_star_status(db, items)

        newitems = 0

        for item in items:
            if item in db:
                continue

            if item.title is None:
                item.get_details()
            if item.published < date_cutoff:
                log.debug(f'Skipping item {item.item_id} due to date cutoff {item.published}.')
                continue

            date_formatted = datetime.fromtimestamp(item.published).strftime('%Y-%m-%d %H:%M:%S')
            log.debug(f'Retrieved: [{date_formatted}] {item.title}')
            db.insert_item(item, starred=starred, broadcasted=default_broadcasted)
            new_item_ids.append(item.item_id)
            newitems += 1

        if newitems == 0 and stop_at_no_new_items:
            log.debug(f'Stopping at page {page+1} due to no new items.')
            break

        db.commit()

    return new_item_ids

def update_feeds(get_full_list, feeddb, date_cutoff, bulk_loading, credential):
    conn = Connection(email=credential['TOR_EMAIL'], password=credential['TOR_PASSWORD'])
    conn.login()

    log.info('Updating feeds...')
    log.debug(f'Items in database: {len(feeddb)}')

    searcher = ItemsSearch(conn)
    stop_at_no_new_items = not get_full_list
    update_limit = FEED_UPDATE_LIMIT_FULL if get_full_list else FEED_UPDATE_LIMIT_REGULAR

    new_item_ids = []

    # Get starred items
    starred_new = retrieve_items_into_db(feeddb, searcher.get_starred_only(limit_items=update_limit), starred=1,
                                        date_cutoff=date_cutoff, stop_at_no_new_items=stop_at_no_new_items,
                                        bulk_loading=bulk_loading)
    new_item_ids.extend(starred_new)

    # Get all items
    all_new = retrieve_items_into_db(feeddb, searcher.get_all(limit_items=update_limit), starred=0,
                                    date_cutoff=date_cutoff, stop_at_no_new_items=stop_at_no_new_items,
                                    bulk_loading=bulk_loading)
    new_item_ids.extend(all_new)

    return new_item_ids

def update_embeddings(embeddingdb, batch_size, api_config, feeddb, bulk_loading=False,
                      force_reembed=False):
    keystoupdate = feeddb.keys().copy()
    if not force_reembed:
        keystoupdate -= embeddingdb.keys()
    progress_log = log.info if bulk_loading else log.debug

    log.info(f'Items: feed_db:{len(feeddb)} '
             f'embedding_db:{len(embeddingdb)} '
             f'to_update:{len(keystoupdate)}')
    if len(keystoupdate) == 0:
        return 0

    log.info('Updating embeddings...')

    api_url = api_config.get('api_url', OPENAI_API_URL)
    client = OpenAI(api_key=api_config['api_key'], base_url=api_url)
    model_name = api_config.get('model') or OPENAI_EMBEDDING_MODEL

    with embeddingdb.write_batch() as writer:
        for bid, batch in enumerate(batched(keystoupdate, batch_size)):
            progress_log(f'Updating embedding: batch {bid+1} ...')

            items = [feeddb.get_formatted_item(item_id) for item_id in batch]
            embresults = client.embeddings.create(model=model_name, input=items)

            for item_id, result in zip(batch, embresults.data):
                writer[item_id] = result.embedding

    return len(keystoupdate)

def update_s2_info(feeddb, s2_config, new_item_ids, dateoffset=60):
    if not new_item_ids:
        return

    api_headers = {'X-API-KEY': s2_config['S2_API_KEY']}
    api_url = s2_config.get('S2_API_URL', 'http://api.semanticscholar.org/graph/v1/paper/search/match')

    log.info(f'Retrieving Semantic Scholar information for {len(new_item_ids)} new items...')

    # Convert external_ids to feed_ids
    feed_ids = []
    for external_id in new_item_ids:
        feeddb.cursor.execute('SELECT id FROM feeds WHERE external_id = %s', (external_id,))
        result = feeddb.cursor.fetchone()
        if result:
            feed_ids.append(result['id'])

    for feed_id in feed_ids:
        time.sleep(s2_config['S2_THROTTLE'])

        feedinfo = feeddb[feed_id]
        if not feedinfo:
            continue

        pubdate = datetime.fromtimestamp(feedinfo['published'])

        date_from = pubdate - timedelta(days=dateoffset)
        date_to = pubdate + timedelta(days=dateoffset)
        date_range = (f'{date_from.year}-{date_from.month:02d}-{date_from.day:02d}:'
                      f'{date_to.year}-{date_to.month:02d}-{date_to.day:02d}')

        search_query = {
            'query': feedinfo['title'],
            'publicationDateOrYear': date_range,
            'fields': 'title,url,authors,venue,publicationDate,tldr',
        }
        r = requests.get(api_url, headers=api_headers, params=search_query).json()
        if 'data' not in r or not r['data']:
            continue

        s2feed = r['data'][0]
        # s2feed['matchScore']
        if s2feed['tldr'] and s2feed['tldr'].get('text'):
            feeddb.update_tldr(feed_id, s2feed['tldr']['text'])
        if s2feed['authors']:
            feeddb.update_author(feed_id, format_authors(s2feed['authors']))
        if (s2feed.get('venue') is not None and s2feed['venue'].strip() and
                s2feed['venue'] not in S2_VENUE_UPDATE_BLACKLIST):
            feeddb.update_origin(feed_id, s2feed['venue'])

        feeddb.commit()

def format_authors(authors, max_authors=4):
    assert max_authors >= 3

    if len(authors) <= max_authors:
        return ', '.join(author['name'] for author in authors)
    else:
        first_authors = ', '.join(a['name'] for a in authors[:max_authors-2])
        last_authors = ', '.join(a['name'] for a in authors[-2:])
        return first_authors + ', ..., ' + last_authors

def add_starred_to_queue(feeddb):
    """Add recently starred items to the broadcast queue."""
    # Get recently starred items (last 7 days)
    since = time.time() - 7 * 86400
    feeddb.cursor.execute('''
        SELECT f.id, f.title
        FROM feeds f
        JOIN preferences p ON f.id = p.feed_id
        WHERE p.source = 'feed-star'
              AND p.score > 0
              AND p.time >= to_timestamp(%s)
              AND NOT EXISTS (
                  SELECT 1 FROM broadcasts bl
                  WHERE bl.feed_id = f.id AND bl.channel_id = 1
              )
    ''', (since,))

    starred_items = feeddb.cursor.fetchall()
    for item in starred_items:
        feeddb.add_to_broadcast_queue(item['id'])
        log.info(f'Added starred item to broadcast queue: {item["title"]}')

def score_new_feeds(feeddb, embeddingdb, channels, model_dir, force_rescore=False,
                    check_starred=True):
    if force_rescore:
        unscored = feeddb.keys()
    else:
        unscored = feeddb.get_unscored_items()

    log.info('Scoring new feeds...')
    log.debug(f'Items to score: {len(unscored)}')

    if not unscored:
        return

    # Get all channels to process items for each channel with its own settings
    all_channels = channels.get_all_channels()
    if not all_channels:
        log.warning('No channels configured')
        return

    # Load models for each channel
    channel_models = {}
    for channel in all_channels:
        model_id = channel['model_id'] or 1  # Default to model 1
        if model_id not in channel_models:
            model_file_path = f'{model_dir}/model-{model_id}.pkl'
            try:
                channel_models[model_id] = pickle.load(open(model_file_path, 'rb'))
                log.info(f'Loaded model {model_id} from {model_file_path}')
            except FileNotFoundError:
                log.error(f'Model file not found: {model_file_path}')
                channel_models[model_id] = None
    batchsize = 100

    for bid, batch in enumerate(batched(unscored, batchsize)):
        log.debug(f'Scoring batch: {bid+1}')
        emb = embeddingdb[batch]

        # Score with each channel's model and add to appropriate queues
        for channel in all_channels:
            model_id = channel['model_id'] or 1
            predmodel = channel_models.get(model_id)
            if not predmodel:
                continue

            score_threshold = channel['score_threshold'] or 0.7
            channel_id = channel['id']

            emb_xrm = predmodel['scaler'].transform(emb)
            dmtx_pred = xgb.DMatrix(emb_xrm)
            scores = predmodel['model'].predict(dmtx_pred)

            for item_id, score in zip(batch, scores):
                # Update score for this model (using model_id=1 for backward compatibility)
                if channel_id == 1:  # Only update main score for default channel
                    feeddb.update_score(item_id, score)
                    iteminfo = feeddb[item_id]
                    log.info(f'New item: [{score:.2f}] {iteminfo["origin"]} / '
                             f'{iteminfo["title"]}')

                # Add high-scoring items to this channel's broadcast queue
                if score >= score_threshold:
                    # Get feed_id from external_id
                    feeddb.cursor.execute('SELECT id FROM feeds WHERE external_id = %s', (item_id,))
                    result = feeddb.cursor.fetchone()
                    if result:
                        feed_id = result['id']
                        # Check if already broadcasted
                        feeddb.cursor.execute('''
                            SELECT 1 FROM broadcast_logs
                            WHERE feed_id = %s AND channel_id = %s
                        ''', (feed_id, channel_id))
                        if not feeddb.cursor.fetchone():
                            feeddb.add_to_broadcast_queue(feed_id, channel_id)
                            iteminfo = feeddb[item_id]
                            log.info(f'Added to channel {channel["name"]} queue: {iteminfo["title"]}')

        feeddb.commit()

    # Also check for newly starred items and add them to the queue
    if check_starred:
        add_starred_to_queue(feeddb)

@click.option('--config', default='qbio/config.yml', help='Database configuration file.')
@click.option('--batch-size', default=100, help='Batch size for processing.')
@click.option('--get-full-list', is_flag=True, help='Retrieve all items from feeds.')
@click.option('--force-reembed', is_flag=True, help='Force recalculation of embeddings for all items.')
@click.option('--force-rescore', is_flag=True, help='Force rescoring all items.')
@click.option('--log-file', default=None, help='Log file.')
@click.option('-q', '--quiet', is_flag=True, help='Suppress log output.')
def main(config, batch_size, get_full_list,
         force_reembed, force_rescore, log_file, quiet):
    initialize_logging(task='update', logfile=log_file, quiet=quiet)

    # Load configuration
    import yaml
    with open(config, 'r') as f:
        full_config = yaml.safe_load(f)

    date_cutoff = datetime(*FEED_EPOCH).timestamp()
    feeddb = FeedDatabase(config)
    embeddingdb = EmbeddingDatabase(config)
    channels = BroadcastChannels(config)

    tor_config = {
        'TOR_EMAIL': full_config['feed_service']['username'],
        'TOR_PASSWORD': full_config['feed_service']['password']
    }
    new_item_ids = update_feeds(get_full_list, feeddb, date_cutoff, bulk_loading=False,
                                credential=tor_config)

    s2_config = {
        'S2_API_KEY': full_config['semanticscholar']['api_key'],
        'S2_API_URL': full_config['semanticscholar'].get('api_url'),
        'S2_THROTTLE': full_config['semanticscholar'].get('throttle', 1),
    }
    try:
        update_s2_info(feeddb, s2_config, new_item_ids)
    except requests.exceptions.ConnectionError:
        import traceback
        traceback.print_exc()
        # Show the exception but proceed to the next job.

    num_updates = update_embeddings(embeddingdb, batch_size, full_config['embedding_api'],
                                    feeddb, force_reembed=force_reembed,
                                    bulk_loading=False)

    if num_updates > 0:
        model_dir = full_config.get('models', {}).get('path', '.')
        score_new_feeds(feeddb, embeddingdb, channels, model_dir, force_rescore)

    log.info('Update completed.')
