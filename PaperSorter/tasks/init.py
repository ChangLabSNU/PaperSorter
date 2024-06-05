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
from ..embedding_database import EmbeddingDatabase
from .update import update_feeds, update_embeddings
from ..log import log, initialize_logging
from datetime import datetime
import click
import os

FEED_EPOCH = 2020, 1, 1

@click.option('--feed-database', default='feeds.db', help='Feed database file.')
@click.option('--embedding-database', default='embeddings.db', help='Embedding database file.')
@click.option('--batch-size', default=100, help='Batch size for processing.')
@click.option('--log-file', default=None, help='Log file.')
@click.option('-q', '--quiet', is_flag=True, help='Suppress log output.')
def main(feed_database, embedding_database, batch_size, log_file, quiet):
    initialize_logging(task='init', logfile=log_file, quiet=quiet)

    from dotenv import load_dotenv
    load_dotenv()

    date_cutoff = datetime(*FEED_EPOCH).timestamp()
    feeddb = FeedDatabase(feed_database)
    embeddingdb = EmbeddingDatabase(embedding_database)

    tor_config = {
        'TOR_EMAIL': os.environ['TOR_EMAIL'],
        'TOR_PASSWORD': os.environ['TOR_PASSWORD']
    }
    update_feeds(True, feeddb, date_cutoff, credential=tor_config,
                 bulk_loading=True)

    upstage_api_key = os.environ['UPSTAGE_API_KEY']
    update_embeddings(embeddingdb, batch_size, upstage_api_key, feeddb,
                      force_reembed=True, bulk_loading=True)

    log.info('Initialization finished.')
