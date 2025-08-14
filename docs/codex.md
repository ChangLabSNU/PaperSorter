Here’s a concise walkthrough of the repo’s architecture, how data flows through
it, and what each major piece does.

**High-Level Overview**
- Feed ingestion: Pulls articles from RSS/Atom sources into PostgreSQL.
- Embeddings: Calls an OpenAI‑compatible API to embed each article’s text (pgvec
tor-backed).
- Prediction: XGBoost model predicts user interest; scores are stored per model.
- Web UI: Flask app for login (Google OAuth), browsing, labeling, search, admin.
- Broadcast: Slack notifier pushes high‑scoring items to channels with de‑duplic
ation.
- Jobs: Background job to generate AI “poster” HTML summaries for collections.

**CLI Commands**
- `papersorter init`: Creates schema and indexes (with pgvector) via `PaperSorte
r/data/schema.py`.
- `papersorter update`:
  - Fetches RSS items (`providers/rss.py`) → stores into `feeds`.
  - Optionally enriches with Semantic Scholar.
  - Generates embeddings and runs predictions to queue items for broadcast.
- `papersorter train`: Trains an XGBoost binary classifier from embeddings + lab
els; saves `model-<id>.pkl`.
- `papersorter predict`: Batches predictions for recent items across active mode
ls.
- `papersorter broadcast`: Sends queued items to Slack webhooks; marks processed
; performs de‑duplication.
- `papersorter serve`: Starts Flask app for labeling, search, admin screens.

All commands are wired through Click in `PaperSorter/__main__.py`, which exposes
 each task as a subcommand.

**Data Model (PostgreSQL + pgvector)**
- `feeds`: canonical article records (title, content, author, origin, link, tldr
, published, added).
- `embeddings`: `vector` column (HNSW index) keyed by `feed_id`.
- `preferences`: user labels (sources: `feed-star`, `interactive`, `alert-feedba
ck`).
- `predicted_preferences`: per‑model scores for each feed.
- `models`: registered models (active flags).
- `channels`: Slack endpoints + per‑channel score threshold + selected `model_id
`.
- `broadcasts`: unified table serving as queue + broadcast log.
- `users`: minimal user profile and settings (bookmark, min score).
- `feed_sources`: RSS/Atom sources to poll.
- `events`, `labeling_sessions`, `saved_searches`: logging, labeling, and short-
link search storage.

Schema is programmatically created in `data/schema.py`; `init` also ensures pgve
ctor is installed.

**Ingestion**
- `providers/base.py`: Provider interface and `FeedItem` dataclass.
- `providers/rss.py`: Fetches and parses feeds with robust fallbacks (custom SSL
 context, manual XML extraction if parser fails).
- `tasks/update.py`:
  - Determines which sources to poll (by `last_checked` cutoff).
  - Writes items into `feeds`, avoiding duplicates by `external_id`.
  - Calls Semantic Scholar (optional) for venue/author/TLDR enrichment.
  - Calls embeddings + scoring pipeline and queues items that pass thresholds.

**Embeddings and Similarity**
- `embedding_database.py`:
  - Manages `embeddings` table (pgvector).
  - Generates embeddings from an OpenAI‑compatible API (`api_url`, `model`, `dim
ensions`).
  - Supports similarity queries (by feed or free‑text) with server‑side vector o
ps.
- `feed_database.py`:
  - Higher‑level operations around `feeds` and queues.
  - Utilities: metadata projections, de‑duplication (title normalization + fuzzy
 match), queue manipulation, and star/label updates.

**Prediction**
- `tasks/train.py`:
  - Builds training set from `embeddings` + latest `preferences`.
  - Uses pseudo‑labels from previous predictions to augment training (with confi
gurable positive/negative cutoffs and weights).
  - Trains XGBoost + `StandardScaler`, evaluates ROC‑AUC, saves `{model, scaler}
` to `model.pkl` (or `model-<id>.pkl` conventionally in a model dir).
- `feed_predictor.py`:
  - Generates missing embeddings in batches.
  - Loads model(s), scales embeddings, predicts, writes to `predicted_preference
s`.
  - Enqueues items into per‑channel queues based on channel thresholds.

Note: There’s a known scoring caveat in `tasks/update.py` (commented): items may
 be rescored across all active models if any model is missing a score.

**Broadcasting**
- `tasks/broadcast.py`:
  - Per-channel processing of the unified `broadcasts` queue.
  - Deduplicates using prior broadcasts + fuzzy title matching.
  - Sends structured Slack messages (title, source, author, TLDR/abstract, actio
n buttons).
  - Marks items as processed (sets `broadcasted_time`).
- `broadcast_channels.py`: CRUD for `channels`.

**Web Application**
- `web/app.py`:
  - Flask factory with proxy fix, DB connection factory, background job cleanup.
  - Google OAuth via Authlib; `flask_login` for session auth.
  - Blueprints: `auth`, `main` (pages), `api` (feeds, search, settings, user).
- `web/main.py`:
  - Root feed page, labeling page, and link shortener redirect.
  - Label POST updates both `labeling_sessions` and user `preferences`.
- `web/api/*`:
  - `feeds.py`: paginated feed list API, star toggle, fetch content.
  - `search.py`: text semantic search (via embedding), LLM summarization of sele
ctions, Semantic Scholar add/search (admin).
  - `user.py`: user preferences (min score slider), bookmark, async poster job A
PIs.
- `web/jobs/poster.py`: background thread to generate a single-page React HTML “
poster” via LLM from selected articles; optionally persists HTML to disk.
- `web/auth/*`: Google OAuth routes and simple `User` model; `admin_required` de
corator.

Templates are plain HTML/CSS with light JS embedded in pages under `PaperSorter/
templates/` (e.g., `feeds_list.html` for the main UI).

**Configuration**
- `config.yml`: central config (DB, OAuth keys, embedding/summarization API prov
iders, Semantic Scholar, web base URL, storage).
- APIs are pluggable by changing `api_url`/`model` to any OpenAI‑compatible serv
ice.

**Typical Data Flow**
- Update: `update` polls sources → inserts new `feeds` → enriches (optional) → e
mbeds → predicts with active model(s) → enqueues to `broadcasts`.
- Train: user labels via web → `train` retrains model → admin updates `models`/`
channels`.
- Broadcast: `broadcast` sends Slack notifications per channel and marks process
ed.
- Web: users browse/search, star/label; admins manage channels/models/users/sour
ces; background jobs generate posters.

**Notable Details and Tradeoffs**
- De‑duplication: Fuzzy matching on normalized titles to avoid reposting similar
 items across time and sources.
- Multi‑model: Channels can point to different active models and thresholds.
- OAuth: Google OAuth is required for login; admin‑only routes guarded by decora
tor.
- Known issue: The “unscored” selection can over-trigger rescoring when new mode
ls are activated (commented in code).
- RSS fetch SSL verification is disabled (accepts all certificates) to improve f
eed compatibility; review if strict security is needed.

If you want, I can:
- Diagram the data flow with table/endpoint touchpoints.
- Sketch how to add a new provider (e.g., PubMed API) or a new broadcast target.
- Review security hardening (OAuth, SSL verify, webhook failures, rate limits).

Token usage: total=112697 input=108174 (+ 1928064 cached) output=4523 (reasoning 1024)