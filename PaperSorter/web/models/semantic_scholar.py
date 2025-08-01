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

"""Semantic Scholar item model."""

import uuid
from datetime import datetime
from ...providers.theoldreader import Item


class SemanticScholarItem(Item):
    """Item model for Semantic Scholar papers."""
    
    def __init__(self, paper_info):
        self.paper_info = paper_info
        article_id = uuid.uuid3(uuid.NAMESPACE_URL, paper_info['url'])

        super().__init__(None, str(article_id))

        tldr = (
            ('(tl;dr) ' + paper_info['tldr']['text'])
            if paper_info['tldr'] and paper_info['tldr']['text']
            else '')
        self.title = paper_info['title']
        self.content = paper_info['abstract'] or tldr
        self.href = paper_info['url']
        self.author = ', '.join([a['name'] for a in paper_info['authors']])
        self.origin = self.determine_journal(paper_info)
        self.mediaUrl = paper_info['url']

        pdate = paper_info['publicationDate']
        if pdate is not None:
            pubtime = datetime(*list(map(int, paper_info['publicationDate'].split('-'))))
            self.published = int(pubtime.timestamp())
        else:
            self.published = None

    def determine_journal(self, paper_info):
        if paper_info['journal']:
            return paper_info['journal']['name']
        elif paper_info['venue']:
            return paper_info['venue']
        elif 'ArXiv' in paper_info['externalIds']:
            return 'arXiv'
        else:
            return 'Unknown'