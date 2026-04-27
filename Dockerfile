###############################################################################
# Dockerfile – Glacias API
#
# Single image used for three services (api, worker, migrate).
# The entry-point command is overridden per-service in docker-compose.yml.
###############################################################################

FROM python:3.12-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (leverages Docker layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose API port (informational)
EXPOSE 8000

# Default command: start the API server.
# Override in docker-compose.yml for worker / migrate services.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
