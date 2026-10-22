"""AURA observability — event bus, JSONL logging, metrics, run repository."""
from __future__ import annotations
import asyncio
import json
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from aura.models import AuditEvent, EventLevel, RunRecord, RunStatus


# ── Event Bus ─────────────────────────────────────────────────────────────────

class EventBus:
    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._any_subscribers: List[Callable] = []

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._subscribers[event_type].append(handler)

    def subscribe_all(self, handler: Callable) -> None:
        self._any_subscribers.append(handler)

    def unsubscribe_all_from(self, handler: Callable) -> None:
        self._any_subscribers = [h for h in self._any_subscribers if h != handler]

    async def emit(self, event: AuditEvent) -> None:
        handlers = self._subscribers.get(event.event_type, []) + self._any_subscribers
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception:
                pass


_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


# ── JSONL Logger ──────────────────────────────────────────────────────────────

class JSONLLogger:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._events_file = log_dir / "aura-events.jsonl"
        self._errors_file = log_dir / "aura-errors.jsonl"
        self._lock = asyncio.Lock()

    async def log(self, event: AuditEvent) -> None:
        line = event.to_jsonl() + "\n"
        async with self._lock:
            try:
                with open(self._events_file, "a", encoding="utf-8") as f:
                    f.write(line)
                if event.level in (EventLevel.ERROR, EventLevel.CRITICAL):
                    with open(self._errors_file, "a", encoding="utf-8") as f:
                        f.write(line)
            except Exception:
                pass

    async def read_events(
        self,
        limit: int = 200,
        level_filter: Optional[str] = None,
        event_type_filter: Optional[str] = None,
        run_id_filter: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        if not self._events_file.exists():
            return results
        try:
            with open(self._events_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if level_filter and obj.get("level") != level_filter:
                    continue
                if event_type_filter and event_type_filter not in obj.get("event_type", ""):
                    continue
                if run_id_filter and obj.get("run_id") != run_id_filter:
                    continue
                if search and search.lower() not in line.lower():
                    continue
                results.append(obj)
                if len(results) >= limit:
                    break
        except Exception:
            pass
        return results


# ── Metrics ───────────────────────────────────────────────────────────────────

class MetricsCollector:
    def __init__(self) -> None:
        self.active_runs: int = 0
        self.completed_runs: int = 0
        self.failed_runs: int = 0
        self.cancelled_runs: int = 0
        self.total_tool_calls: int = 0
        self.allowed_actions: int = 0
        self.blocked_actions: int = 0
        self.pending_approvals: int = 0
        self.total_jev_assessments: int = 0
        self.jev_failures: int = 0
        self.jev_timeouts: int = 0
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self._jev_latencies: deque = deque(maxlen=100)
        self._run_durations: deque = deque(maxlen=100)
        self._recent_events: deque = deque(maxlen=50)
        self._risk_distribution: Dict[str, int] = defaultdict(int)
        self.jev_connected: bool = False
        self.agent_connected: bool = False
        self.started_at: float = time.monotonic()

    def record_jev_latency(self, ms: float) -> None:
        self._jev_latencies.append(ms)

    def record_run_duration(self, ms: float) -> None:
        self._run_durations.append(ms)

    def record_risk(self, risk_level: str) -> None:
        self._risk_distribution[risk_level] += 1

    def add_recent_event(self, summary: str) -> None:
        self._recent_events.appendleft({
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "summary": summary,
        })

    @property
    def jev_p50_ms(self) -> Optional[float]:
        if not self._jev_latencies:
            return None
        s = sorted(self._jev_latencies)
        return s[len(s) // 2]

    @property
    def jev_p95_ms(self) -> Optional[float]:
        if len(self._jev_latencies) < 5:
            return None
        s = sorted(self._jev_latencies)
        return s[int(len(s) * 0.95)]

    @property
    def jev_sparkline(self) -> str:
        if not self._jev_latencies:
            return "─" * 12
        lats = list(self._jev_latencies)[-12:]
        if not lats:
            return "─" * 12
        mn, mx = min(lats), max(lats)
        chars = "▁▂▃▄▅▆▇█"
        result = ""
        for v in lats:
            if mx == mn:
                idx = 3
            else:
                idx = int((v - mn) / (mx - mn) * 7)
            result += chars[idx]
        return result

    @property
    def recent_events(self) -> List[Dict]:
        return list(self._recent_events)

    @property
    def risk_distribution(self) -> Dict[str, int]:
        return dict(self._risk_distribution)

    def on_audit_event(self, event: AuditEvent) -> None:
        et = event.event_type
        if et == "aura.run.started":
            self.active_runs += 1
            self.add_recent_event(f"{event.run_id}  RUN_STARTED")
        elif et == "aura.run.completed":
            self.active_runs = max(0, self.active_runs - 1)
            self.completed_runs += 1
            if event.execution and event.execution.get("duration_ms"):
                self.record_run_duration(event.execution["duration_ms"])
            self.add_recent_event(f"{event.run_id}  RUN_COMPLETED")
        elif et == "aura.run.failed":
            self.active_runs = max(0, self.active_runs - 1)
            self.failed_runs += 1
            self.add_recent_event(f"{event.run_id}  RUN_FAILED")
        elif et == "aura.action.proposed":
            self.total_tool_calls += 1
        elif et == "aura.action.executed":
            self.allowed_actions += 1
        elif et == "aura.action.blocked":
            self.blocked_actions += 1
            self.add_recent_event(f"{event.request_id}  POLICY_BLOCK")
        elif et == "aura.jev.assessment.completed":
            self.total_jev_assessments += 1
            if event.jev:
                lat = event.jev.get("latency_ms")
                if lat:
                    self.record_jev_latency(float(lat))
                rl = event.jev.get("risk_level", "unknown")
                self.record_risk(rl)
        elif et == "aura.jev.assessment.failed":
            self.jev_failures += 1
        elif et == "aura.approval.requested":
            self.pending_approvals += 1
        elif et == "aura.approval.resolved":
            self.pending_approvals = max(0, self.pending_approvals - 1)
        elif et == "aura.agent.token_usage":
            if event.metadata:
                self.input_tokens += event.metadata.get("input_tokens", 0) or 0
                self.output_tokens += event.metadata.get("output_tokens", 0) or 0


_metrics: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


# ── Run Repository ────────────────────────────────────────────────────────────

class RunRepository:
    def __init__(self) -> None:
        self._runs: Dict[str, RunRecord] = {}
        self._lock = asyncio.Lock()

    async def save(self, run: RunRecord) -> None:
        async with self._lock:
            self._runs[run.run_id] = run

    async def get(self, run_id: str) -> Optional[RunRecord]:
        async with self._lock:
            return self._runs.get(run_id)

    async def list_runs(self, limit: int = 50) -> List[RunRecord]:
        async with self._lock:
            runs = sorted(self._runs.values(), key=lambda r: r.started_at, reverse=True)
            return runs[:limit]

    async def update_status(self, run_id: str, status: RunStatus, error: Optional[str] = None) -> None:
        async with self._lock:
            run = self._runs.get(run_id)
            if run:
                run.status = status
                if error:
                    run.error = error
                if status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.TIMEOUT):
                    run.completed_at = datetime.now(timezone.utc)
                    if run.started_at:
                        delta = (run.completed_at - run.started_at).total_seconds() * 1000
                        run.duration_ms = delta


_run_repo: Optional[RunRepository] = None


def get_run_repo() -> RunRepository:
    global _run_repo
    if _run_repo is None:
        _run_repo = RunRepository()
    return _run_repo
