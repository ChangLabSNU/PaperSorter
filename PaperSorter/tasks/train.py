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
import click
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import xgboost as xgb
from sklearn.metrics import roc_auc_score
import pickle

@click.option('-o', '--output', default='model.pkl', help='Output file name.')
@click.option('-r', '--rounds', default=100, help='Number of boosting rounds.')
@click.option('-f', '--output-feedback', default='feedback.xlsx',
              help='Output file name for feedback.')
def main(output, rounds, output_feedback):
    feeddb = FeedDatabase('feeds.db')
    embeddingdb = EmbeddingDatabase('embeddings.db')

    feedinfo = feeddb.get_metadata().set_index('id')
    feed_ids = sorted(set(feedinfo.index.to_list()) & embeddingdb.keys())
    feedinfo = feedinfo.reindex(feed_ids).copy()

    print('Loading embeddings...')
    embs = embeddingdb[feed_ids]

    print('Scaling embeddings...')
    scaler = StandardScaler()
    embs_scaled = scaler.fit_transform(embs)

    print('Loading labels...')
    dataY = feedinfo['starred'].copy()
    dataY.update(feedinfo['label'].dropna())
    dataY = dataY.values[:, None]

    print('Splitting data...')
    X_train, X_test, y_train, y_test, fids_train, fids_test = \
        train_test_split(embs_scaled, dataY, feed_ids)

    dtrain_reg = xgb.DMatrix(X_train, y_train)
    dtest_reg = xgb.DMatrix(X_test, y_test)

    print('Training regression model...')
    evals = [(dtrain_reg, 'train'), (dtest_reg, 'validation')]
    params = {'objective': 'binary:logistic', 'device': 'cuda'}
    model = xgb.train(
        params=params,
        dtrain=dtrain_reg,
        num_boost_round=rounds,
        evals=evals,
        verbose_eval=5,
        early_stopping_rounds=10,
    )

    print('Saving model...')
    pickle.dump({
        'model': model,
        'scaler': scaler,
    }, open(output, 'wb'))

    print('Evaluating regression model...')
    y_testpred = model.predict(dtest_reg)
    rocauc = roc_auc_score(y_test, y_testpred)
    print(f"-> ROCAUC of the base model: {rocauc:.3f}")

    print('Saving spreadsheet for feedback...')
    feeds_test = feedinfo.loc[fids_test].copy()
    feeds_test['score'] = y_testpred
    feeds_test = feeds_test[
        (feeds_test['starred'] == 0) &
        (feeds_test['label'].isna())].sort_values('score', ascending=False)
    feeds_test[['score', 'title', 'content', 'label', 'author', 'origin'
                ]].to_excel(output_feedback)
