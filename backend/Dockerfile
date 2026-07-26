# Stage 1: Install Python dependencies
# NOTE: Pin base image by SHA256 digest for reproducibility.
# Update digest periodically via Dependabot or manually from:
#   docker pull python:3.11-slim && docker inspect --format='{{index .RepoDigests 0}}' python:3.11-slim
FROM python:3.11-slim@sha256:8f64a67710a45efd04ef8a5de41cadd839a9fa68a9cde8093fcfa30f498cd245 AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy source needed for hatchling to build the wheel
COPY pyproject.toml ./
COPY src/ ./src/

# For production, generate a locked requirements.txt with:
#   pip-compile --generate-hashes pyproject.toml -o requirements.txt
# Then install with: pip install --require-hashes -r requirements.txt
RUN pip install --no-cache-dir --prefix=/install .

# Stage 2: Runtime
FROM python:3.11-slim@sha256:8f64a67710a45efd04ef8a5de41cadd839a9fa68a9cde8093fcfa30f498cd245

LABEL org.opencontainers.image.source="https://github.com/cl-xy/ai-investment-analyst"
LABEL org.opencontainers.image.description="Multi-agent investment analysis API"

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=random
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PATH="/install/bin:$PATH"
ENV PYTHONPATH="/install/lib/python3.11/site-packages:/app"

# Runtime-only system deps (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages
COPY --from=builder /install /install

# Copy application code
COPY src/ ./src/

# Create data directory for SQLite (portfolio + checkpoints)
RUN mkdir -p data

# Non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
  CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
