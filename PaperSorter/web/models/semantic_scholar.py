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
from ...providers import FeedItem


class SemanticScholarItem(FeedItem):
    """Item model for Semantic Scholar papers."""

    def __init__(self, paper_info):
        self.paper_info = paper_info
        article_id = uuid.uuid3(uuid.NAMESPACE_URL, paper_info['url'])

        # Extract content with tldr fallback
        tldr = (
            ('(tl;dr) ' + paper_info['tldr']['text'])
            if paper_info['tldr'] and paper_info['tldr']['text']
            else '')
        content = paper_info['abstract'] or tldr

        # Parse publication date
        published_datetime = None
        pdate = paper_info['publicationDate']
        if pdate is not None:
            published_datetime = datetime(*list(map(int, paper_info['publicationDate'].split('-'))))
        else:
            published_datetime = datetime.now()

        # Initialize parent FeedItem
        super().__init__(
            external_id=str(article_id),
            title=paper_info['title'],
            content=content,
            author=', '.join([a['name'] for a in paper_info['authors']]),
            origin=self.determine_journal(paper_info),
            link=paper_info['url'],
            published=published_datetime
        )

        # Store additional attributes for compatibility
        self.href = self.link
        self.mediaUrl = self.link

    def determine_journal(self, paper_info):
        if paper_info['journal']:
            return paper_info['journal']['name']
        elif paper_info['venue']:
            return paper_info['venue']
        elif 'ArXiv' in paper_info['externalIds']:
            return 'arXiv'
        else:
            return 'Unknown'