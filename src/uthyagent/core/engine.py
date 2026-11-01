"""Bounded observe-plan-act-verify task engine for desktop actions."""

from __future__ import annotations

import asyncio
import inspect
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

from uthyagent.core.domain import (
    ActionOutcome,
    ActionType,
    AgentAction,
    DesktopState,
    RunMode,
    SafetyDecision,
    StepRecord,
    TaskRecord,
    TaskStatus,
    utc_now,
)
from uthyagent.core.verifier import state_fingerprint, verify_action

ApprovalCallback = Callable[
    [AgentAction, SafetyDecision, DesktopState, int], bool | Awaitable[bool]
]
UpdateCallback = Callable[[TaskRecord, str], None]


async def _invoke(method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Invoke either an async collaborator or a blocking local API off-loop."""
    if inspect.iscoroutinefunction(method):
        return await method(*args, **kwargs)
    return await asyncio.to_thread(method, *args, **kwargs)


class TaskEngine:
    """Run one task with strict step limits and fail-closed action checks.

    Collaborators are injected to keep the core independently testable. The
    observer and OS backend are synchronous today; the provider is async. Task
    storage may be sync or async. Collaborators are always awaited or moved to a
    worker thread so the UI loop is not blocked by desktop calls.
    """

    def __init__(
        self,
        observer: Any,
        planner: Any,
        automation: Any,
        safety: Any,
        store: Any | None = None,
        *,
        max_steps: int = 20,
        max_consecutive_failures: int = 3,
        approval_callback: ApprovalCallback | None = None,
        on_update: UpdateCallback | None = None,
    ) -> None:
        if not 1 <= max_steps <= 100:
            raise ValueError("max_steps must be between 1 and 100")
        if not 1 <= max_consecutive_failures <= 10:
            raise ValueError("max_consecutive_failures must be between 1 and 10")
        self.observer = observer
        self.planner = planner
        self.automation = automation
        self.safety = safety
        self.store = store
        self.max_steps = max_steps
        self.max_consecutive_failures = max_consecutive_failures
        self.approval_callback = approval_callback
        self.on_update = on_update

    async def run(
        self,
        request: str,
        mode: RunMode = RunMode.OBSERVE,
        *,
        cancel_event: asyncio.Event | None = None,
    ) -> TaskRecord:
        request = request.strip()
        if not request:
            raise ValueError("A task request is required")
        if len(request) > 8_000:
            raise ValueError("Task request exceeds 8000 characters")
        if isinstance(mode, str):
            mode = RunMode(mode)

        task = TaskRecord(
            task_id=str(uuid.uuid4()), request=request, mode=mode, status=TaskStatus.RUNNING
        )
        await self._persist(task)
        self._notify(task, "Observing the desktop")
        try:
            state: DesktopState = await _invoke(self.observer.observe)
            task.active_application = state.active_application
            if mode is RunMode.OBSERVE:
                task.status = TaskStatus.COMPLETED
                task.result = self._observation_summary(state)
                return task
            if self.planner is None:
                raise RuntimeError(
                    "No AI provider is configured. Configure a provider or use observe mode."
                )

            failures = 0
            seen_actions: dict[tuple[str, str], int] = {}
            for index in range(1, self.max_steps + 1):
                if cancel_event is not None and cancel_event.is_set():
                    task.status = TaskStatus.CANCELLED
                    task.result = "Task cancelled by the user."
                    break
                if not callable(getattr(self.automation, "execute", None)):
                    raise RuntimeError("No desktop automation backend is configured.")

                # A fresh backend snapshot provides current display bounds before
                # the model proposes coordinates. It is not a permission bypass.
                snapshot = getattr(self.automation, "snapshot", None)
                if callable(snapshot):
                    backend_state = await _invoke(snapshot)
                    if isinstance(backend_state, DesktopState):
                        state = replace(
                            state,
                            session_type=backend_state.session_type or state.session_type,
                            screen_width=backend_state.screen_width,
                            screen_height=backend_state.screen_height,
                        )

                self._notify(task, f"Planning step {index} of {self.max_steps}")
                action: AgentAction = await _invoke(
                    self.planner.plan_action, request, state, list(task.steps)
                )
                if not isinstance(action, AgentAction):
                    raise TypeError("Planner did not return a validated AgentAction")

                if action.type is ActionType.COMPLETE:
                    decision = SafetyDecision(
                        True, "Completion marker; no desktop mutation requested"
                    )
                    if not action.expected_result:
                        task.status = TaskStatus.FAILED
                        task.error = (
                            "The planner reported completion without an observable expected result."
                        )
                        task.steps.append(
                            StepRecord(
                                index,
                                action,
                                SafetyDecision(
                                    False, "completion requires an observable expected_result"
                                ),
                                ActionOutcome(False, task.error),
                            )
                        )
                        break
                    check = verify_action(action, state, state, True)
                    outcome = ActionOutcome(
                        check.verified,
                        check.explanation,
                        evidence={
                            "verification": {
                                "verified": check.verified,
                                "explanation": check.explanation,
                                "before_fingerprint": check.before_fingerprint,
                                "after_fingerprint": check.after_fingerprint,
                            }
                        },
                    )
                    task.steps.append(StepRecord(index, action, decision, outcome))
                    if not check.verified:
                        task.status = TaskStatus.FAILED
                        task.error = "The planner reported completion, but its expected result was not visible."
                        break
                    task.status = TaskStatus.COMPLETED
                    task.result = (
                        action.rationale
                        or action.expected_result
                        or "Task marked complete by the planner."
                    )[:1_000]
                    break

                action = self._resolve_accessible_target(action, state)
                screen_size = None
                if (
                    isinstance(state.screen_width, int)
                    and state.screen_width > 0
                    and isinstance(state.screen_height, int)
                    and state.screen_height > 0
                ):
                    screen_size = (state.screen_width, state.screen_height)
                decision: SafetyDecision = await _invoke(
                    self.safety.evaluate,
                    action,
                    mode,
                    active_application=state.active_application,
                    screen_size=screen_size,
                    confirmed=False,
                )
                if not isinstance(decision, SafetyDecision):
                    raise TypeError("Safety policy did not return a SafetyDecision")

                if decision.requires_confirmation:
                    if self.approval_callback is None:
                        task.status = TaskStatus.AWAITING_APPROVAL
                        task.result = f"Waiting for approval: {decision.reason}"
                        task.steps.append(StepRecord(index, action, decision, None))
                        break
                    approved = await self._approval(action, decision, state, index)
                    if not approved:
                        task.status = TaskStatus.CANCELLED
                        task.result = (
                            "The proposed action was not approved; no action was executed."
                        )
                        task.steps.append(StepRecord(index, action, decision, None))
                        break
                    decision = await _invoke(
                        self.safety.evaluate,
                        action,
                        mode,
                        active_application=state.active_application,
                        screen_size=screen_size,
                        confirmed=True,
                    )
                    if not isinstance(decision, SafetyDecision):
                        raise TypeError("Safety policy did not return a SafetyDecision")

                if not decision.allowed:
                    task.status = TaskStatus.FAILED
                    task.error = f"Action blocked by safety policy: {decision.reason}"
                    task.steps.append(StepRecord(index, action, decision, None))
                    break

                # Planning and a user's approval may take long enough for the
                # foreground window or target geometry to change. Discard the
                # stale proposal and plan again from the current state.
                fresh_state: DesktopState = await _invoke(self.observer.observe)
                if callable(snapshot):
                    fresh_backend_state = await _invoke(snapshot)
                    if isinstance(fresh_backend_state, DesktopState):
                        fresh_state = replace(
                            fresh_state,
                            session_type=fresh_backend_state.session_type
                            or fresh_state.session_type,
                            screen_width=fresh_backend_state.screen_width,
                            screen_height=fresh_backend_state.screen_height,
                        )
                if state_fingerprint(fresh_state) != state_fingerprint(state):
                    stale_decision = SafetyDecision(
                        False,
                        "Desktop changed after planning; action was not executed and will be replanned",
                    )
                    task.steps.append(StepRecord(index, action, stale_decision, None))
                    state = fresh_state
                    task.active_application = fresh_state.active_application
                    task.updated_at = utc_now()
                    await self._persist(task)
                    self._notify(task, stale_decision.reason)
                    continue
                state = fresh_state

                signature = (action.type.value, repr(action))
                seen_actions[signature] = seen_actions.get(signature, 0) + 1
                if seen_actions[signature] >= 3:
                    task.status = TaskStatus.FAILED
                    task.error = "Stopped after detecting a repeated action loop."
                    task.steps.append(StepRecord(index, action, decision, None))
                    break

                self._notify(task, action.rationale or f"Executing {action.type.value}")
                outcome: ActionOutcome = await _invoke(self.automation.execute, action, state)
                if not isinstance(outcome, ActionOutcome):
                    raise TypeError("Automation backend did not return an ActionOutcome")
                after: DesktopState = await _invoke(self.observer.observe)
                verification = verify_action(action, state, after, outcome.success)
                evidence = dict(outcome.evidence)
                evidence["verification"] = {
                    "verified": verification.verified,
                    "explanation": verification.explanation,
                    "before_fingerprint": verification.before_fingerprint,
                    "after_fingerprint": verification.after_fingerprint,
                }
                outcome = ActionOutcome(
                    success=outcome.success,
                    message=outcome.message,
                    started_at=outcome.started_at,
                    finished_at=outcome.finished_at,
                    evidence=evidence,
                )
                task.steps.append(StepRecord(index, action, decision, outcome))
                task.active_application = after.active_application
                task.updated_at = utc_now()
                await self._persist(task)
                self._notify(task, verification.explanation)

                if verification.verified:
                    failures = 0
                else:
                    failures += 1
                    task.retry_count += 1
                    if failures >= self.max_consecutive_failures:
                        task.status = TaskStatus.FAILED
                        task.error = (
                            "Stopped after repeated unverified actions. " + verification.explanation
                        )
                        break
                state = after
            else:
                task.status = TaskStatus.FAILED
                task.error = f"Reached the configured limit of {self.max_steps} steps."

            if task.status is TaskStatus.RUNNING:
                task.status = TaskStatus.FAILED
                task.error = "Task ended without a terminal state."
        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            task.result = "Task cancelled."
        except Exception as exc:
            # Provider/network exceptions are intentionally surfaced without raw
            # body content; store redaction is an additional safety layer.
            task.status = TaskStatus.FAILED
            task.error = f"{type(exc).__name__}: {exc}"[:1_000]
        finally:
            task.updated_at = utc_now()
            await self._persist(task)
            self._notify(task, task.result or task.error or task.status.value)
        return task

    async def _approval(
        self, action: AgentAction, decision: SafetyDecision, state: DesktopState, index: int
    ) -> bool:
        if self.approval_callback is None:
            return False
        result = self.approval_callback(action, decision, state, index)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    async def _persist(self, task: TaskRecord) -> None:
        if self.store is None:
            return
        save = getattr(self.store, "save", None) or getattr(self.store, "save_task", None)
        if not callable(save):
            raise TypeError("Task store must provide save(task)")
        await _invoke(save, task)

    def _notify(self, task: TaskRecord, message: str) -> None:
        if self.on_update is not None:
            self.on_update(task, message[:500])

    @staticmethod
    def _resolve_accessible_target(action: AgentAction, state: DesktopState) -> AgentAction:
        if action.type is not ActionType.CLICK or not action.target:
            return action
        match = next(
            (
                control
                for control in state.controls
                if control.name.casefold() == action.target.casefold() and control.rect
            ),
            None,
        )
        if match is None or match.rect is None or match.rect.width <= 0 or match.rect.height <= 0:
            return replace(action, target=None)
        rect = match.rect
        if action.x is None or action.y is None:
            return replace(action, x=rect.x + rect.width // 2, y=rect.y + rect.height // 2)
        if not rect.contains(action.x, action.y):
            return replace(action, target=None)
        return action

    @staticmethod
    def _observation_summary(state: DesktopState) -> str:
        app = state.active_application or "unknown application"
        title = f" — {state.window_title}" if state.window_title else ""
        count = len(state.controls)
        return f"Observed {app}{title}; found {count} accessible controls. No desktop changes were made."
