# syntax=docker/dockerfile:1

# Multi-stage build for optimal image size and security
# Stage 1: Build stage
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime stage
FROM python:3.11-slim

# Add metadata labels
LABEL maintainer="Draken Team"
LABEL description="AutoGen Studio containerized application"
LABEL version="1.0"

# Create non-root user for security
RUN groupadd -r appuser && \
    useradd -r -g appuser -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # AutoGen Studio specific
    AUTOGENSTUDIO_APPDIR=/app/.autogenstudio

# Create necessary directories and set permissions
RUN mkdir -p /app/.autogenstudio && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port (AutoGen Studio default is 8081)
EXPOSE 8081

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8081').read()" || exit 1

# Run AutoGen Studio
CMD ["autogenstudio", "ui", "--host", "0.0.0.0", "--port", "8081"]
