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

import plyvel
import numpy as np

class EmbeddingDatabase:

    dtype = np.float64

    def __init__(self, filename):
        self.db = plyvel.DB(filename, create_if_missing=True)

    def __del__(self):
        if hasattr(self, 'db'):
            self.db.close()

    def __len__(self):
        return sum(1 for _ in self.db.iterator())

    def __contains__(self, item):
        v = self.db.get(item.encode())
        return v is not None

    def keys(self):
        return set([key.decode() for key, _ in self.db.iterator()])

    def __getitem__(self, key):
        if isinstance(key, str):
            return np.frombuffer(self.db.get(key.encode()), dtype=self.dtype)
        elif isinstance(key, list):
            return np.array([
                np.frombuffer(self.db.get(k.encode()), dtype=self.dtype)
                for k in key])
        else:
            raise TypeError('Key should be str or list of str.')

    def __setitem__(self, key, value):
        if not isinstance(value, np.ndarray):
            value = np.array(value)

        assert value.dtype == self.dtype

        self.db.put(key.encode(), value.tobytes())

    def write_batch(self):
        return EmbeddingDatabaseWriteBatch(self)


class EmbeddingDatabaseWriteBatch:

    def __init__(self, edb):
        self.batch = edb.db.write_batch()
        self.dtype = edb.dtype

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.batch.write()
        else:
            self.batch.clear()

    def __setitem__(self, key, value):
        if not isinstance(value, np.ndarray):
            value = np.array(value)

        assert value.dtype == self.dtype

        self.batch.put(key.encode(), value.tobytes())
