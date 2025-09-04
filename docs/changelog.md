# Changelog

All notable changes to PaperSorter will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive Sphinx documentation with Read the Docs theme
- Auto-generated API documentation from docstrings
- CLI command reference with examples
- Getting Started guides for new users
- GitHub Actions workflow for documentation deployment

## [1.0.0] - 2025-01-16

### Added
- Initial release of PaperSorter
- RSS/Atom feed support for paper ingestion
- Machine learning-based paper recommendation using XGBoost
- PostgreSQL database with pgvector for embeddings
- Web interface for paper labeling and management
- Slack, Discord, and email notification support
- OAuth authentication (Google, GitHub, ORCID)
- Multi-model support for different research domains
- Semantic search using embedding similarity
- AI-powered summarization and poster generation
- Admin interface for system configuration
- Comprehensive CLI with task automation
- Docker and Kubernetes deployment support

### Changed
- Migrated from SQLite to PostgreSQL for better scalability
- Improved embedding generation with configurable models
- Enhanced web UI with responsive design
- Optimized database queries for large datasets

### Fixed
- Unicode handling in paper titles and abstracts
- Memory leaks in long-running update processes
- Race conditions in parallel feed processing
- Authentication session management issues

## [0.9.0] - 2024-12-01 (Beta)

### Added
- Beta release for testing
- Core functionality implementation
- Basic web interface
- Initial model training capabilities

### Known Issues
- Limited to single-user deployment
- No backup/restore functionality
- Manual configuration required

## [0.5.0] - 2024-10-15 (Alpha)

### Added
- Alpha release for internal testing
- Proof of concept implementation
- Basic RSS feed parsing
- Simple XGBoost model training

---

## Version History Summary

- **1.0.0** - Production-ready release with full feature set
- **0.9.0** - Beta release with core functionality
- **0.5.0** - Alpha release for testing

## Upgrade Notes

### Upgrading from 0.9.x to 1.0.0

1. **Database Migration Required**
   ```bash
   papersorter migrate --from 0.9
   ```

2. **Configuration Changes**
   - `google_oauth` renamed to `oauth.google`
   - New `web.base_url` setting required
   - `embedding_api.dimensions` now optional

3. **Breaking Changes**
   - CLI command structure reorganized
   - API endpoints moved to `/api/v1/` prefix
   - Model file format updated (retrain required)

### Upgrading from 0.5.x to 1.0.0

Complete reinstallation recommended due to extensive changes.

## Support

For upgrade assistance:
- Issues: https://github.com/ChangLabSNU/papersorter/issues