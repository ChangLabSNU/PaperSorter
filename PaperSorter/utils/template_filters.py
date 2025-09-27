#!/usr/bin/env python3
#
# Copyright (c) 2024-2025 Seoul National University
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

"""Shared Jinja2 template filters for PaperSorter."""

import html
import re
from markupsafe import Markup, escape


def safe_html_filter(text):
    """
    Filter to allow only safe HTML tags in text content.
    Allows: i, b, em, strong, sup, sub tags while escaping everything else.
    """
    if not text:
        return text

    # First escape all HTML
    escaped_text = escape(text)

    # Define allowed tags and their replacements back to HTML
    allowed_tags = {
        r'&lt;i&gt;(.*?)&lt;/i&gt;': r'<i>\1</i>',
        r'&lt;b&gt;(.*?)&lt;/b&gt;': r'<b>\1</b>',
        r'&lt;em&gt;(.*?)&lt;/em&gt;': r'<em>\1</em>',
        r'&lt;strong&gt;(.*?)&lt;/strong&gt;': r'<strong>\1</strong>',
        r'&lt;sup&gt;(.*?)&lt;/sup&gt;': r'<sup>\1</sup>',
        r'&lt;sub&gt;(.*?)&lt;/sub&gt;': r'<sub>\1</sub>',
    }

    # Convert back allowed tags from escaped to HTML
    result = str(escaped_text)
    for pattern, replacement in allowed_tags.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE | re.DOTALL)

    return Markup(result)


def strip_html_filter(text):
    """
    Strip all HTML tags from text for use in page titles and meta tags.
    """
    if not text:
        return text

    # Remove all HTML tags using regex
    clean_text = re.sub(r'<[^>]+>', '', str(text))

    # Also decode HTML entities
    clean_text = html.unescape(clean_text)

    return clean_text


def register_filters(jinja_env):
    """
    Register all custom template filters with a Jinja2 environment.

    Args:
        jinja_env: Jinja2 Environment instance
    """
    jinja_env.filters['safe_html'] = safe_html_filter
    jinja_env.filters['strip_html'] = strip_html_filter