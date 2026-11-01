"""Shared data contracts for UthyAgent's Linux-first task loop.

The reference Android application is not imported here; these are original,
platform-neutral types for the desktop implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class RunMode(StrEnum):
    OBSERVE = "observe"
    ASSISTED = "assisted"
    AUTONOMOUS = "autonomous"
    RESTRICTED = "restricted"


class TaskStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActionType(StrEnum):
    CLICK = "click"
    TYPE_TEXT = "type_text"
    KEY_PRESS = "key_press"
    SCROLL = "scroll"
    WAIT = "wait"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height


@dataclass(frozen=True, slots=True)
class AccessibleControl:
    name: str
    role: str
    rect: Rect | None = None
    states: tuple[str, ...] = ()
    identifier: str | None = None


@dataclass(frozen=True, slots=True)
class DesktopState:
    observed_at: str = field(default_factory=utc_now)
    session_type: str = "unknown"
    active_application: str | None = None
    window_title: str | None = None
    screen_width: int | None = None
    screen_height: int | None = None
    controls: tuple[AccessibleControl, ...] = ()
    ocr_text: str = ""
    screenshot_path: str | None = None
    warnings: tuple[str, ...] = ()

    def compact(self, max_controls: int = 80, max_text: int = 6000) -> dict[str, Any]:
        return {
            "observed_at": self.observed_at,
            "session_type": self.session_type,
            "active_application": self.active_application,
            "window_title": self.window_title,
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "controls": [
                {
                    "name": control.name,
                    "role": control.role,
                    "rect": None
                    if control.rect is None
                    else {
                        "x": control.rect.x,
                        "y": control.rect.y,
                        "width": control.rect.width,
                        "height": control.rect.height,
                    },
                    "states": list(control.states),
                    "identifier": control.identifier,
                }
                for control in self.controls[:max_controls]
            ],
            "ocr_text": self.ocr_text[:max_text],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class AgentAction:
    type: ActionType
    rationale: str = ""
    target: str | None = None
    text: str | None = None
    key: str | None = None
    x: int | None = None
    y: int | None = None
    button: str = "left"
    scroll_x: int = 0
    scroll_y: int = 0
    wait_ms: int = 500
    expected_result: str | None = None


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    allowed: bool
    reason: str
    requires_confirmation: bool = False


@dataclass(frozen=True, slots=True)
class ActionOutcome:
    success: bool
    message: str
    started_at: str = field(default_factory=utc_now)
    finished_at: str = field(default_factory=utc_now)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StepRecord:
    index: int
    action: AgentAction
    decision: SafetyDecision
    outcome: ActionOutcome | None
    observed_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    request: str
    mode: RunMode
    status: TaskStatus = TaskStatus.CREATED
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    active_application: str | None = None
    steps: list[StepRecord] = field(default_factory=list)
    result: str | None = None
    error: str | None = None
    retry_count: int = 0


class ProviderError(RuntimeError):
    """A provider failed safely, without returning an executable action."""


class AutomationError(RuntimeError):
    """An operating-system automation backend could not perform an action."""


class ApprovalRequired(RuntimeError):
    """An action is valid but gated on explicit user approval."""
