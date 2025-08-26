# PaperSorter Docker Image
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt pyproject.toml setup.py ./
COPY PaperSorter/__version__.py ./PaperSorter/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn[gthread]

# Copy the application code
COPY . .

# Install PaperSorter package
RUN pip install --no-cache-dir -e .

# Create non-root user
RUN useradd -m -u 1000 papersorter && \
    mkdir -p /data/logs /data/models /data/posters && \
    chown -R papersorter:papersorter /app /data

# Copy entrypoint script
COPY docker/scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Switch to non-root user
USER papersorter

# Set environment variables
ENV PAPERSORTER_DATADIR=/data \
    PAPERSORTER_CONFIG=/app/config.yml \
    PYTHONUNBUFFERED=1

# Expose port
EXPOSE 5001

# Use entrypoint for database wait
ENTRYPOINT ["/entrypoint.sh"]

# Default command (can be overridden)
CMD ["gunicorn", \
     "--worker-class", "gthread", \
     "--workers", "1", \
     "--threads", "4", \
     "--bind", "0.0.0.0:5001", \
     "--access-logfile", "/data/logs/access.log", \
     "--error-logfile", "/data/logs/error.log", \
     "--log-level", "info", \
     "--timeout", "120", \
     "docker.scripts.wsgi:app"]