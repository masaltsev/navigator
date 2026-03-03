"""
Unit tests for workers/celery_app.py and workers/tasks.py.

Tests Celery configuration and task signatures without requiring Redis
or a running broker.
"""

import pytest

from workers.celery_app import app


class TestCeleryAppConfig:
    def test_app_name(self):
        assert app.main == "harvester"

    def test_serializer_json(self):
        assert app.conf.task_serializer == "json"
        assert app.conf.result_serializer == "json"

    def test_acks_late(self):
        assert app.conf.task_acks_late is True

    def test_prefetch_multiplier(self):
        assert app.conf.worker_prefetch_multiplier == 1

    def test_time_limits(self):
        assert app.conf.task_soft_time_limit == 120
        assert app.conf.task_time_limit == 180

    def test_queues_routing(self):
        routes = app.conf.task_routes
        assert "workers.tasks.crawl_and_enrich" in routes
        assert routes["workers.tasks.crawl_and_enrich"]["queue"] == "harvester"
        assert routes["workers.tasks.process_batch"]["queue"] == "harvester-batch"

    def test_worker_max_tasks(self):
        assert app.conf.worker_max_tasks_per_child == 50

    def test_result_expires(self):
        assert app.conf.result_expires == 86400


class TestTaskRegistration:
    def test_crawl_and_enrich_registered(self):
        from workers.tasks import crawl_and_enrich
        assert crawl_and_enrich.name == "workers.tasks.crawl_and_enrich"

    def test_process_batch_registered(self):
        from workers.tasks import process_batch
        assert process_batch.name == "workers.tasks.process_batch"

    def test_crawl_and_enrich_max_retries(self):
        from workers.tasks import crawl_and_enrich
        assert crawl_and_enrich.max_retries == 2

    def test_crawl_and_enrich_signature(self):
        from workers.tasks import crawl_and_enrich
        sig = crawl_and_enrich.s(
            url="https://example.com",
            source_id="test",
            multi_page=True,
        )
        assert sig is not None
