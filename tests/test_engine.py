from __future__ import annotations

import asyncio
import unittest

from uthyagent.core.domain import (
    AccessibleControl,
    ActionOutcome,
    ActionType,
    AgentAction,
    DesktopState,
    Rect,
    RunMode,
    TaskStatus,
)
from uthyagent.core.engine import TaskEngine
from uthyagent.core.safety import SafetyPolicy


class FakeObserver:
    def __init__(self, state: DesktopState) -> None:
        self.state = state
        self.calls = 0

    def observe(self) -> DesktopState:
        self.calls += 1
        return self.state


class ChangingObserver(FakeObserver):
    def __init__(self, *states: DesktopState) -> None:
        super().__init__(states[0])
        self.states = list(states)

    def observe(self) -> DesktopState:
        state = self.states[min(self.calls, len(self.states) - 1)]
        self.calls += 1
        self.state = state
        return state


class FakePlanner:
    def __init__(self, *actions: AgentAction) -> None:
        self.actions = list(actions)
        self.calls = 0

    async def plan_action(self, request: str, state: DesktopState, history: list) -> AgentAction:
        self.calls += 1
        return self.actions.pop(0)


class FakeAutomation:
    def __init__(self, observer: FakeObserver) -> None:
        self.observer = observer
        self.actions: list[AgentAction] = []

    def snapshot(self) -> DesktopState:
        return DesktopState(session_type="x11", screen_width=800, screen_height=600)

    def execute(self, action: AgentAction, state: DesktopState) -> ActionOutcome:
        self.actions.append(action)
        self.observer.state = DesktopState(
            session_type="x11",
            active_application=state.active_application,
            window_title=state.window_title,
            screen_width=800,
            screen_height=600,
            controls=state.controls,
            ocr_text=state.ocr_text + " changed",
        )
        return ActionOutcome(True, "fake action completed")


class FakeStore:
    def __init__(self) -> None:
        self.saved = []

    def save(self, task) -> None:
        self.saved.append((task.task_id, task.status))


class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_observe_mode_never_calls_planner_or_backend(self) -> None:
        observer = FakeObserver(DesktopState(active_application="Files", window_title="Downloads"))
        planner = FakePlanner(AgentAction(ActionType.CLICK, x=5, y=5))
        store = FakeStore()
        engine = TaskEngine(observer, planner, automation=None, safety=SafetyPolicy(), store=store)
        task = await engine.run("Inspect the desktop", RunMode.OBSERVE)
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertIn("No desktop changes", task.result or "")
        self.assertEqual(planner.calls, 0)
        self.assertEqual(len(task.steps), 0)
        self.assertTrue(store.saved)

    async def test_assisted_action_waits_for_approval_and_does_not_execute(self) -> None:
        observer = FakeObserver(DesktopState(session_type="x11", active_application="Editor"))
        planner = FakePlanner(AgentAction(ActionType.WAIT, wait_ms=10))
        backend = FakeAutomation(observer)
        engine = TaskEngine(observer, planner, backend, SafetyPolicy())
        task = await engine.run("Wait", RunMode.ASSISTED)
        self.assertEqual(task.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(backend.actions, [])
        self.assertTrue(task.steps[0].decision.requires_confirmation)

    async def test_explicit_assisted_approval_is_for_one_action(self) -> None:
        observer = FakeObserver(DesktopState(session_type="x11", active_application="Editor"))
        planner = FakePlanner(
            AgentAction(ActionType.WAIT, wait_ms=10),
            AgentAction(ActionType.COMPLETE, rationale="Wait finished", expected_result="Editor"),
        )
        backend = FakeAutomation(observer)
        approvals = []

        async def approve(action, decision, state, index):
            approvals.append((action.type, index))
            return True

        engine = TaskEngine(observer, planner, backend, SafetyPolicy(), approval_callback=approve)
        task = await engine.run("Wait", RunMode.ASSISTED)
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(len(backend.actions), 1)
        self.assertEqual(approvals, [(ActionType.WAIT, 1)])
        self.assertTrue(task.steps[0].outcome.evidence["verification"]["verified"])

    async def test_accessible_target_is_resolved_to_a_bounded_coordinate(self) -> None:
        initial = DesktopState(
            session_type="x11",
            active_application="Editor",
            controls=(AccessibleControl("Save", "button", Rect(40, 20, 30, 20)),),
        )
        observer = FakeObserver(initial)
        planner = FakePlanner(
            AgentAction(ActionType.CLICK, target="Save"),
            AgentAction(
                ActionType.COMPLETE, rationale="Save action verified", expected_result="Save"
            ),
        )
        backend = FakeAutomation(observer)
        engine = TaskEngine(observer, planner, backend, SafetyPolicy())
        task = await engine.run("Save the document", RunMode.AUTONOMOUS)
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual((backend.actions[0].x, backend.actions[0].y), (55, 30))

    async def test_cancelled_task_stops_before_planning(self) -> None:
        observer = FakeObserver(DesktopState(active_application="Editor"))
        planner = FakePlanner(AgentAction(ActionType.COMPLETE))
        cancelled = asyncio.Event()
        cancelled.set()
        engine = TaskEngine(observer, planner, automation=None, safety=SafetyPolicy())
        task = await engine.run("Cancel me", RunMode.AUTONOMOUS, cancel_event=cancelled)
        self.assertEqual(task.status, TaskStatus.CANCELLED)
        self.assertEqual(planner.calls, 0)

    async def test_state_change_after_planning_discards_action_and_replans(self) -> None:
        initial = DesktopState(
            session_type="x11",
            active_application="Editor",
            window_title="Draft",
            controls=(AccessibleControl("Save", "button", Rect(0, 0, 20, 20)),),
        )
        changed = DesktopState(
            session_type="x11", active_application="Browser", window_title="New page"
        )
        observer = ChangingObserver(initial, changed)
        planner = FakePlanner(
            AgentAction(ActionType.CLICK, target="Save", x=10, y=10),
            AgentAction(
                ActionType.COMPLETE,
                rationale="No action needed in the new window",
                expected_result="New page",
            ),
        )
        backend = FakeAutomation(observer)
        engine = TaskEngine(observer, planner, backend, SafetyPolicy())
        task = await engine.run("Save the document", RunMode.AUTONOMOUS)
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(backend.actions, [])
        self.assertIn("Desktop changed after planning", task.steps[0].decision.reason)

    async def test_completion_without_visible_evidence_is_not_success(self) -> None:
        observer = FakeObserver(DesktopState(session_type="x11", active_application="Editor"))
        planner = FakePlanner(AgentAction(ActionType.COMPLETE, rationale="Everything is done"))
        backend = FakeAutomation(observer)
        engine = TaskEngine(observer, planner, backend, SafetyPolicy())
        task = await engine.run("Finish task", RunMode.AUTONOMOUS)
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertIn("without an observable expected result", task.error or "")


if __name__ == "__main__":
    unittest.main()
