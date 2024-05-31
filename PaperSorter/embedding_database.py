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

import bsddb3
import numpy as np

class EmbeddingDatabase:

    dtype = np.float64

    def __init__(self, filename):
        self.db = bsddb3.hashopen(filename, 'c')

    def __del__(self):
        self.db.close()

    def __len__(self):
        return len(self.db)

    def __contains__(self, item):
        return item in self.db

    def keys(self):
        return set(map(bytes.decode, self.db.keys()))

    def __getitem__(self, key):
        if isinstance(key, str):
            return np.frombuffer(self.db[key.encode()], dtype=self.dtype)
        elif isinstance(key, list):
            return np.array([
                np.frombuffer(self.db[k.encode()], dtype=self.dtype)
                for k in key])
        else:
            raise TypeError('Key should be str or list of str.')

    def __setitem__(self, key, value):
        if not isinstance(value, np.ndarray):
            value = np.array(value)

        assert value.dtype == self.dtype

        self.db[key.encode()] = value.tobytes()

    def sync(self):
        self.db.sync()
