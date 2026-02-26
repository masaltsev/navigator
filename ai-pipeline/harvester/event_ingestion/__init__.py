"""
Универсальный пайплайн приёма мероприятий (Event Ingestion Pipeline).

Любой источник сырых данных (агрегаторы, сайты организаций, соцсети) приводит
данные к каноническому формату RawEventInput. Пайплайн выдаёт единую структуру
для отправки в Core API.

Использование:
    from event_ingestion import RawEventInput, run_event_ingestion_pipeline
    raw = RawEventInput(source_reference="...", title="...", raw_text="...", ...)
    payload = await run_event_ingestion_pipeline(raw, organizer_id="...")
    await core.import_event(payload)
"""

from event_ingestion.adapters import event_candidate_to_raw, silverage_event_to_raw
from event_ingestion.core_payload import build_core_event_payload
from event_ingestion.models import RawEventInput
from event_ingestion.pipeline import run_event_ingestion_pipeline

__all__ = [
    "RawEventInput",
    "run_event_ingestion_pipeline",
    "build_core_event_payload",
    "event_candidate_to_raw",
    "silverage_event_to_raw",
]
