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

__all__ = ['Connection', 'ItemsSearch', 'Item']

from ..contrib.tor import Connection
from ..contrib.tor import url_api
from ..contrib.tor import ItemsSearch as BaseItemsSearch
from ..contrib.tor import Item as BaseItem

class Item(BaseItem):

    CATEGORY_STARRED = 'user/-/state/com.google/starred'
    CATEGORY_LIKE = 'user/-/state/com.google/like'

    def __init__(self, connection, item_id):
        self.connection = connection

        self.starred = self.like = None # True / False / None (unknown)

        if isinstance(item_id, dict):
            self.item_id = item_id['id']
            self.title = item_id['title']
            self.content = item_id['summary']['content']
            self.href = item_id['canonical'][0]['href']
            self.author = item_id['author']
            self.origin = item_id['origin']['title']
            if 'enclosure' in item_id:
                self.mediaUrl = item_id['enclosure'][0]['href']
            else:
                self.mediaUrl = None
            self.published = item_id['published']

            self.detect_user_interactions(item_id)
        else:
            self.item_id = item_id
            self.title = None
            self.content = None
            self.href = None
            self.author = None
            self.origin = None
            self.mediaUrl = None
            self.published = None

    def detect_user_interactions(self, tor_item):
        if 'categories' not in tor_item:
            return

        self.starred = self.CATEGORY_STARRED in tor_item['categories']
        self.like = self.CATEGORY_LIKE in tor_item['categories']


class ItemsSearch(BaseItemsSearch):

    def _make_search_request(self, var, limit_items=1000):
        var['n'] = limit_items
        return self.connection.make_request(
                url_api + 'stream/contents',
                var,
                use_get=True
        )

    def _load_rest(self, continuation, var, limit_items=1000, items_list=None):
        if items_list is not None:
            yield [
                Item(self.connection, item)
                for item in items_list
            ]

        while continuation is not None:
            var['c'] = continuation
            resp = self._make_search_request(var, limit_items)
            continuation = resp.get('continuation')
            yield [
                Item(self.connection, item)
                for item in resp['items']
            ]

    def get_starred_only(self, limit_items=1000, feed=None):
        var = {
            's': 'user/-/state/com.google/starred'
        }
        if feed is not None:
            var['s'] = feed
        resp = self._make_search_request(var, limit_items)
        continuation = resp.get('continuation')
        items_list = resp.get('items', [])
        return self._load_rest(continuation, var, limit_items, items_list)

    def get_liked_only(self, limit_items=1000, feed=None):
        var = {
            's': 'user/-/state/com.google/like'
        }
        if feed is not None:
            var['s'] = feed
        resp = self._make_search_request(var, limit_items)
        continuation = resp.get('continuation')
        items_list = resp.get('items', [])
        return self._load_rest(continuation, var, limit_items, items_list)

    def get_read_only(self, limit_items=1000, feed=None):
        var = {
            's': 'user/-/state/com.google/read'
        }
        if feed is not None:
            var['s'] = feed
        resp = self._make_search_request(var, limit_items)
        continuation = resp.get('continuation')
        items_list = resp.get('items', [])
        return self._load_rest(continuation, var, limit_items, items_list)

    def get_all(self, limit_items=1000, feed=None):
        var = {
            's': 'user/-/state/com.google/reading-list'
        }
        if feed is not None:
            var['s'] = feed
        resp = self._make_search_request(var, limit_items)
        continuation = resp.get('continuation')
        items_list = resp.get('items', [])
        return self._load_rest(continuation, var, limit_items, items_list)
