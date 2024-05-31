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
from langchain_upstage import UpstageEmbeddings
import xgboost as xgb
from datetime import datetime
import pickle
import click

FEED_UPDATE_LIMIT_REGULAR = 200
FEED_UPDATE_LIMIT_FULL = 1000

def batched(iterable, n):
    items = []
    for item in iterable:
        items.append(item)
        if len(items) == n:
            yield items
            items = []
    if items:
        yield items

def retrieve_items_into_db(db, iterator, starred, date_cutoff, stop_at_no_new_items=False):
    for page, items in enumerate(iterator):
        print(f"Page {page+1}")
        newitems = 0

        for item in items:
            if item in db:
                continue

            if item.title is None:
                item.get_details()
            if item.published < date_cutoff:
                #print(f'Skipping item {item.item_id} due to date cutoff {item.published}.')
                continue

            #date_formatted = datetime.fromtimestamp(item.published).strftime('%Y-%m-%d %H:%M:%S')
            #print(f'[{date_formatted}] {item.title}')
            db.insert_item(item, starred=starred)
            newitems += 1

        if newitems == 0 and stop_at_no_new_items:
            print(f'Stopping at page {page+1} due to no new items.')
            break

        db.commit()

def update_feeds(get_full_list, feeddb, date_cutoff, config):
    conn = Connection(email=config['TOR_EMAIL'], password=config['TOR_PASSWORD'])
    conn.login()

    print('Items in database:', len(feeddb))

    print('Retrieving new items...')

    searcher = ItemsSearch(conn)
    stop_at_no_new_items = not get_full_list
    update_limit = FEED_UPDATE_LIMIT_FULL if get_full_list else FEED_UPDATE_LIMIT_REGULAR

    retrieve_items_into_db(feeddb, searcher.get_starred_only(limit_items=update_limit), starred=1,
                           date_cutoff=date_cutoff, stop_at_no_new_items=stop_at_no_new_items)
    retrieve_items_into_db(feeddb, searcher.get_all(limit_items=update_limit), starred=0,
                           date_cutoff=date_cutoff, stop_at_no_new_items=stop_at_no_new_items)

    print('Done.\n')

def update_embeddings(embeddingdb, batch_size, config, feeddb):
    keystoupdate = feeddb.keys() - embeddingdb.keys()
    print('Items in database:', len(feeddb))
    print('Items in embedding database:', len(embeddingdb))
    print('Items to update:', len(keystoupdate))
    if len(keystoupdate) == 0:
        return

    embeddings_model = UpstageEmbeddings(
        upstage_api_key=config['UPSTAGE_API_KEY'],
        model='solar-embedding-1-large')

    for bid, batch in enumerate(batched(keystoupdate, batch_size)):
        print('Updating embedding: batch', bid+1, '...')

        items = [feeddb.get_formatted_item(item_id) for item_id in batch]
        embeddings = embeddings_model.embed_documents(items)

        for item_id, embedding in zip(batch, embeddings):
            embeddingdb[item_id] = embedding
        
        embeddingdb.sync()

    print('Done.\n')

def score_new_feeds(feeddb, embeddingdb, prediction_model, force_rescore=False):
    if force_rescore:
        unscored = feeddb.keys()
    else:
        unscored = feeddb.get_unscored_items()

    print('Items to score:', len(unscored))

    if not unscored:
        return

    predmodel = pickle.load(open(prediction_model, 'rb'))
    batchsize = 100

    for bid, batch in enumerate(batched(unscored, batchsize)):
        print('Scoring batch:', bid+1)
        emb = embeddingdb[batch]
        emb_xrm = predmodel['scaler'].transform(emb)

        dmtx_pred = xgb.DMatrix(emb_xrm)
        scores = predmodel['model'].predict(dmtx_pred)

        for item_id, score in zip(batch, scores):
            feeddb.update_score(item_id, score)

        feeddb.commit()

@click.option('--batch-size', default=100, help='Batch size for processing.')
@click.option('--get-full-list', is_flag=True, help='Retrieve all items from feeds.')
@click.option('--prediction-model', default='model.pkl', help='Predictor model for scoring.')
@click.option('--force-rescore', is_flag=True, help='Force rescoring all items.')
def main(batch_size, get_full_list, prediction_model, force_rescore):
    from dotenv import dotenv_values
    config = dotenv_values()

    feeddb = FeedDatabase('feeds.db')
    date_cutoff = datetime(2020, 1, 1).timestamp()

    embeddingdb = EmbeddingDatabase('embeddings.db')

    print('== Updating feeds ==')
    update_feeds(get_full_list, feeddb, date_cutoff, config)

    print('== Updating embeddings ==')
    update_embeddings(embeddingdb, batch_size, config, feeddb)

    if prediction_model != '':
        print('== Scoring new feeds ==')
        score_new_feeds(feeddb, embeddingdb, prediction_model, force_rescore)
