# Deployment Guide

This guide covers different methods for deploying PaperSorter in production.

## Systemd Service Deployment

### Prerequisites

1. PaperSorter installed in a Python environment
2. A valid `config.yml` configuration file
3. Root access for systemd configuration

### Installation Steps

#### 1. Create a dedicated user (optional but recommended)

```bash
sudo useradd -r -m -s /bin/bash papersorter
```

#### 2. Set up the application directory

```bash
# Clone or copy your PaperSorter installation
sudo -u papersorter git clone <repository> /home/papersorter/papersorter
cd /home/papersorter/papersorter

# Install PaperSorter in a virtual environment
sudo -u papersorter python -m venv venv
sudo -u papersorter venv/bin/pip install -e .
```

#### 3. Create log directory

```bash
sudo mkdir -p /var/log/papersorter
sudo chown papersorter:papersorter /var/log/papersorter
```

#### 4. Install the systemd service

```bash
# Copy and customize the service file
sudo cp examples/papersorter.service /etc/systemd/system/
sudo nano /etc/systemd/system/papersorter.service
```

Edit the service file to match your setup:
- Update the `User` and `Group` to match your user
- Update `WorkingDirectory` to your PaperSorter installation path
- Update `PAPER_SORTER_CONFIG` to point to your config.yml file
- Update the `ExecStart` path to your Python environment's gunicorn

#### 5. Enable and start the service

```bash
# Reload systemd configuration
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable papersorter

# Start the service
sudo systemctl start papersorter

# Check service status
sudo systemctl status papersorter
```

### Service Management

#### Common commands

```bash
# Start the service
sudo systemctl start papersorter

# Stop the service
sudo systemctl stop papersorter

# Restart the service
sudo systemctl restart papersorter

# Check service status
sudo systemctl status papersorter

# View service logs
sudo journalctl -u papersorter -f

# View application logs
sudo tail -f /var/log/papersorter/error.log
sudo tail -f /var/log/papersorter/access.log
```

### Configuration Options

#### Environment Variables

The service supports these environment variables:

- `PAPER_SORTER_CONFIG`: Path to the configuration file (required)
- `PAPER_SORTER_SKIP_AUTH`: Email address to skip authentication (development only)

#### Gunicorn Options

You can adjust the gunicorn options in the service file:

- `--workers`: Number of worker processes (default: 2)
- `--threads`: Number of threads per worker (default: 4)
- `--bind`: Address and port to bind (default: 0.0.0.0:8000)
- `--timeout`: Worker timeout in seconds (default: 120)

## Nginx Reverse Proxy

For production deployments, use Nginx as a reverse proxy:

### Basic Configuration

Create `/etc/nginx/sites-available/papersorter`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Increase timeout for long-running requests (like poster generation)
    proxy_read_timeout 300s;
    proxy_connect_timeout 75s;
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/papersorter /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### HTTPS with Let's Encrypt

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal is configured automatically
```

## Docker Deployment

### Using Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  papersorter:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./config.yml:/app/config.yml:ro
      - ./models:/app/models
    environment:
      - PAPER_SORTER_CONFIG=/app/config.yml
    restart: unless-stopped

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: papersorter
      POSTGRES_USER: papersorter
      POSTGRES_PASSWORD: your_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  postgres_data:
```

Start the services:

```bash
docker-compose up -d
```

## Cron Jobs Setup

Set up periodic tasks for fetching and processing articles:

```bash
# Edit crontab
crontab -e

# Add these lines:
# Update feeds every 4 hours
0 */4 * * * /path/to/venv/bin/papersorter update --config /path/to/config.yml

# Send broadcasts every day at 9 AM
0 9 * * * /path/to/venv/bin/papersorter broadcast --config /path/to/config.yml

# Generate predictions once a day
0 2 * * * /path/to/venv/bin/papersorter predict --config /path/to/config.yml
```

## Troubleshooting

### Service fails to start

1. Check the service logs:
   ```bash
   sudo journalctl -u papersorter -n 50
   ```

2. Verify the configuration file path is correct:
   ```bash
   sudo -u papersorter test -f /path/to/config.yml && echo "File exists"
   ```

3. Test the application manually:
   ```bash
   sudo -u papersorter PAPER_SORTER_CONFIG=/path/to/config.yml \
       /path/to/venv/bin/gunicorn PaperSorter.web.wsgi:app
   ```

### Permission errors

Ensure the service user has read access to:
- The application directory
- The configuration file
- The Python virtual environment

And write access to:
- The log directory (/var/log/papersorter)
- The working directory (for temporary files)

### Database connection errors

1. Verify database credentials in config.yml
2. Ensure the database is accessible from the service
3. Check if the database user has necessary permissions
4. For PostgreSQL with pgvector, ensure the extension is installed:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

### WSGI import errors

If you encounter `TypeError: expected str, bytes or os.PathLike object, not dict`:
- Ensure you're using `PaperSorter.web.wsgi:app` in your gunicorn command
- Not `PaperSorter.web:create_app` or `PaperSorter.web.app:create_app`

## Performance Tuning

### Gunicorn Workers

Calculate optimal workers:
```python
workers = (2 * CPU_cores) + 1
```

For a 4-core system, use 9 workers.

### PostgreSQL Connection Pooling

Add to your config.yml:
```yaml
db:
  pool_size: 20
  max_overflow: 40
  pool_timeout: 30
  pool_recycle: 3600
```

### Redis Caching (Optional)

For high-traffic deployments, consider adding Redis for caching:

```yaml
redis:
  host: localhost
  port: 6379
  db: 0
```