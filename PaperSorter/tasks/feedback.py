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
import click
import pandas as pd

@click.option('--feed-database', default='feeds.db', help='Feed database file.')
@click.option('-i', '--input', help='Input file name.', required=True)
@click.option('--log-file', default=None, help='Log file.')
@click.option('-q', '--quiet', is_flag=True, help='Suppress log output.')
def main(feed_database, input, log_file, quiet):
    initialize_logging(task='feedback', logfile=log_file, quiet=quiet)

    feeddb = FeedDatabase(feed_database)

    feedback = pd.read_excel(input).set_index('id')
    newlabels = feedback['label'].dropna().astype(int)
    for item_id, label in newlabels.items():
        feeddb.update_label(item_id, label)
    feeddb.commit()

    positive = (newlabels == 1).sum()
    negative = (newlabels == 0).sum()
    log.info(f'Updated labels for {len(newlabels)} items: {positive} positive, '
             f'{negative} negative.')
