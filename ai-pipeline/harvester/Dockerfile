FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN pip install --upgrade pip && \
    pip install '.[dev]'

RUN playwright install --with-deps chromium

COPY . .

# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

FROM base AS worker
CMD ["celery", "-A", "workers.celery_app", "worker", \
     "--loglevel=info", "--concurrency=2", \
     "-Q", "harvester,harvester-batch"]

FROM base AS cli
ENTRYPOINT ["python", "-m", "scripts.run_single_url"]

FROM base AS test
CMD ["pytest", "-v", "--tb=short"]
