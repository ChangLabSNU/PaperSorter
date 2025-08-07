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

"""User model for authentication."""

from flask_login import UserMixin


class User(UserMixin):
    """User model for Flask-Login integration."""

    def __init__(
        self,
        id,
        username,
        email=None,
        is_admin=False,
        timezone="Asia/Seoul",
        feedlist_minscore=None,
    ):
        self.id = id
        self.username = username
        self.email = email
        self.is_admin = is_admin
        self.timezone = timezone
        # Store the integer value from DB, convert to decimal for internal use
        self.feedlist_minscore_int = (
            feedlist_minscore if feedlist_minscore is not None else 25
        )
        self.feedlist_minscore = (
            self.feedlist_minscore_int / 100.0
        )  # Convert to decimal (e.g., 25 -> 0.25)
