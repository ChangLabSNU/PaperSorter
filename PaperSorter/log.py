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

import logging

console = logging.StreamHandler()
console.setLevel(logging.INFO)

log = logging.getLogger('PaperSorter')
log.setLevel(logging.DEBUG)
log.addHandler(console)

def initialize_logging(logfile=None, quiet=False):
    if logfile is not None:
        formatter = logging.Formatter('[%(asctime)s] %(message)s', '%Y-%m-%d %H:%M:%S')
        logf_handler = logging.FileHandler(logfile, mode='a')
        logf_handler.setLevel(logging.DEBUG)
        logf_handler.setFormatter(formatter)
        log.addHandler(logf_handler)

    if quiet:
        console.setLevel(logging.WARNING)

