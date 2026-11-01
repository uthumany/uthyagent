import json
from concurrent.futures import ThreadPoolExecutor

import pytest

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
from uthyagent.storage.task_store import TaskStore


def make_task(task_id="t-1"):
    return TaskRecord(
        task_id=task_id,
        request="Open the dashboard with api_key=should-not-survive",
        mode=RunMode.ASSISTED,
        status=TaskStatus.COMPLETED,
        active_application="Browser",
        steps=[
            StepRecord(
                index=0,
                action=AgentAction(
                    ActionType.TYPE_TEXT, text="password=secret-value", target="search"
                ),
                decision=SafetyDecision(True, "safe", requires_confirmation=False),
                outcome=ActionOutcome(
                    True,
                    "Authorization: Bearer abcdefghijklmnop",
                    evidence={"api_key": "top-secret", "note": "ok"},
                ),
            )
        ],
        result="done",
        error="token=ghp_abcdefghijklmnopqrstuvwxyz",
        retry_count=1,
    )


def test_round_trip_nested_record_and_redaction(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    original = make_task()
    store.save(original)
    loaded = store.get("t-1")

    assert loaded is not None
    assert loaded.task_id == original.task_id
    assert loaded.mode is RunMode.ASSISTED
    assert loaded.steps[0].action.type is ActionType.TYPE_TEXT
    assert loaded.steps[0].outcome.evidence == {"api_key": "[REDACTED]", "note": "ok"}
    assert loaded.request != original.request
    assert "should-not-survive" not in loaded.request
    assert "ghp_abcdefghijklmnopqrstuvwxyz" not in (loaded.error or "")


def test_upsert_list_search_delete_and_filters(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    store.save(make_task("one"))
    second = make_task("two")
    second.status = TaskStatus.FAILED
    store.save(second)

    assert [x.task_id for x in store.list(status="failed")] == ["two"]
    assert [x.task_id for x in store.search("dashboard")] == ["two", "one"]
    assert store.delete("one") is True
    assert store.delete("one") is False
    assert store.get("one") is None

    with pytest.raises(ValueError):
        store.list(status="bogus")
    with pytest.raises(ValueError):
        store.list(limit=0)
    with pytest.raises(ValueError):
        store.search("")


def test_export_is_json_and_does_not_include_secrets(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    store.save(make_task())
    payload = json.loads(store.export())
    text = json.dumps(payload)
    assert payload[0]["task_id"] == "t-1"
    assert "top-secret" not in text
    assert "ghp_abcdefghijklmnopqrstuvwxyz" not in text


def test_retention_and_schema_migration_metadata(tmp_path):
    store = TaskStore(tmp_path / "tasks.sqlite3")
    task = make_task()
    task.updated_at = "2020-01-01T00:00:00+00:00"
    store.save(task)
    assert store.purge(older_than="2021-01-01T00:00:00+00:00") == 1
    assert store.get("t-1") is None


def test_concurrent_connections_can_save(tmp_path):
    path = tmp_path / "tasks.sqlite3"
    store = TaskStore(path)

    def save(i):
        store.save(make_task(str(i)))

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(save, range(12)))
    assert len(store.list(limit=100)) == 12


def test_ephemeral_memory_database_is_rejected_explicitly():
    with pytest.raises(ValueError, match="persistent SQLite"):
        TaskStore(":memory:")
