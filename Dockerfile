# Multi-stage build for the trading agent system
FROM python:3.11-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY agent_system/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# Install additional dependencies for cloud deployment
RUN pip install --no-cache-dir --break-system-packages \
    psycopg2-binary \
    redis \
    prometheus-client \
    gunicorn \
    uvicorn

# Copy application code
COPY agent_system/ ./agent_system/
COPY bridge/ ./bridge/
COPY src/ ./src/
COPY ui/ ./ui/

# Create non-root user
RUN useradd -m -u 1000 trader && chown -R trader:trader /app
USER trader

# Expose ports
EXPOSE 8080 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default command
CMD ["python", "agent_system/main.py"]