# Repository Guidelines

## Project Structure & Module Organization
- `PaperSorter/` – main package: `cli/`, `tasks/`, `providers/`, `notification/`, `utils/`, `web/`, `templates/`, `static/`, data helpers.
- `docs/` – Sphinx docs (`make html`).
- `docker/`, `docker-compose*.yml`, `papersorter-cli` – containerized runtime.
- `migrations/`, `SQL_SCHEMA.sql` – database schema/migrations.
- `examples/`, `tools/`, `notebook/` – scripts and prototypes.
- `config.yml` – root config (often a symlink); do not commit secrets.

## Build, Test, and Development Commands
- Create env: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- Initialize DB: `papersorter init` (Docker: `./papersorter-cli init`).
- Run web locally: `papersorter serve --debug --port 5001`.
- Update/predict/train: `papersorter update`, `papersorter predict`, `papersorter train --name "Model v1"`.
- Lint/format/types: `black PaperSorter/`, `flake8 PaperSorter/`, `mypy PaperSorter/`.
- Tests: `pytest` (optional coverage: `pytest --cov=PaperSorter` if `pytest-cov` installed).
- Docs: `cd docs && make html`.

## Coding Style & Naming Conventions
- Python 3.8+; PEP 8 with Black formatting (88 cols default).
- Lint with Flake8; type hints required on public APIs; keep `mypy` clean.
- Naming: modules/functions/vars `snake_case`; classes `PascalCase`; constants `UPPER_CASE`.
- Keep modules focused; prefer explicit imports; add docstrings for non-trivial functions.

## Testing Guidelines
- Framework: Pytest. Place tests under `tests/` mirroring `PaperSorter/` paths.
- File naming: `tests/test_*.py`; use fixtures and fakes over hitting real services.
- Database: prefer isolated test DB or mocks; avoid modifying prod schemas.
- Aim for coverage on new/changed code; include CLI and key branches.

## Commit & Pull Request Guidelines
- Commits: imperative, concise subject (e.g., "Fix event logging in update task").
- Include rationale in body when behavior changes; reference issues (`Fixes #123`).
- PRs must: describe scope and impact, include screenshots for UI, sample CLI output/logs for tasks, update docs/CHANGELOG when user-facing, note migration impacts.
- CI hygiene: run `black`, `flake8`, `mypy`, and `pytest` locally before opening PRs.

## Security & Configuration Tips
- Do not commit secrets. Use `.env` (copy from `.env.example`) and `config.yml` locally; keep lab-specific configs (e.g., `qbio/`) out of PRs unless intended.
- Validate external API keys via environment/config; never hardcode.
- For Docker, prefer `docker-compose up -d` and manage settings in `.env`.
