"""Durable, privacy-conscious storage for task execution records."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from uthyagent.core.domain import (
    ActionOutcome,
    ActionType,
    AgentAction,
    RunMode,
    SafetyDecision,
    StepRecord,
    TaskRecord,
    TaskStatus,
)

SCHEMA_VERSION = 1
_REDACTED = "[REDACTED]"
_SECRET_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|auth(?:orization)?|bearer|bot[_-]?token|token|password|passwd|secret|private[_-]?key|client[_-]?secret|credential|cookie|set-cookie|x-api-key)",
    re.I,
)
_SECRET_VALUE = re.compile(
    r"(?i)(\b(?:sk|pk|rk)[_-][a-z0-9_-]{12,}\b|\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|[0-9]{6,}:[A-Za-z0-9_-]{20,})\b|\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{12,})"
)
_INLINE_SECRET = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|auth(?:orization)?|bearer|bot[_-]?token|password|passwd|secret|private[_-]?key|client[_-]?secret|credential|cookie)\b\s*[:=]\s*)([^\s,;]+)"
)


def default_path() -> Path:
    """Return the user-local XDG database path (without creating it)."""
    root = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(root) / "uthyagent" / "tasks.sqlite3"


def _redact(value: Any, key: str | None = None) -> Any:
    if key and _SECRET_KEY.search(key):
        return _REDACTED
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, tuple):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        value = _INLINE_SECRET.sub(lambda match: match.group(1) + _REDACTED, value)
        return _SECRET_VALUE.sub(_REDACTED, value)
    return value


def _json(value: Any) -> str:
    return json.dumps(_redact(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _action_dict(action: AgentAction) -> dict[str, Any]:
    return {
        "type": action.type.value,
        "rationale": action.rationale,
        "target": action.target,
        "text": action.text,
        "key": action.key,
        "x": action.x,
        "y": action.y,
        "button": action.button,
        "scroll_x": action.scroll_x,
        "scroll_y": action.scroll_y,
        "wait_ms": action.wait_ms,
        "expected_result": action.expected_result,
    }


def _step_dict(step: StepRecord) -> dict[str, Any]:
    outcome = (
        None
        if step.outcome is None
        else {
            "success": step.outcome.success,
            "message": step.outcome.message,
            "started_at": step.outcome.started_at,
            "finished_at": step.outcome.finished_at,
            "evidence": step.outcome.evidence,
        }
    )
    return {
        "index": step.index,
        "action": _action_dict(step.action),
        "decision": {
            "allowed": step.decision.allowed,
            "reason": step.decision.reason,
            "requires_confirmation": step.decision.requires_confirmation,
        },
        "outcome": outcome,
        "observed_at": step.observed_at,
    }


def _from_step(data: dict[str, Any]) -> StepRecord:
    a = data["action"]
    action = AgentAction(
        type=ActionType(a["type"]),
        rationale=a.get("rationale", ""),
        target=a.get("target"),
        text=a.get("text"),
        key=a.get("key"),
        x=a.get("x"),
        y=a.get("y"),
        button=a.get("button", "left"),
        scroll_x=a.get("scroll_x", 0),
        scroll_y=a.get("scroll_y", 0),
        wait_ms=a.get("wait_ms", 500),
        expected_result=a.get("expected_result"),
    )
    d = data["decision"]
    decision = SafetyDecision(
        bool(d["allowed"]), d["reason"], bool(d.get("requires_confirmation", False))
    )
    o = data.get("outcome")
    outcome = (
        None
        if o is None
        else ActionOutcome(
            bool(o["success"]),
            o["message"],
            o["started_at"],
            o["finished_at"],
            o.get("evidence", {}),
        )
    )
    return StepRecord(int(data["index"]), action, decision, outcome, data["observed_at"])


class TaskStore:
    """SQLite-backed task records. Each operation uses a fresh, short-lived connection."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        if path is not None and os.fspath(path) == ":memory:":
            raise ValueError("TaskStore requires a persistent SQLite file path")
        self.path = Path(path) if path is not None else default_path()
        self._lock = threading.RLock()
        if self.path != Path(":memory:"):
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self._connection() as conn:
            self._migrate(conn)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def _connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self._connection()
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        row = conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()
        version = int(row[0]) if row else 0
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"unsupported task store schema version {version}")
        if version < 1:
            conn.execute("""CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY, request TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, active_application TEXT,
                result TEXT, error TEXT, retry_count INTEGER NOT NULL, steps_json TEXT NOT NULL)""")
            conn.execute("CREATE INDEX idx_tasks_updated ON tasks(updated_at)")
            conn.execute("CREATE INDEX idx_tasks_status ON tasks(status)")
            conn.execute("INSERT OR REPLACE INTO schema_meta(key,value) VALUES('version','1')")

    def save(self, task: TaskRecord) -> TaskRecord:
        if not task.task_id or not isinstance(task.retry_count, int) or task.retry_count < 0:
            raise ValueError("task_id and non-negative integer retry_count are required")
        if not isinstance(task.mode, RunMode) or not isinstance(task.status, TaskStatus):
            raise ValueError("mode and status must be domain enums")
        steps = [_step_dict(s) for s in task.steps]
        with self._transaction() as conn:
            conn.execute(
                """INSERT INTO tasks(task_id,request,mode,status,created_at,updated_at,active_application,result,error,retry_count,steps_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET request=excluded.request,mode=excluded.mode,status=excluded.status,
                created_at=excluded.created_at,updated_at=excluded.updated_at,active_application=excluded.active_application,result=excluded.result,
                error=excluded.error,retry_count=excluded.retry_count,steps_json=excluded.steps_json""",
                (
                    task.task_id,
                    _redact(task.request),
                    task.mode.value,
                    task.status.value,
                    task.created_at,
                    task.updated_at,
                    task.active_application,
                    _redact(task.result),
                    _redact(task.error),
                    task.retry_count,
                    _json(steps),
                ),
            )
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return self._record(row) if row else None

    def list(
        self, *, status: TaskStatus | str | None = None, limit: int = 100, offset: int = 0
    ) -> list[TaskRecord]:
        if (
            not isinstance(limit, int)
            or not 0 < limit <= 10000
            or not isinstance(offset, int)
            or offset < 0
        ):
            raise ValueError("limit must be 1..10000 and offset non-negative")
        params: list[Any] = []
        sql = "SELECT * FROM tasks"
        if status is not None:
            value = status.value if isinstance(status, TaskStatus) else status
            if value not in {s.value for s in TaskStatus}:
                raise ValueError("invalid status")
            sql += " WHERE status=?"
            params.append(value)
        sql += " ORDER BY updated_at DESC, task_id LIMIT ? OFFSET ?"
        params.extend((limit, offset))
        with self._connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._record(row) for row in rows]

    def search(self, query: str, *, limit: int = 100) -> list[TaskRecord]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be non-empty")
        if not isinstance(limit, int) or not 0 < limit <= 10000:
            raise ValueError("invalid limit")
        pattern = f"%{query}%"
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE task_id LIKE ? OR request LIKE ? OR result LIKE ? OR error LIKE ? ORDER BY updated_at DESC LIMIT ?",
                (pattern, pattern, pattern, pattern, limit),
            ).fetchall()
        return [self._record(row) for row in rows]

    def delete(self, task_id: str) -> bool:
        with self._transaction() as conn:
            return conn.execute("DELETE FROM tasks WHERE task_id=?", (task_id,)).rowcount > 0

    def purge(self, *, older_than: str, statuses: Iterable[TaskStatus | str] | None = None) -> int:
        """Delete records with updated_at before an ISO timestamp, optionally by status."""
        sql, params = "DELETE FROM tasks WHERE updated_at < ?", [older_than]
        if statuses is not None:
            vals = [s.value if isinstance(s, TaskStatus) else s for s in statuses]
            if not vals or any(v not in {s.value for s in TaskStatus} for v in vals):
                raise ValueError("invalid statuses")
            sql += " AND status IN (" + ",".join("?" for _ in vals) + ")"
            params.extend(vals)
        with self._transaction() as conn:
            return conn.execute(sql, params).rowcount

    def export(self, task_id: str | None = None) -> str:
        records = [self.get(task_id)] if task_id is not None else self.list(limit=10000)
        records = [r for r in records if r is not None]
        return json.dumps(
            [self._public_record(r) for r in records], ensure_ascii=False, sort_keys=True, indent=2
        )

    @staticmethod
    def _record(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            task_id=row["task_id"],
            request=row["request"],
            mode=RunMode(row["mode"]),
            status=TaskStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            active_application=row["active_application"],
            steps=[_from_step(x) for x in json.loads(row["steps_json"])],
            result=row["result"],
            error=row["error"],
            retry_count=row["retry_count"],
        )

    @staticmethod
    def _public_record(task: TaskRecord) -> dict[str, Any]:
        return _redact(
            {
                "task_id": task.task_id,
                "request": task.request,
                "mode": task.mode.value,
                "status": task.status.value,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
                "active_application": task.active_application,
                "steps": [_step_dict(s) for s in task.steps],
                "result": task.result,
                "error": task.error,
                "retry_count": task.retry_count,
            }
        )

    def close(self) -> None:
        """Compatibility no-op; connections are scoped to operations."""
        return None


__all__ = ["TaskStore", "default_path"]
