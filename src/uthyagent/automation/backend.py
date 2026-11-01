"""Safe Linux desktop automation backends.

The implementation deliberately supports only X11 through the external ``xdotool``
program.  Wayland is reported as unavailable rather than being bypassed with
unsafe or compositor-specific workarounds.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from uthyagent.core.domain import (
    ActionOutcome,
    ActionType,
    AgentAction,
    AutomationError,
    DesktopState,
    Rect,
)

_XDOTool = Callable[..., subprocess.CompletedProcess[str]]


def detect_session_type(environ: dict[str, str] | None = None) -> str:
    """Return ``x11``, ``wayland``, or ``unknown`` from session environment.

    ``XDG_SESSION_TYPE`` is authoritative when present.  Display variables are
    useful fallbacks in lightweight sessions and test environments.
    """
    env = os.environ if environ is None else environ
    session = env.get("XDG_SESSION_TYPE", "").strip().lower()
    if session in {"x11", "wayland"}:
        return session
    if env.get("WAYLAND_DISPLAY", "").strip():
        return "wayland"
    if env.get("DISPLAY", "").strip():
        return "x11"
    return "unknown"


@dataclass(frozen=True, slots=True)
class BackendAvailability:
    """A diagnostic, non-executable description of backend availability."""

    available: bool
    backend: str
    session_type: str
    reason: str
    executable: str | None = None

    def as_dict(self) -> dict[str, str | bool | None]:
        return {
            "available": self.available,
            "backend": self.backend,
            "session_type": self.session_type,
            "reason": self.reason,
            "executable": self.executable,
        }


def backend_availability(environ: dict[str, str] | None = None) -> BackendAvailability:
    """Report whether the safe xdotool backend can be used right now."""
    session = detect_session_type(environ)
    executable = shutil.which("xdotool")
    if session == "wayland":
        return BackendAvailability(
            False,
            "xdotool",
            session,
            "Wayland detected; xdotool requires X11. Use an approved Wayland-native accessibility backend instead.",
            executable,
        )
    if session != "x11":
        return BackendAvailability(
            False,
            "xdotool",
            session,
            "X11 is not indicated by the session environment (DISPLAY is required).",
            executable,
        )
    if not executable:
        return BackendAvailability(
            False,
            "xdotool",
            session,
            "xdotool is not installed or is not available on PATH.",
            None,
        )
    return BackendAvailability(
        True, "xdotool", session, "xdotool is available for X11 automation.", executable
    )


def report_backend_availability(
    environ: dict[str, str] | None = None,
) -> dict[str, str | bool | None]:
    """Return backend availability as a serializable mapping."""
    return backend_availability(environ).as_dict()


_ALLOWED_KEYS = frozenset(
    {
        "enter",
        "return",
        "tab",
        "escape",
        "esc",
        "backspace",
        "delete",
        "space",
        "up",
        "down",
        "left",
        "right",
        "home",
        "end",
        "pageup",
        "pagedown",
        "ctrl",
        "alt",
        "shift",
        "super",
        "meta",
        "menu",
        "insert",
        "print",
        "f1",
        "f2",
        "f3",
        "f4",
        "f5",
        "f6",
        "f7",
        "f8",
        "f9",
        "f10",
        "f11",
        "f12",
    }
)
_ALLOWED_BUTTONS = frozenset({"left", "middle", "right"})
_MAX_SCROLL = 100
_MAX_WAIT_MS = 60_000


class X11Backend:
    """Minimal xdotool backend with fail-closed coordinate and input checks."""

    def __init__(
        self,
        environ: dict[str, str] | None = None,
        *,
        runner: _XDOTool | None = None,
        xdotool_path: str | None = None,
    ) -> None:
        self.environ = dict(os.environ if environ is None else environ)
        self._runner = runner or subprocess.run
        self._xdotool_path = xdotool_path or shutil.which("xdotool")
        self._state: DesktopState | None = None
        self._display_bounds: Rect | None = None

    @property
    def availability(self) -> BackendAvailability:
        result = backend_availability(self.environ)
        if self._xdotool_path and result.session_type == "x11":
            return BackendAvailability(
                True,
                result.backend,
                result.session_type,
                "xdotool is available for X11 automation.",
                self._xdotool_path,
            )
        return result

    def _require_available(self) -> str:
        status = self.availability
        if not status.available:
            raise AutomationError(status.reason)
        return status.executable or self._xdotool_path or "xdotool"

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        executable = self._require_available()
        try:
            result = self._runner([executable, *args], check=True, capture_output=True, text=True)
        except (OSError, subprocess.SubprocessError) as exc:
            raise AutomationError(f"xdotool operation failed: {exc}") from exc
        return result

    def snapshot(self) -> DesktopState:
        """Take a fresh geometry snapshot used to bound subsequent actions."""
        self._require_available()
        try:
            result = self._run("getdisplaygeometry")
            width, height = _parse_geometry(result.stdout)
        except (ValueError, AutomationError) as exc:
            if isinstance(exc, AutomationError):
                raise
            raise AutomationError(f"Could not read X11 display bounds: {exc}") from exc
        self._display_bounds = Rect(0, 0, width, height)
        self._state = DesktopState(session_type="x11", screen_width=width, screen_height=height)
        return self._state

    def execute(self, action: AgentAction, state: DesktopState | None = None) -> ActionOutcome:
        """Execute one validated action, returning an ``ActionOutcome``."""
        started = time.monotonic()
        if action.type in {
            ActionType.CLICK,
            ActionType.TYPE_TEXT,
            ActionType.KEY_PRESS,
            ActionType.SCROLL,
        }:
            self._require_available()
        current = state or self._state
        try:
            if action.type == ActionType.CLICK:
                x, y = self._coordinates(action, current)
                self._run("mousemove", "--", str(x), str(y))
                self._run("click", "--clearmodifiers", "--button", _button_number(action.button))
                message = f"Clicked at ({x}, {y})"
            elif action.type == ActionType.TYPE_TEXT:
                if action.text is None:
                    raise AutomationError("type_text requires text")
                self._run("type", "--clearmodifiers", "--delay", "20", "--", action.text)
                message = "Typed text"
            elif action.type == ActionType.KEY_PRESS:
                key = _validate_key(action.key)
                self._run("key", "--clearmodifiers", "--", key)
                message = f"Pressed {key}"
            elif action.type == ActionType.SCROLL:
                if abs(action.scroll_x) > _MAX_SCROLL or abs(action.scroll_y) > _MAX_SCROLL:
                    raise AutomationError(
                        f"Scroll values must be between {-_MAX_SCROLL} and {_MAX_SCROLL}"
                    )
                if action.scroll_x == 0 and action.scroll_y == 0:
                    raise AutomationError("scroll requires a non-zero scroll amount")
                for button, amount in _scroll_events(action.scroll_x, action.scroll_y):
                    self._run(
                        "click",
                        "--clearmodifiers",
                        "--repeat",
                        str(amount),
                        "--delay",
                        "10",
                        "--button",
                        str(button),
                    )
                message = "Scrolled"
            elif action.type == ActionType.WAIT:
                if not 0 <= action.wait_ms <= _MAX_WAIT_MS:
                    raise AutomationError(f"wait_ms must be between 0 and {_MAX_WAIT_MS}")
                time.sleep(action.wait_ms / 1000)
                message = f"Waited {action.wait_ms} ms"
            elif action.type == ActionType.COMPLETE:
                message = "Action sequence complete"
            else:
                raise AutomationError(f"Unsupported action type: {action.type}")
        except AutomationError:
            raise
        except Exception as exc:
            raise AutomationError(str(exc)) from exc
        elapsed = time.monotonic() - started
        return ActionOutcome(
            True, message, evidence={"backend": "xdotool", "elapsed_ms": round(elapsed * 1000, 2)}
        )

    def _coordinates(self, action: AgentAction, state: DesktopState | None) -> tuple[int, int]:
        if action.x is None or action.y is None:
            if action.target and state:
                for control in state.controls:
                    if control.name == action.target and control.rect:
                        rect = control.rect
                        return rect.x + rect.width // 2, rect.y + rect.height // 2
            raise AutomationError(
                "click requires coordinates or a named control with an accessible rect"
            )
        bounds = self._display_bounds
        if bounds is None:
            raise AutomationError("click requires a fresh snapshot before coordinates can be used")
        if not bounds.contains(action.x, action.y):
            raise AutomationError("click coordinates are outside the current display bounds")
        if state and action.target:
            control = next((c for c in state.controls if c.name == action.target), None)
            if control and control.rect and not control.rect.contains(action.x, action.y):
                raise AutomationError("click coordinates are outside the target control rect")
        return action.x, action.y


def _parse_geometry(output: str) -> tuple[int, int]:
    parts = output.strip().split()
    if len(parts) != 2:
        raise ValueError("xdotool returned an invalid geometry")
    width, height = (int(part) for part in parts)
    if width <= 0 or height <= 0:
        raise ValueError("display dimensions must be positive")
    return width, height


def _button_number(button: str) -> str:
    if button not in _ALLOWED_BUTTONS:
        raise AutomationError(f"Unknown mouse button: {button}")
    return {"left": "1", "middle": "2", "right": "3"}[button]


def _validate_key(key: str | None) -> str:
    if not key:
        raise AutomationError("key_press requires a key")
    normalized = key.strip().lower()
    if len(normalized) == 1 and normalized.isalnum():
        return normalized
    if normalized not in _ALLOWED_KEYS:
        raise AutomationError(f"Key is not allowlisted: {key}")
    return normalized


def _scroll_events(scroll_x: int, scroll_y: int) -> Sequence[tuple[int, int]]:
    events: list[tuple[int, int]] = []
    if scroll_y:
        events.append((4 if scroll_y > 0 else 5, abs(scroll_y)))
    if scroll_x:
        events.append((7 if scroll_x > 0 else 6, abs(scroll_x)))
    return events


# Friendly aliases for callers that prefer a generic backend name.
XdotoolBackend = X11Backend
get_backend_availability = backend_availability
