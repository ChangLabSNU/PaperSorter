FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev postgresql-client curl ca-certificates openssl gettext \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir uwsgi

COPY . .
RUN pip install --no-cache-dir .
RUN addgroup --system app && adduser --system --ingroup app app && \
    chown -R app:app /app
USER app

RUN chmod +x entrypoint.sh

USER app

EXPOSE 5001

# Use entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]