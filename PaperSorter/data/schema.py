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

"""Database schema definitions for PaperSorter."""

# Custom types
CUSTOM_TYPES = {
    "preferences_source": {
        "type": "ENUM",
        "values": ["feed-star", "interactive", "alert-feedback"]
    }
}

# Table definitions in dependency order
TABLES = [
    {
        "name": "users",
        "columns": [
            ("id", "bigserial PRIMARY KEY"),
            ("username", "text NOT NULL UNIQUE"),
            ("password", "text NOT NULL"),
            ("created", "timestamp with time zone"),
            ("lastlogin", "timestamp with time zone"),
            ("is_admin", "boolean DEFAULT false NOT NULL"),
            ("theme", "varchar(10) DEFAULT 'light' CHECK (theme IN ('light', 'dark', 'auto'))"),
            ("timezone", "text DEFAULT 'Asia/Seoul'"),
            ("bookmark", "bigint"),
            ("feedlist_minscore", "integer DEFAULT 25"),
            ("primary_channel_id", "integer"),
        ]
    },
    {
        "name": "articles",  # Legacy compatibility
        "columns": [
            ("id", "bigserial PRIMARY KEY"),
            ("external_id", "text UNIQUE"),
            ("title", "text NOT NULL"),
            ("content", "text"),
            ("author", "text"),
            ("origin", "text"),
            ("link", "text"),
            ("mediaurl", "text"),
            ("tldr", "text"),
            ("published", "timestamp with time zone NOT NULL"),
            ("added", "timestamp with time zone DEFAULT now() NOT NULL"),
        ]
    },
    {
        "name": "feeds",  # Main table
        "columns": [
            ("id", "bigserial PRIMARY KEY"),
            ("external_id", "text UNIQUE"),
            ("title", "text NOT NULL"),
            ("content", "text"),
            ("author", "text"),
            ("origin", "text"),
            ("link", "text"),
            ("mediaurl", "text"),
            ("tldr", "text"),
            ("published", "timestamp with time zone NOT NULL"),
            ("added", "timestamp with time zone DEFAULT now() NOT NULL"),
        ]
    },
    {
        "name": "feed_sources",
        "columns": [
            ("id", "serial PRIMARY KEY"),
            ("name", "text NOT NULL"),
            ("source_type", "text NOT NULL"),
            ("url", "text"),
            ("added", "timestamp with time zone DEFAULT now() NOT NULL"),
            ("last_updated", "timestamp with time zone"),
            ("last_checked", "timestamp with time zone"),
        ]
    },
    {
        "name": "models",
        "columns": [
            ("id", "serial PRIMARY KEY"),
            ("name", "text"),
            ("notes", "text"),
            ("created", "timestamp with time zone DEFAULT now() NOT NULL"),
            ("is_active", "boolean DEFAULT true NOT NULL"),
        ]
    },
    {
        "name": "channels",
        "columns": [
            ("id", "serial PRIMARY KEY"),
            ("name", "text"),
            ("endpoint_url", "text"),
            ("score_threshold", "double precision"),
            ("model_id", "integer REFERENCES {schema}.models(id) ON UPDATE CASCADE ON DELETE CASCADE"),
            ("is_active", "boolean DEFAULT true NOT NULL"),
            ("broadcast_limit", "integer DEFAULT 20 NOT NULL CHECK (broadcast_limit >= 1 AND broadcast_limit <= 100)"),
            ("broadcast_hours", "text"),
        ]
    },
    {
        "name": "embeddings",
        "columns": [
            ("feed_id", "bigint PRIMARY KEY REFERENCES {schema}.feeds(id) ON DELETE CASCADE"),
            ("embedding", "public.vector(1536)"),
        ]
    },
    {
        "name": "preferences",
        "columns": [
            ("id", "bigserial PRIMARY KEY"),
            ("feed_id", "integer NOT NULL REFERENCES {schema}.feeds(id) ON UPDATE CASCADE ON DELETE CASCADE"),
            ("user_id", "bigint NOT NULL REFERENCES {schema}.users(id) ON UPDATE CASCADE ON DELETE RESTRICT"),
            ("time", "timestamp with time zone"),
            ("score", "double precision"),
            ("source", "{schema}.preferences_source NOT NULL"),
        ]
    },
    {
        "name": "predicted_preferences",
        "columns": [
            ("feed_id", "bigint NOT NULL REFERENCES {schema}.feeds(id) ON UPDATE CASCADE ON DELETE CASCADE"),
            ("model_id", "integer NOT NULL REFERENCES {schema}.models(id) ON UPDATE CASCADE ON DELETE CASCADE"),
            ("score", "double precision NOT NULL"),
        ],
        "primary_key": ["feed_id", "model_id"]
    },
    {
        "name": "broadcasts",
        "columns": [
            ("feed_id", "bigint NOT NULL REFERENCES {schema}.feeds(id) ON UPDATE CASCADE ON DELETE CASCADE"),
            ("channel_id", "integer NOT NULL REFERENCES {schema}.channels(id) ON UPDATE CASCADE ON DELETE CASCADE"),
            ("broadcasted_time", "timestamp with time zone"),
        ],
        "primary_key": ["feed_id", "channel_id"]
    },
    {
        "name": "labeling_sessions",
        "columns": [
            ("id", "bigserial PRIMARY KEY"),
            ("feed_id", "bigint NOT NULL REFERENCES {schema}.feeds(id) ON UPDATE CASCADE ON DELETE RESTRICT"),
            ("user_id", "bigint NOT NULL REFERENCES {schema}.users(id) ON UPDATE CASCADE ON DELETE RESTRICT"),
            ("score", "double precision"),
            ("update_time", "timestamp with time zone"),
        ]
    },
    {
        "name": "events",
        "columns": [
            ("id", "serial PRIMARY KEY"),
            ("occurred", "timestamp with time zone DEFAULT now() NOT NULL"),
            ("event_type", "text"),
            ("external_id", "text"),
            ("content", "text"),
            ("feed_id", "bigint REFERENCES {schema}.feeds(id) ON UPDATE CASCADE ON DELETE CASCADE"),
            ("user_id", "integer REFERENCES {schema}.users(id) ON UPDATE CASCADE"),
        ]
    },
    {
        "name": "saved_searches",
        "columns": [
            ("id", "bigserial PRIMARY KEY"),
            ("short_name", "text NOT NULL UNIQUE"),
            ("user_id", "integer REFERENCES {schema}.users(id) ON UPDATE CASCADE ON DELETE CASCADE"),
            ("added", "timestamp with time zone DEFAULT now() NOT NULL"),
            ("query", "text NOT NULL UNIQUE"),
            ("last_access", "timestamp with time zone"),
        ]
    },
]

# Index definitions
INDEXES = [
    # HNSW index for vector similarity search
    {
        "name": "embeddings_embedding_idx",
        "table": "embeddings",
        "type": "hnsw",
        "columns": ["embedding public.vector_cosine_ops"],
    },

    # Feeds indexes
    {"name": "idx_feeds_external_id", "table": "feeds", "columns": ["external_id"]},
    {"name": "idx_feeds_added", "table": "feeds", "columns": ["added"]},
    {"name": "idx_feeds_published", "table": "feeds", "columns": ["published"]},
    {"name": "idx_feeds_title", "table": "feeds", "columns": ["title"]},
    {"name": "idx_feeds_link", "table": "feeds", "columns": ["link"]},
    {"name": "idx_feeds_mediaurl", "table": "feeds", "columns": ["mediaurl"]},

    # Articles indexes (legacy compatibility)
    {"name": "idx_articles_external_id", "table": "articles", "columns": ["external_id"]},
    {"name": "idx_articles_added", "table": "articles", "columns": ["added"]},
    {"name": "idx_articles_published", "table": "articles", "columns": ["published"]},
    {"name": "idx_articles_title", "table": "articles", "columns": ["title"]},
    {"name": "idx_articles_link", "table": "articles", "columns": ["link"]},
    {"name": "idx_articles_mediaurl", "table": "articles", "columns": ["mediaurl"]},

    # Preferences indexes
    {"name": "idx_preferences_feed_id", "table": "preferences", "columns": ["feed_id"]},
    {"name": "idx_preferences_user_id", "table": "preferences", "columns": ["user_id"]},
    {"name": "idx_preferences_score", "table": "preferences", "columns": ["score"]},
    {"name": "idx_preferences_time", "table": "preferences", "columns": ["time"]},

    # Events indexes
    {"name": "idx_events_occurred", "table": "events", "columns": ["occurred"]},
    {"name": "idx_events_type", "table": "events", "columns": ["event_type"]},
    {"name": "idx_events_feed", "table": "events", "columns": ["feed_id"]},

    # Broadcasts indexes
    {"name": "idx_broadcasts_time", "table": "broadcasts", "columns": ["broadcasted_time"]},

    # Feed sources indexes
    {"name": "idx_feed_sources_last_checked", "table": "feed_sources", "columns": ["last_checked"]},

    # Labeling sessions indexes
    {"name": "idx_labeling_sessions_user", "table": "labeling_sessions", "columns": ["user_id"]},
    {"name": "idx_labeling_sessions_score", "table": "labeling_sessions", "columns": ["user_id", "score"]},

    # Users indexes
    {"name": "idx_users_primary_channel", "table": "users", "columns": ["primary_channel_id"]},
]

# Tables to drop in reverse dependency order (for drop_existing option)
DROP_ORDER = [
    "embeddings",
    "broadcasts",
    "predicted_preferences",
    "preferences",
    "labeling_sessions",
    "events",
    "saved_searches",
    "channels",
    "models",
    "feed_sources",
    "feeds",
    "articles",
    "users",
]