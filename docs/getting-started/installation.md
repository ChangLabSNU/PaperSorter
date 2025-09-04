# Installation Guide

This guide will walk you through installing PaperSorter and its dependencies.

## Quick Start with Docker (Recommended)

The easiest way to install PaperSorter is using Docker, which handles all dependencies automatically:

```bash
# Clone the repository
git clone https://github.com/ChangLabSNU/papersorter.git
cd papersorter

# Configure environment
cp .env.example .env
# Edit .env with your API keys and settings

# Start all services
docker-compose up -d

# Initialize database
./papersorter-cli init

# Check status
./papersorter-cli status
```

That's it! PaperSorter is now running at http://localhost:5001


## System Requirements

### For Docker Installation
- **Docker**: Docker Engine 20.10+ and Docker Compose v2
- **RAM**: 4GB minimum, 8GB+ recommended
- **Storage**: 10GB+ for database and models
- **Network**: Stable internet connection

### For Manual Installation
- **CPU**: 2+ cores recommended
- **RAM**: 4GB minimum, 8GB+ recommended
- **Storage**: 10GB+ for database and models
- **Python**: 3.9 or higher
- **PostgreSQL**: 12 or higher with pgvector extension
- **Git**: For cloning the repository

### Operating System Support
- Linux (Ubuntu 20.04+, Debian 11+, RHEL 8+)
- macOS (11.0+)
- Windows (WSL2 recommended)

## Manual Installation

### 1. Clone the Repository

```bash
git clone https://github.com/ChangLabSNU/papersorter.git
cd papersorter
```

### 2. Create Python Virtual Environment

```bash
# Using venv
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Or using conda
conda create -n papersorter python=3.11
conda activate papersorter
```

### 3. Install PaperSorter

```bash
# Install in development mode
pip install -e .

# Or install with all optional dependencies
pip install -e ".[all]"
```

## Database Setup

### PostgreSQL Installation

#### Ubuntu/Debian
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

#### macOS
```bash
brew install postgresql@14
brew services start postgresql@14
```

#### Windows (WSL2)
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
```

### pgvector Extension

PaperSorter requires the pgvector extension for storing embeddings:

```bash
# Ubuntu/Debian
sudo apt install postgresql-14-pgvector

# macOS
brew install pgvector

# From source (all systems)
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

### Database Creation

```sql
-- Connect to PostgreSQL
sudo -u postgres psql

-- Create database and user
CREATE USER papersorter WITH PASSWORD 'your_secure_password';
CREATE DATABASE papersorter OWNER papersorter;

-- Connect to the database
\c papersorter

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE papersorter TO papersorter;
\q
```

## Configuration

### 1. Create Configuration File

```bash
cp config.example.yml config.yml
```

### 2. Edit Configuration

```yaml
# config.yml
db:
  type: postgres
  host: localhost
  port: 5432
  user: papersorter
  database: papersorter
  password: "your_secure_password"

web:
  base_url: "http://localhost:5001"
  flask_secret_key: "generate_with_secrets.token_hex(32)"

# Add your API keys (see configuration guide for details)
embedding_api:
  api_key: "your_openai_api_key"
  model: "text-embedding-3-large"
```

## Dependency Installation

### Core Dependencies

```bash
# Already installed with pip install -e .
# Verify installation:
pip list | grep -E "numpy|pandas|scikit-learn|xgboost"
```

### Optional Dependencies

```bash
# For Gmail integration
pip install google-auth google-auth-oauthlib

# For development
pip install pytest black flake8 mypy

# For documentation
pip install -r docs/requirements.txt
```

## Verification

### Docker Installation

```bash
# Check service status
./papersorter-cli status

# Test database connection
./papersorter-cli test-db

# View logs
./papersorter-cli logs

# Test embedding API
./papersorter-cli test-embedding --text "Test embedding generation"
```

### Manual Installation

```bash
# Verify PaperSorter is installed
papersorter --version

# List available commands
papersorter --help

# Test database connection
papersorter test-db

# Test embedding API
papersorter test-embedding --text "Test embedding generation"
```

## Troubleshooting

### Common Issues

#### PostgreSQL Connection Error
```
psycopg2.OperationalError: could not connect to server
```
**Solution**: Ensure PostgreSQL is running and credentials are correct:
```bash
sudo systemctl status postgresql
psql -U papersorter -d papersorter -h localhost
```

#### pgvector Extension Not Found
```
ERROR: could not open extension control file "vector.control"
```
**Solution**: Install pgvector properly for your PostgreSQL version:
```bash
# Find your PostgreSQL version
psql --version

# Install matching pgvector
sudo apt install postgresql-$(psql --version | awk '{print $3}' | cut -d. -f1)-pgvector
```

#### Python Package Conflicts
```
ERROR: pip's dependency resolver does not currently take into account...
```
**Solution**: Use a clean virtual environment:
```bash
deactivate
rm -rf venv
python -m venv venv --clear
source venv/bin/activate
pip install --upgrade pip
pip install -e .
```

#### Memory Issues with Large Datasets
**Solution**: Adjust PostgreSQL settings in `/etc/postgresql/14/main/postgresql.conf`:
```conf
shared_buffers = 256MB
work_mem = 4MB
maintenance_work_mem = 64MB
```

## Platform-Specific Notes

### Docker Troubleshooting

#### Services won't start
```bash
# Check logs
docker-compose logs

# Verify environment
docker-compose config

# Rebuild if needed
docker-compose build --no-cache
docker-compose up -d
```

#### Permission issues
```bash
# Fix ownership (container runs as UID 1000)
docker-compose exec web chown -R papersorter:papersorter /data
```

#### Database connection issues
```bash
# Check database is running
docker-compose ps postgres

# Test connection
docker-compose exec web pg_isready -h postgres
```

### Production Deployment

For production deployments with Docker:

```bash
# Use production compose file
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```


### Cloud Deployments

- **AWS**: Use RDS for PostgreSQL with pgvector
- **Google Cloud**: Use Cloud SQL with pgvector extension
- **Azure**: Use Azure Database for PostgreSQL with extensions
- **DigitalOcean**: Use Managed PostgreSQL with pgvector

## Next Steps

After successful installation:

1. Continue to [Quick Start Guide](quickstart.md)
2. Configure Feed Sources via web interface
3. Set up [Notifications](../user-guide/notifications.md)
4. Train your [First Model](first-model.md)

## Support

If you encounter issues:
- Check the documentation
- Search [GitHub Issues](https://github.com/ChangLabSNU/papersorter/issues)