--
-- PostgreSQL database dump
--

-- Dumped from database version 16.9 (Ubuntu 16.9-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.9 (Ubuntu 16.9-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: papersorter; Type: SCHEMA; Schema: -; Owner: papersorter
--

CREATE SCHEMA papersorter;


ALTER SCHEMA papersorter OWNER TO papersorter;

--
-- Name: preferences_source; Type: TYPE; Schema: papersorter; Owner: papersorter
--

CREATE TYPE papersorter.preferences_source AS ENUM (
    'feed-star',
    'interactive',
    'alert-feedback'
);


ALTER TYPE papersorter.preferences_source OWNER TO papersorter;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: broadcasts; Type: TABLE; Schema: papersorter; Owner: papersorter
--

CREATE TABLE papersorter.broadcasts (
    feed_id bigint NOT NULL,
    channel_id integer NOT NULL,
    broadcasted_time timestamp with time zone
);


ALTER TABLE papersorter.broadcasts OWNER TO papersorter;

--
-- Name: channels; Type: TABLE; Schema: papersorter; Owner: papersorter
--

CREATE TABLE papersorter.channels (
    id integer NOT NULL,
    name text,
    endpoint_url text,
    score_threshold double precision,
    model_id integer,
    is_active boolean DEFAULT true NOT NULL
);


ALTER TABLE papersorter.channels OWNER TO papersorter;

--
-- Name: channels_id_seq; Type: SEQUENCE; Schema: papersorter; Owner: papersorter
--

CREATE SEQUENCE papersorter.channels_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE papersorter.channels_id_seq OWNER TO papersorter;

--
-- Name: channels_id_seq; Type: SEQUENCE OWNED BY; Schema: papersorter; Owner: papersorter
--

ALTER SEQUENCE papersorter.channels_id_seq OWNED BY papersorter.channels.id;


--
-- Name: embeddings; Type: TABLE; Schema: papersorter; Owner: papersorter
--

CREATE TABLE papersorter.embeddings (
    feed_id bigint NOT NULL,
    embedding public.vector(3072)
);


ALTER TABLE papersorter.embeddings OWNER TO papersorter;

--
-- Name: events; Type: TABLE; Schema: papersorter; Owner: papersorter
--

CREATE TABLE papersorter.events (
    id integer NOT NULL,
    occurred timestamp with time zone DEFAULT now() NOT NULL,
    event_type text,
    external_id text,
    content text,
    feed_id bigint,
    user_id integer
);


ALTER TABLE papersorter.events OWNER TO papersorter;

--
-- Name: events_id_seq; Type: SEQUENCE; Schema: papersorter; Owner: papersorter
--

CREATE SEQUENCE papersorter.events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE papersorter.events_id_seq OWNER TO papersorter;

--
-- Name: events_id_seq; Type: SEQUENCE OWNED BY; Schema: papersorter; Owner: papersorter
--

ALTER SEQUENCE papersorter.events_id_seq OWNED BY papersorter.events.id;

ALTER TABLE ONLY papersorter.events
    ADD CONSTRAINT fk_events_user FOREIGN KEY (user_id) REFERENCES papersorter.users(id) ON UPDATE CASCADE;


--
-- Name: feeds; Type: TABLE; Schema: papersorter; Owner: papersorter
--

CREATE TABLE papersorter.feeds (
    id bigint NOT NULL,
    external_id text,
    title text NOT NULL,
    content text,
    author text,
    origin text,
    link text,
    mediaurl text,
    tldr text,
    published timestamp with time zone NOT NULL,
    added timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE papersorter.feeds OWNER TO papersorter;

--
-- Name: feeds_id_seq; Type: SEQUENCE; Schema: papersorter; Owner: papersorter
--

CREATE SEQUENCE papersorter.feeds_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE papersorter.feeds_id_seq OWNER TO papersorter;

--
-- Name: feeds_id_seq; Type: SEQUENCE OWNED BY; Schema: papersorter; Owner: papersorter
--

ALTER SEQUENCE papersorter.feeds_id_seq OWNED BY papersorter.feeds.id;


--
-- Name: labeling_sessions; Type: TABLE; Schema: papersorter; Owner: papersorter
--

CREATE TABLE papersorter.labeling_sessions (
    id bigint NOT NULL,
    feed_id bigint NOT NULL,
    user_id bigint NOT NULL,
    score double precision,
    update_time timestamp with time zone
);


ALTER TABLE papersorter.labeling_sessions OWNER TO papersorter;

--
-- Name: models; Type: TABLE; Schema: papersorter; Owner: papersorter
--

CREATE TABLE papersorter.models (
    id integer NOT NULL,
    user_id bigint,
    name text,
    created timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean DEFAULT true NOT NULL
);


ALTER TABLE papersorter.models OWNER TO papersorter;

--
-- Name: models_id_seq; Type: SEQUENCE; Schema: papersorter; Owner: papersorter
--

CREATE SEQUENCE papersorter.models_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE papersorter.models_id_seq OWNER TO papersorter;

--
-- Name: models_id_seq; Type: SEQUENCE OWNED BY; Schema: papersorter; Owner: papersorter
--

ALTER SEQUENCE papersorter.models_id_seq OWNED BY papersorter.models.id;


--
-- Name: predicted_preferences; Type: TABLE; Schema: papersorter; Owner: papersorter
--

CREATE TABLE papersorter.predicted_preferences (
    feed_id bigint NOT NULL,
    model_id integer NOT NULL,
    score double precision NOT NULL
);


ALTER TABLE papersorter.predicted_preferences OWNER TO papersorter;

--
-- Name: preferences; Type: TABLE; Schema: papersorter; Owner: papersorter
--

CREATE TABLE papersorter.preferences (
    id bigint NOT NULL,
    feed_id integer NOT NULL,
    user_id bigint NOT NULL,
    "time" timestamp with time zone,
    score double precision,
    source papersorter.preferences_source NOT NULL
);


ALTER TABLE papersorter.preferences OWNER TO papersorter;

--
-- Name: preferences_id_seq; Type: SEQUENCE; Schema: papersorter; Owner: papersorter
--

CREATE SEQUENCE papersorter.preferences_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE papersorter.preferences_id_seq OWNER TO papersorter;

--
-- Name: preferences_id_seq; Type: SEQUENCE OWNED BY; Schema: papersorter; Owner: papersorter
--

ALTER SEQUENCE papersorter.preferences_id_seq OWNED BY papersorter.preferences.id;


--
-- Name: users; Type: TABLE; Schema: papersorter; Owner: papersorter
--

CREATE TABLE papersorter.users (
    id bigint NOT NULL,
    username text NOT NULL,
    password text NOT NULL,
    created timestamp with time zone,
    lastlogin timestamp with time zone,
    is_admin boolean DEFAULT false NOT NULL,
    timezone text DEFAULT 'Asia/Seoul'::text,
    bookmark bigint,
    feedlist_minscore integer DEFAULT 25
);


ALTER TABLE papersorter.users OWNER TO papersorter;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: papersorter; Owner: papersorter
--

CREATE SEQUENCE papersorter.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE papersorter.users_id_seq OWNER TO papersorter;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: papersorter; Owner: papersorter
--

ALTER SEQUENCE papersorter.users_id_seq OWNED BY papersorter.users.id;


--
-- Name: channels id; Type: DEFAULT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.channels ALTER COLUMN id SET DEFAULT nextval('papersorter.channels_id_seq'::regclass);


--
-- Name: events id; Type: DEFAULT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.events ALTER COLUMN id SET DEFAULT nextval('papersorter.events_id_seq'::regclass);


--
-- Name: feeds id; Type: DEFAULT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.feeds ALTER COLUMN id SET DEFAULT nextval('papersorter.feeds_id_seq'::regclass);


--
-- Name: models id; Type: DEFAULT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.models ALTER COLUMN id SET DEFAULT nextval('papersorter.models_id_seq'::regclass);


--
-- Name: preferences id; Type: DEFAULT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.preferences ALTER COLUMN id SET DEFAULT nextval('papersorter.preferences_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.users ALTER COLUMN id SET DEFAULT nextval('papersorter.users_id_seq'::regclass);


--
-- Name: broadcasts broadcast_logs_pkey; Type: CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.broadcasts
    ADD CONSTRAINT broadcast_logs_pkey PRIMARY KEY (feed_id, channel_id);


--
-- Name: channels channels_pkey; Type: CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.channels
    ADD CONSTRAINT channels_pkey PRIMARY KEY (id);


--
-- Name: embeddings embeddings_pkey; Type: CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.embeddings
    ADD CONSTRAINT embeddings_pkey PRIMARY KEY (feed_id);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id);


--
-- Name: feeds feeds_external_id_unique; Type: CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.feeds
    ADD CONSTRAINT feeds_external_id_unique UNIQUE (external_id);


--
-- Name: feeds idx_16500_primary; Type: CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.feeds
    ADD CONSTRAINT idx_16500_primary PRIMARY KEY (id);


--
-- Name: labeling_sessions idx_16506_primary; Type: CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.labeling_sessions
    ADD CONSTRAINT idx_16506_primary PRIMARY KEY (id);


--
-- Name: preferences idx_16512_primary; Type: CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.preferences
    ADD CONSTRAINT idx_16512_primary PRIMARY KEY (id);


--
-- Name: models idx_models_id_unique; Type: CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.models
    ADD CONSTRAINT idx_models_id_unique UNIQUE (id);


--
-- Name: models models_pkey; Type: CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.models
    ADD CONSTRAINT models_pkey PRIMARY KEY (id);


--
-- Name: predicted_preferences predicted_preferences_pkey; Type: CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.predicted_preferences
    ADD CONSTRAINT predicted_preferences_pkey PRIMARY KEY (feed_id, model_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: idx_16500_idx_feeds_id; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_16500_idx_feeds_id ON papersorter.feeds USING btree (external_id);


--
-- Name: idx_16512_idx_ratings_feedid; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_16512_idx_ratings_feedid ON papersorter.preferences USING btree (feed_id);


--
-- Name: idx_broadcast_logs_time; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_broadcast_logs_time ON papersorter.broadcasts USING btree (broadcasted_time);


--
-- Name: idx_events_feed; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_events_feed ON papersorter.events USING btree (feed_id);


--
-- Name: idx_events_occurred; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_events_occurred ON papersorter.events USING btree (occurred);


--
-- Name: idx_events_type; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_events_type ON papersorter.events USING btree (event_type);


--
-- Name: idx_feeds_added; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_feeds_added ON papersorter.feeds USING btree (added);


--
-- Name: idx_feeds_link; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_feeds_link ON papersorter.feeds USING btree (link);


--
-- Name: idx_feeds_mediaurl; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_feeds_mediaurl ON papersorter.feeds USING btree (mediaurl);


--
-- Name: idx_feeds_published; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_feeds_published ON papersorter.feeds USING btree (published);


--
-- Name: idx_feeds_title; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_feeds_title ON papersorter.feeds USING btree (title);


--
-- Name: idx_labeling_session; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_labeling_session ON papersorter.labeling_sessions USING btree (user_id);


--
-- Name: idx_labeling_sessions_score; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_labeling_sessions_score ON papersorter.labeling_sessions USING btree (user_id, score);


--
-- Name: idx_models_user; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_models_user ON papersorter.models USING btree (user_id);


--
-- Name: idx_preferences_score; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_preferences_score ON papersorter.preferences USING btree (score);


--
-- Name: idx_preferences_time; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_preferences_time ON papersorter.preferences USING btree ("time");


--
-- Name: idx_user_id; Type: INDEX; Schema: papersorter; Owner: papersorter
--

CREATE INDEX idx_user_id ON papersorter.preferences USING btree (user_id);


--
-- Name: broadcasts fk_broadcast_logs_channel; Type: FK CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.broadcasts
    ADD CONSTRAINT fk_broadcast_logs_channel FOREIGN KEY (channel_id) REFERENCES papersorter.channels(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: broadcasts fk_broadcast_logs_feed; Type: FK CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.broadcasts
    ADD CONSTRAINT fk_broadcast_logs_feed FOREIGN KEY (feed_id) REFERENCES papersorter.feeds(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: channels fk_channels_model; Type: FK CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.channels
    ADD CONSTRAINT fk_channels_model FOREIGN KEY (model_id) REFERENCES papersorter.models(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: events fk_events_feed; Type: FK CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.events
    ADD CONSTRAINT fk_events_feed FOREIGN KEY (feed_id) REFERENCES papersorter.feeds(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: embeddings fk_feed_id; Type: FK CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.embeddings
    ADD CONSTRAINT fk_feed_id FOREIGN KEY (feed_id) REFERENCES papersorter.feeds(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: labeling_sessions fk_labeling_sessions_feed_id; Type: FK CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.labeling_sessions
    ADD CONSTRAINT fk_labeling_sessions_feed_id FOREIGN KEY (feed_id) REFERENCES papersorter.feeds(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: labeling_sessions fk_labeling_sessions_user_id; Type: FK CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.labeling_sessions
    ADD CONSTRAINT fk_labeling_sessions_user_id FOREIGN KEY (user_id) REFERENCES papersorter.users(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: models fk_models_user_id; Type: FK CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.models
    ADD CONSTRAINT fk_models_user_id FOREIGN KEY (user_id) REFERENCES papersorter.users(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: predicted_preferences fk_pred_pref_feed; Type: FK CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.predicted_preferences
    ADD CONSTRAINT fk_pred_pref_feed FOREIGN KEY (feed_id) REFERENCES papersorter.feeds(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: predicted_preferences fk_pred_pref_model; Type: FK CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.predicted_preferences
    ADD CONSTRAINT fk_pred_pref_model FOREIGN KEY (model_id) REFERENCES papersorter.models(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: preferences fk_preferences_user_id; Type: FK CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.preferences
    ADD CONSTRAINT fk_preferences_user_id FOREIGN KEY (user_id) REFERENCES papersorter.users(id) ON UPDATE CASCADE ON DELETE RESTRICT;


--
-- Name: preferences fk_ratings_feedid; Type: FK CONSTRAINT; Schema: papersorter; Owner: papersorter
--

ALTER TABLE ONLY papersorter.preferences
    ADD CONSTRAINT fk_ratings_feedid FOREIGN KEY (feed_id) REFERENCES papersorter.feeds(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--
