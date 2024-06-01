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
from datetime import datetime
import pickle
import click
import os

FEED_UPDATE_LIMIT_REGULAR = 200
FEED_UPDATE_LIMIT_FULL = 1000
FEED_EPOCH = 2020, 1, 1

OPENAI_API_URL = 'https://api.upstage.ai/v1/solar'
OPENAI_EMBEDDING_MODEL = 'solar-embedding-1-large-passage'

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
                log.info(f'New star to {item.item_id}')
            else:
                log.info(f'Dropping a star from {item.item_id}')

            db.update_star_status(item.item_id, item.starred)
            changes += 1

    if changes > 0:
        db.commit()

def retrieve_items_into_db(db, iterator, starred, date_cutoff, stop_at_no_new_items=False):
    for page, items in enumerate(iterator):
        log.info(f"Processing page {page+1}")
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
                #print(f'Skipping item {item.item_id} due to date cutoff {item.published}.')
                continue

            date_formatted = datetime.fromtimestamp(item.published).strftime('%Y-%m-%d %H:%M:%S')
            log.info(f'Retrieved [{date_formatted}] {item.title}')
            db.insert_item(item, starred=starred)
            newitems += 1

        if newitems == 0 and stop_at_no_new_items:
            log.info(f'Stopping at page {page+1} due to no new items.')
            break

        db.commit()

def update_feeds(get_full_list, feeddb, date_cutoff, config):
    conn = Connection(email=config['TOR_EMAIL'], password=config['TOR_PASSWORD'])
    conn.login()

    log.info(f'Items in database: {len(feeddb)}')

    log.info('Retrieving new items...')

    searcher = ItemsSearch(conn)
    stop_at_no_new_items = not get_full_list
    update_limit = FEED_UPDATE_LIMIT_FULL if get_full_list else FEED_UPDATE_LIMIT_REGULAR

    retrieve_items_into_db(feeddb, searcher.get_starred_only(limit_items=update_limit), starred=1,
                           date_cutoff=date_cutoff, stop_at_no_new_items=stop_at_no_new_items)
    retrieve_items_into_db(feeddb, searcher.get_all(limit_items=update_limit), starred=0,
                           date_cutoff=date_cutoff, stop_at_no_new_items=stop_at_no_new_items)

    log.info('Done.\n')

def update_embeddings(embeddingdb, batch_size, api_key, feeddb, force_reembed=False):
    keystoupdate = feeddb.keys().copy()
    if not force_reembed:
        keystoupdate -= embeddingdb.keys()

    log.info(f'Items in database: {len(feeddb)}')
    log.info(f'Items in embedding database: {len(embeddingdb)}')
    log.info(f'Items to update: {len(keystoupdate)}')
    if len(keystoupdate) == 0:
        return

    client = OpenAI(api_key=api_key, base_url=OPENAI_API_URL)
    model_name = OPENAI_EMBEDDING_MODEL

    with embeddingdb.write_batch() as writer:
        for bid, batch in enumerate(batched(keystoupdate, batch_size)):
            log.info(f'Updating embedding: batch {bid+1} ...')

            items = [feeddb.get_formatted_item(item_id) for item_id in batch]
            embresults = client.embeddings.create(model=model_name, input=items)

            for item_id, result in zip(batch, embresults.data):
                writer[item_id] = result.embedding

    log.info('Done.\n')

def score_new_feeds(feeddb, embeddingdb, prediction_model, force_rescore=False):
    if force_rescore:
        unscored = feeddb.keys()
    else:
        unscored = feeddb.get_unscored_items()

    log.info(f'Items to score: {len(unscored)}')

    if not unscored:
        return

    predmodel = pickle.load(open(prediction_model, 'rb'))
    batchsize = 100

    for bid, batch in enumerate(batched(unscored, batchsize)):
        log.info(f'Scoring batch: {bid+1}')
        emb = embeddingdb[batch]
        emb_xrm = predmodel['scaler'].transform(emb)

        dmtx_pred = xgb.DMatrix(emb_xrm)
        scores = predmodel['model'].predict(dmtx_pred)

        for item_id, score in zip(batch, scores):
            feeddb.update_score(item_id, score)

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
    initialize_logging(logfile=log_file, quiet=quiet)

    from dotenv import load_dotenv
    load_dotenv()

    date_cutoff = datetime(*FEED_EPOCH).timestamp()
    feeddb = FeedDatabase(feed_database)
    embeddingdb = EmbeddingDatabase(embedding_database)

    log.info('== Updating feeds ==')
    tor_config = {
        'TOR_EMAIL': os.environ['TOR_EMAIL'],
        'TOR_PASSWORD': os.environ['TOR_PASSWORD']
    }
    update_feeds(get_full_list, feeddb, date_cutoff, tor_config)

    log.info('== Updating embeddings ==')
    upstage_api_key = os.environ['UPSTAGE_API_KEY']
    update_embeddings(embeddingdb, batch_size, upstage_api_key, feeddb, force_reembed)

    if prediction_model != '':
        log.info('== Scoring new feeds ==')
        score_new_feeds(feeddb, embeddingdb, prediction_model, force_rescore)
