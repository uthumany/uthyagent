from __future__ import annotations

import subprocess

import pytest

from uthyagent.automation.backend import (
    X11Backend,
    backend_availability,
    detect_session_type,
)
from uthyagent.core.domain import (
    AccessibleControl,
    ActionType,
    AgentAction,
    AutomationError,
    DesktopState,
    Rect,
)


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        stdout = "1920 1080\n" if argv[1:] == ["getdisplaygeometry"] else ""
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")


def test_detect_session_type_prefers_explicit_session() -> None:
    assert detect_session_type({"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"}) == "wayland"
    assert detect_session_type({"DISPLAY": ":0"}) == "x11"
    assert detect_session_type({"WAYLAND_DISPLAY": "wayland-0"}) == "wayland"
    assert detect_session_type({}) == "unknown"


def test_wayland_is_reported_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("uthyagent.automation.backend.shutil.which", lambda _: "/usr/bin/xdotool")
    status = backend_availability({"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"})
    assert not status.available
    assert "Wayland" in status.reason


def test_snapshot_and_click_use_argument_array() -> None:
    runner = FakeRunner()
    backend = X11Backend(
        {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}, runner=runner, xdotool_path="/usr/bin/xdotool"
    )
    backend.snapshot()
    outcome = backend.execute(AgentAction(ActionType.CLICK, x=12, y=34))
    assert outcome.success
    assert runner.calls[0] == ["/usr/bin/xdotool", "getdisplaygeometry"]
    assert runner.calls[1] == ["/usr/bin/xdotool", "mousemove", "--", "12", "34"]
    assert runner.calls[2] == ["/usr/bin/xdotool", "click", "--clearmodifiers", "--button", "1"]


def test_text_is_passed_as_one_safe_argument() -> None:
    runner = FakeRunner()
    backend = X11Backend(
        {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}, runner=runner, xdotool_path="xdotool"
    )
    backend.execute(AgentAction(ActionType.TYPE_TEXT, text="$(touch /tmp/nope); hello"))
    assert runner.calls[-1] == [
        "xdotool",
        "type",
        "--clearmodifiers",
        "--delay",
        "20",
        "--",
        "$(touch /tmp/nope); hello",
    ]


def test_click_requires_fresh_bounds_and_rejects_out_of_bounds() -> None:
    runner = FakeRunner()
    backend = X11Backend(
        {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}, runner=runner, xdotool_path="xdotool"
    )
    with pytest.raises(AutomationError):
        backend.execute(AgentAction(ActionType.CLICK, x=1, y=1))
    backend.snapshot()
    with pytest.raises(AutomationError):
        backend.execute(AgentAction(ActionType.CLICK, x=1920, y=1))


def test_named_accessible_control_can_supply_click_point() -> None:
    runner = FakeRunner()
    backend = X11Backend(
        {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}, runner=runner, xdotool_path="xdotool"
    )
    backend.snapshot()
    state = DesktopState(
        session_type="x11", controls=(AccessibleControl("Save", "button", Rect(10, 20, 20, 10)),)
    )
    backend.execute(AgentAction(ActionType.CLICK, target="Save"), state)
    assert runner.calls[-2:] == [
        ["xdotool", "mousemove", "--", "20", "25"],
        ["xdotool", "click", "--clearmodifiers", "--button", "1"],
    ]


def test_key_button_and_scroll_are_allowlisted_and_bounded() -> None:
    runner = FakeRunner()
    backend = X11Backend(
        {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}, runner=runner, xdotool_path="xdotool"
    )
    backend.execute(AgentAction(ActionType.KEY_PRESS, key="Enter"))
    backend.execute(AgentAction(ActionType.SCROLL, scroll_y=-2))
    assert runner.calls[0][-1] == "enter"
    assert runner.calls[1][-1] == "5"
    with pytest.raises(AutomationError):
        backend.execute(AgentAction(ActionType.KEY_PRESS, key="ctrl;rm"))
    with pytest.raises(AutomationError):
        backend.execute(AgentAction(ActionType.CLICK, x=1, y=1, button="wheel"))
    with pytest.raises(AutomationError):
        backend.execute(AgentAction(ActionType.SCROLL, scroll_y=101))
