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
            newitems += 1

        if newitems == 0 and stop_at_no_new_items:
            log.debug(f'Stopping at page {page+1} due to no new items.')
            break

        db.commit()

def update_feeds(get_full_list, feeddb, date_cutoff, bulk_loading, credential):
    conn = Connection(email=credential['TOR_EMAIL'], password=credential['TOR_PASSWORD'])
    conn.login()

    log.info('Updating feeds...')
    log.debug(f'Items in database: {len(feeddb)}')

    searcher = ItemsSearch(conn)
    stop_at_no_new_items = not get_full_list
    update_limit = FEED_UPDATE_LIMIT_FULL if get_full_list else FEED_UPDATE_LIMIT_REGULAR

    retrieve_items_into_db(feeddb, searcher.get_starred_only(limit_items=update_limit), starred=1,
                           date_cutoff=date_cutoff, stop_at_no_new_items=stop_at_no_new_items,
                           bulk_loading=bulk_loading)
    retrieve_items_into_db(feeddb, searcher.get_all(limit_items=update_limit), starred=0,
                           date_cutoff=date_cutoff, stop_at_no_new_items=stop_at_no_new_items,
                           bulk_loading=bulk_loading)

def update_embeddings(embeddingdb, batch_size, api_key, feeddb, bulk_loading=False,
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

    client = OpenAI(api_key=api_key, base_url=OPENAI_API_URL)
    model_name = OPENAI_EMBEDDING_MODEL

    with embeddingdb.write_batch() as writer:
        for bid, batch in enumerate(batched(keystoupdate, batch_size)):
            progress_log(f'Updating embedding: batch {bid+1} ...')

            items = [feeddb.get_formatted_item(item_id) for item_id in batch]
            embresults = client.embeddings.create(model=model_name, input=items)

            for item_id, result in zip(batch, embresults.data):
                writer[item_id] = result.embedding

    return len(keystoupdate)

def update_s2_info(feeddb, s2_config, dateoffset=60):
    unscored_items = feeddb.get_unscored_items()
    if not unscored_items:
        return

    api_headers = {'X-API-KEY': s2_config['S2_API_KEY']}

    log.info('Retrieving Semantic Scholar information...')

    for feed_id in unscored_items:
        time.sleep(s2_config['S2_THROTTLE'])

        feedinfo = feeddb[feed_id]
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
        url = 'http://api.semanticscholar.org/graph/v1/paper/search/match'
        r = requests.get(url, headers=api_headers, params=search_query).json()
        if 'data' not in r or not r['data']:
            continue

        s2feed = r['data'][0]
        # s2feed['matchScore']
        if s2feed['tldr'] and s2feed['tldr'].get('text'):
            feeddb.update_tldr(feed_id, s2feed['tldr']['text'])
        if s2feed['authors']:
            feeddb.update_author(feed_id, format_authors(s2feed['authors']))

        feeddb.commit()

def format_authors(authors, max_authors=4):
    assert max_authors >= 3

    if len(authors) <= max_authors:
        return ', '.join(author['name'] for author in authors)
    else:
        first_authors = ', '.join(a['name'] for a in authors[:max_authors-2])
        last_authors = ', '.join(a['name'] for a in authors[-2:])
        return first_authors + ', ..., ' + last_authors

def score_new_feeds(feeddb, embeddingdb, prediction_model, force_rescore=False):
    if force_rescore:
        unscored = feeddb.keys()
    else:
        unscored = feeddb.get_unscored_items()

    log.info('Scoring new feeds...')
    log.debug(f'Items to score: {len(unscored)}')

    if not unscored:
        return

    predmodel = pickle.load(open(prediction_model, 'rb'))
    batchsize = 100

    for bid, batch in enumerate(batched(unscored, batchsize)):
        log.debug(f'Scoring batch: {bid+1}')
        emb = embeddingdb[batch]
        emb_xrm = predmodel['scaler'].transform(emb)

        dmtx_pred = xgb.DMatrix(emb_xrm)
        scores = predmodel['model'].predict(dmtx_pred)

        for item_id, score in zip(batch, scores):
            feeddb.update_score(item_id, score)
            iteminfo = feeddb[item_id]
            log.info(f'New item: [{score:.2f}] {iteminfo["origin"]} / '
                     f'{iteminfo["title"]}')

        feeddb.commit()

@click.option('--feed-database', default='feeds.db', help='Feed database file.')
@click.option('--embedding-database', default='embeddings.db', help='Embedding database file.')
@click.option('--batch-size', default=100, help='Batch size for processing.')
@click.option('--get-full-list', is_flag=True, help='Retrieve all items from feeds.')
@click.option('--prediction-model', default='model.pkl', help='Predictor model for scoring.')
@click.option('--force-reembed', is_flag=True, help='Force recalculation of embeddings for all items.')
@click.option('--force-rescore', is_flag=True, help='Force rescoring all items.')
@click.option('--log-file', default=None, help='Log file.')
@click.option('-q', '--quiet', is_flag=True, help='Suppress log output.')
def main(feed_database, embedding_database, batch_size, get_full_list,
         prediction_model, force_reembed, force_rescore, log_file, quiet):
    initialize_logging(task='update', logfile=log_file, quiet=quiet)

    from dotenv import load_dotenv
    load_dotenv()

    date_cutoff = datetime(*FEED_EPOCH).timestamp()
    feeddb = FeedDatabase(feed_database)
    embeddingdb = EmbeddingDatabase(embedding_database)

    tor_config = {
        'TOR_EMAIL': os.environ['TOR_EMAIL'],
        'TOR_PASSWORD': os.environ['TOR_PASSWORD']
    }
    update_feeds(get_full_list, feeddb, date_cutoff, bulk_loading=False,
                 credential=tor_config)

    s2_config = {
        'S2_API_KEY': os.environ['S2_API_KEY'],
        'S2_THROTTLE': 1,
    }
    update_s2_info(feeddb, s2_config)

    api_key = os.environ['PAPERSORTER_API_KEY']
    num_updates = update_embeddings(embeddingdb, batch_size, api_key,
                                    feeddb, force_reembed=force_reembed,
                                    bulk_loading=False)

    if prediction_model != '' and num_updates > 0:
        score_new_feeds(feeddb, embeddingdb, prediction_model, force_rescore)

    log.info('Update completed.')
