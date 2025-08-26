# PaperSorter Docker Installation Guide

PaperSorter can be easily deployed using Docker and Docker Compose, providing a complete setup with PostgreSQL database, automatic HTTPS, and scheduled tasks.

## Quick Start

### 1. Prerequisites

- Docker Engine 20.10+ and Docker Compose v2
- A domain name (for HTTPS in production)
- API keys for embedding services (OpenAI, Solar, or compatible)

### 2. Installation

```bash
# Clone the repository
git clone https://github.com/ChangLabSNU/papersorter.git
cd papersorter

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys and settings

# Copy Docker config template
cp docker/config.docker.yml config.yml
# Edit config.yml if needed (optional)

# Start all services
docker compose up -d

# Initialize the database
./papersorter-cli init

# Check service status
./papersorter-cli status
```

### 3. Access the Application

- **Local development**: http://localhost:5001
- **Production**: https://your-domain.com (automatic HTTPS via Caddy)

## Architecture

PaperSorter runs as a set of Docker containers:

1. **postgres** - PostgreSQL 16 with pgvector extension for embeddings
2. **web** - Main application server (Gunicorn with gthread worker)
3. **scheduler** - Cron jobs for periodic updates and broadcasts
4. **caddy** - Reverse proxy with automatic HTTPS

## Configuration

### Environment Variables (.env)

Key variables to configure:

```bash
# Database (change password!)
POSTGRES_PASSWORD=secure-password-here

# Flask secret (generate with: python -c "import secrets; print(secrets.token_hex(32))")
FLASK_SECRET_KEY=your-secret-key

# OAuth providers (at least one required)
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret

# Embedding API (required)
OPENAI_API_KEY=your-api-key
# Or custom endpoint:
EMBEDDING_API_URL=https://your-api.com/v1

# Production domain
DOMAIN=papersorter.example.com
ADMIN_EMAIL=admin@example.com
```

### Data Persistence

All data is stored in Docker volumes:

- `papersorter_postgres_data` - Database files
- `papersorter_data` - Application data
  - `/data/models/` - Trained XGBoost models
  - `/data/logs/` - Application and cron logs
  - `/data/posters/` - Generated AI posters
- `papersorter_caddy_data` - SSL certificates

## CLI Usage

The `papersorter-cli` wrapper script provides easy access to all commands:

```bash
# Import initial papers
./papersorter-cli import pubmed --files 20

# Train a model
./papersorter-cli train --name "Initial Model"

# Generate predictions
./papersorter-cli predict --all

# View logs
./papersorter-cli logs

# Open shell in container
./papersorter-cli shell

# Database shell
./papersorter-cli db-shell
```

## Scheduled Tasks

The scheduler container runs these tasks automatically:

- **Update** (every 3 hours): Fetch new papers and generate embeddings
- **Broadcast** (hourly): Send notifications for high-scoring papers
- **Predict** (every 6 hours): Generate predictions for new papers
- **Log cleanup** (daily): Remove logs older than 30 days

To modify the schedule, edit `docker/cron/crontab` and rebuild:

```bash
docker compose build scheduler
docker compose up -d scheduler
```

## Production Deployment

### Using Production Configuration

```bash
# Use both base and production compose files
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### SSL/HTTPS Setup

Caddy automatically obtains and renews SSL certificates from Let's Encrypt:

1. Set your domain in `.env`:
   ```bash
   DOMAIN=papersorter.example.com
   ADMIN_EMAIL=admin@example.com
   ```

2. Ensure ports 80 and 443 are open

3. Start services - certificates will be obtained automatically

### Resource Limits

Production configuration includes resource limits:
- Web: 4GB RAM, 2 CPUs
- Database: 2GB RAM, 2 CPUs
- Scheduler: 2GB RAM, 1 CPU

Adjust in `docker-compose.prod.yml` as needed.

## Maintenance

### Backup

```bash
# Backup database
docker compose exec postgres pg_dump -U papersorter papersorter > backup.sql

# Backup data volume
docker run --rm -v papersorter_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/papersorter-data.tar.gz /data
```

### Restore

```bash
# Restore database
docker compose exec -T postgres psql -U papersorter papersorter < backup.sql

# Restore data volume
docker run --rm -v papersorter_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/papersorter-data.tar.gz -C /
```

### Update

```bash
# Pull latest code
git pull

# Rebuild images
docker compose build --no-cache

# Restart services
docker compose down
docker compose up -d
```

### Monitoring

```bash
# View logs
docker compose logs -f web
docker compose logs -f scheduler

# Check health
curl http://localhost:5001/health

# Monitor resources
docker stats
```

## Troubleshooting

### Services won't start

```bash
# Check logs
docker compose logs

# Verify environment
docker compose config

# Reset everything (WARNING: deletes data)
docker compose down -v
docker compose up -d
```

### Database connection issues

```bash
# Check database is running
docker compose ps postgres

# Test connection
docker compose exec web pg_isready -h postgres

# Check credentials
docker compose exec web env | grep DATABASE_URL
```

### Permission issues

```bash
# Fix ownership (runs as UID 1000)
docker compose exec web chown -R papersorter:papersorter /data
```

### SSL certificate issues

```bash
# Check Caddy logs
docker compose logs caddy

# Manual certificate renewal
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

## Advanced Configuration

### Using External Database

Edit `docker-compose.yml` to remove the postgres service and update `DATABASE_URL`:

```yaml
environment:
  DATABASE_URL: postgresql://user:pass@external-host:5432/papersorter
```

### Custom Nginx/Traefik

Disable Caddy and expose port 5001:

```yaml
services:
  web:
    ports:
      - "5001:5001"
  # Comment out or remove caddy service
```

### Development Mode

For development with hot-reload:

```bash
# Mount source code
docker compose run --rm -v $(pwd)/PaperSorter:/app/PaperSorter web bash

# Inside container
python -m PaperSorter.web.app
```

## Security Notes

1. **Change default passwords** in `.env` before deployment
2. **Secure OAuth credentials** - never commit `.env` to git
3. **Regular updates** - Keep Docker images and dependencies updated
4. **Network isolation** - Database is on internal network only
5. **HTTPS only** - Caddy enforces HTTPS in production

## Support

- GitHub Issues: https://github.com/ChangLabSNU/papersorter/issues
- Documentation: https://github.com/ChangLabSNU/papersorter/docs