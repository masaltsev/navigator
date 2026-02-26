"""
Celery application for Harvester.

Broker and backend: Redis (configured via REDIS_URL env var).

Usage:
    # Start worker (from ai-pipeline/harvester/)
    celery -A workers.celery_app worker --loglevel=info --concurrency=4

    # Monitor
    celery -A workers.celery_app inspect active
"""

import sys
from pathlib import Path

from celery import Celery

_harvester_root = Path(__file__).resolve().parent.parent
if str(_harvester_root) not in sys.path:
    sys.path.insert(0, str(_harvester_root))

_env_file = _harvester_root / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)

from config.settings import get_settings

REDIS_URL = get_settings().redis_url

app = Celery(
    "harvester",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["workers.tasks"],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    task_acks_late=True,
    worker_prefetch_multiplier=1,

    task_soft_time_limit=120,
    task_time_limit=180,

    task_default_queue="harvester",
    task_default_exchange="harvester",
    task_default_routing_key="harvester",

    task_routes={
        "workers.tasks.crawl_and_enrich": {"queue": "harvester"},
        "workers.tasks.harvest_events": {"queue": "harvester"},
        "workers.tasks.process_batch": {"queue": "harvester-batch"},
    },

    result_expires=86400,  # 24h
    worker_max_tasks_per_child=50,
)
