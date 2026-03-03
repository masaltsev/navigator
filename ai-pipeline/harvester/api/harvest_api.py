"""
HTTP API for Harvester — integration point for Laravel Scheduler.

Endpoints:
  POST /harvest/run          — trigger batch processing of source URLs
  POST /harvest/events       — trigger event harvesting for source URLs
  GET  /harvest/status/{id}  — check status of a batch/task
  GET  /health               — health check

This server is a thin wrapper that dispatches work to Celery tasks.
Laravel Scheduler calls POST /harvest/run with a list of source_ids/URLs
on a periodic basis (e.g. daily for due sources).

Run:
    cd ai-pipeline/harvester
    uvicorn api.harvest_api:app --host 0.0.0.0 --port 8100

Or via docker-compose (add to services).
"""

import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

_harvester_root = Path(__file__).resolve().parent.parent
if str(_harvester_root) not in sys.path:
    sys.path.insert(0, str(_harvester_root))

_env_file = _harvester_root / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)

import structlog

from config.logging import configure_logging
from config.settings import get_settings

configure_logging()
logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Navigator Harvester API",
    version="1.0.0",
    description="Trigger and monitor harvest jobs from Laravel Scheduler",
)

API_TOKEN = get_settings().harvester_api_token


class HarvestRunRequest(BaseModel):
    """Request body for POST /harvest/run."""
    sources: list[dict] = Field(
        description="List of sources: [{url, source_id, source_item_id, existing_entity_id}]"
    )
    multi_page: bool = True
    enrich_geo: bool = True
    send_to_core: bool = True


class EventHarvestRequest(BaseModel):
    """Request body for POST /harvest/events."""
    urls: list[str] = Field(description="List of organization base URLs")
    max_event_pages: int = 3
    max_events_per_page: int = 10
    send_to_core: bool = True


class HarvestResponse(BaseModel):
    status: str
    group_id: Optional[str] = None
    task_ids: list[str] = Field(default_factory=list)
    tasks_count: int = 0
    message: str = ""


def _check_auth(authorization: Optional[str]) -> None:
    """Validate Authorization header (Bearer <token> or plain token)."""
    token = (authorization or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if API_TOKEN and token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid API token")


@app.post("/harvest/run", response_model=HarvestResponse)
async def harvest_run(
    request: HarvestRunRequest,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    """
    Trigger batch harvest: dispatch Celery tasks for each source URL.

    Called by Laravel Scheduler with sources due for crawling.
    """
    _check_auth(authorization)

    from workers.tasks import crawl_and_enrich

    if not request.sources:
        return HarvestResponse(status="empty", message="No sources provided")

    from celery import group

    tasks = []
    for src in request.sources:
        url = src.get("url")
        if not url:
            continue
        tasks.append(
            crawl_and_enrich.s(
                url=url,
                source_id=src.get("source_id", "api"),
                source_item_id=src.get("source_item_id"),
                existing_entity_id=src.get("existing_entity_id"),
                multi_page=request.multi_page,
                enrich_geo=request.enrich_geo,
                send_to_core=request.send_to_core,
            )
        )

    if not tasks:
        return HarvestResponse(status="empty", message="No valid URLs in sources")

    job = group(tasks)
    result = job.apply_async()

    logger.info(
        "harvest_api_dispatched",
        tasks_count=len(tasks),
        group_id=str(result.id),
    )

    return HarvestResponse(
        status="dispatched",
        group_id=str(result.id),
        tasks_count=len(tasks),
        message=f"Dispatched {len(tasks)} tasks to Celery",
    )


@app.post("/harvest/events", response_model=HarvestResponse)
async def harvest_events_endpoint(
    request: EventHarvestRequest,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    """
    Trigger event harvesting for organization URLs.

    Discovers /news, /afisha pages and classifies events.
    """
    _check_auth(authorization)

    from workers.tasks import harvest_events

    if not request.urls:
        return HarvestResponse(status="empty", message="No URLs provided")

    task_ids: list[str] = []
    for url in request.urls:
        result = harvest_events.delay(
            url=url,
            max_event_pages=request.max_event_pages,
            max_events_per_page=request.max_events_per_page,
            send_to_core=request.send_to_core,
        )
        task_ids.append(str(result.id))

    logger.info(
        "harvest_events_dispatched",
        tasks_count=len(task_ids),
    )

    return HarvestResponse(
        status="dispatched",
        task_ids=task_ids,
        tasks_count=len(task_ids),
        message=f"Dispatched {len(task_ids)} event harvest tasks",
    )


@app.get("/harvest/status/{task_id}")
async def harvest_status(
    task_id: str,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    """
    Check status of a Celery task or group.

    Returns: state, result (if complete), metadata.
    """
    _check_auth(authorization)

    from celery.result import AsyncResult
    from workers.celery_app import app as celery_app

    result = AsyncResult(task_id, app=celery_app)

    response = {
        "task_id": task_id,
        "state": result.state,
        "ready": result.ready(),
    }

    if result.ready():
        try:
            response["result"] = result.result
        except Exception:
            response["result"] = str(result.result)

    if result.failed():
        response["error"] = str(result.result)

    return response


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "harvester",
        "version": "1.0.0",
    }
