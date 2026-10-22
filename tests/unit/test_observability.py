"""Unit tests for observability subsystem."""
import asyncio
import json
import pytest
from pathlib import Path
from aura.models import AuditEvent, EventLevel
from aura.observability import EventBus, JSONLLogger, MetricsCollector


@pytest.mark.asyncio
async def test_event_bus_subscribe_and_emit():
    bus = EventBus()
    received = []

    def handler(ev):
        received.append(ev)

    bus.subscribe("aura.test", handler)
    ev = AuditEvent(event_type="aura.test")

    await bus.emit(ev)
    assert len(received) == 1
    assert received[0].event_type == "aura.test"


@pytest.mark.asyncio
async def test_event_bus_subscribe_all():
    bus = EventBus()
    received = []
    bus.subscribe_all(lambda ev: received.append(ev))
    ev = AuditEvent(event_type="aura.anything")
    await bus.emit(ev)
    assert len(received) == 1


@pytest.mark.asyncio
async def test_jsonl_logger_writes(tmp_path):
    logger = JSONLLogger(tmp_path)
    ev = AuditEvent(event_type="aura.test.write", run_id="run_test")
    await logger.log(ev)
    log_file = tmp_path / "aura-events.jsonl"
    assert log_file.exists()
    lines = log_file.read_text().strip().split("\n")
    assert len(lines) >= 1
    data = json.loads(lines[-1])
    assert data["event_type"] == "aura.test.write"
    assert data["run_id"] == "run_test"


@pytest.mark.asyncio
async def test_jsonl_logger_read_events(tmp_path):
    logger = JSONLLogger(tmp_path)
    for i in range(5):
        ev = AuditEvent(event_type=f"aura.test.{i}", level=EventLevel.INFO)
        await logger.log(ev)
    events = await logger.read_events(limit=10)
    assert len(events) == 5


def test_metrics_on_run_started():
    m = MetricsCollector()
    ev = AuditEvent(event_type="aura.run.started", run_id="run_001")
    m.on_audit_event(ev)
    assert m.active_runs == 1


def test_metrics_on_run_completed():
    m = MetricsCollector()
    ev_start = AuditEvent(event_type="aura.run.started", run_id="run_001")
    ev_complete = AuditEvent(event_type="aura.run.completed", run_id="run_001")
    m.on_audit_event(ev_start)
    m.on_audit_event(ev_complete)
    assert m.active_runs == 0
    assert m.completed_runs == 1


def test_metrics_action_blocked():
    m = MetricsCollector()
    ev = AuditEvent(event_type="aura.action.blocked", request_id="req_001")
    m.on_audit_event(ev)
    assert m.blocked_actions == 1


def test_metrics_jev_sparkline_empty():
    m = MetricsCollector()
    sparkline = m.jev_sparkline
    assert len(sparkline) > 0


def test_metrics_jev_sparkline_with_data():
    m = MetricsCollector()
    for lat in [10, 50, 200, 30, 150, 80]:
        m.record_jev_latency(lat)
    sparkline = m.jev_sparkline
    assert len(sparkline) > 0
