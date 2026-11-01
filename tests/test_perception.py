from __future__ import annotations

from pathlib import Path

import pytest

from uthyagent.core.domain import DesktopState
from uthyagent.perception.desktop import DesktopObserver, detect_session_type


def test_detect_session_type_prefers_xdg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("DISPLAY", ":99")
    assert detect_session_type() == "wayland"


def test_detect_session_type_falls_back_to_display(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":99")
    assert detect_session_type() == "x11"


def test_detect_session_type_is_headless_without_display(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("XDG_SESSION_TYPE", "WAYLAND_DISPLAY", "DISPLAY"):
        monkeypatch.delenv(key, raising=False)
    assert detect_session_type() == "headless"


def test_observe_fails_gracefully_without_gi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    observer = DesktopObserver()
    state = observer.observe()
    assert isinstance(state, DesktopState)
    assert state.session_type == "x11"
    assert state.controls == ()
    assert any("AT-SPI unavailable" in warning for warning in state.warnings)


def test_observe_headless_reports_capability_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("XDG_SESSION_TYPE", "WAYLAND_DISPLAY", "DISPLAY"):
        monkeypatch.delenv(key, raising=False)
    state = DesktopObserver().observe()
    assert state.session_type == "headless"
    assert any("No graphical session" in warning for warning in state.warnings)


def test_atspi_snapshot_is_bounded_and_sanitizes_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")

    class FakeRole:
        value_name = "PUSH_BUTTON"

    class FakeNode:
        def __init__(self, name: str, children: list[object] | None = None) -> None:
            self.name = name
            self.children = children or []

        def get_name(self) -> str:
            return self.name

        def get_role(self) -> FakeRole:
            return FakeRole()

        def get_child_count(self) -> int:
            return len(self.children)

        def get_child_at_index(self, index: int) -> object:
            return self.children[index]

        def get_state_set(self) -> object:
            class State:
                def contains(self, _member: object) -> bool:
                    return False

            return State()

        def get_component(self, _index: int) -> object:
            raise RuntimeError("no component in test")

    root = FakeNode("bad\x00 label\n")
    fake_atspi = type(
        "Atspi",
        (),
        {
            "get_desktop": staticmethod(
                lambda: type(
                    "Desktop",
                    (),
                    {
                        "get_child_count": lambda self: 1,
                        "get_child_at_index": lambda self, index: root,
                    },
                )()
            )
        },
    )
    fake_gi = type("GI", (), {"repository": type("Repository", (), {"Atspi": fake_atspi})})

    monkeypatch.setitem(__import__("sys").modules, "gi", fake_gi)
    monkeypatch.setitem(__import__("sys").modules, "gi.repository", fake_gi.repository)
    state = DesktopObserver().observe()
    assert len(state.controls) == 1
    assert "\x00" not in state.controls[0].name
    assert "\n" not in state.controls[0].name


def test_screenshot_and_ocr_use_fixed_mocked_commands(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(
        "uthyagent.perception.desktop.shutil.which",
        lambda name: "/usr/bin/fake" if name in {"gnome-screenshot", "tesseract"} else None,
    )

    def fake_run(args, **kwargs):
        if len(args) > 1 and args[1] == "-f":
            Path(args[-1]).write_bytes(b"png")
            return type("Result", (), {"returncode": 0, "stdout": b"", "stderr": b""})()
        assert args[2:] == ["stdout", "--psm", "6"]
        return type("Result", (), {"returncode": 0, "stdout": "Detected text", "stderr": ""})()

    monkeypatch.setattr("uthyagent.perception.desktop.subprocess.run", fake_run)
    state = DesktopObserver(capture_screenshot=True, ocr=True).observe()
    assert state.screenshot_path is not None
    screenshot = Path(state.screenshot_path)
    assert screenshot.read_bytes() == b"png"
    assert screenshot.parent.stat().st_mode & 0o777 == 0o700
    assert screenshot.stat().st_mode & 0o777 == 0o600
    assert state.ocr_text == "Detected text"
    assert DesktopObserver.clear_screenshots() == 1
    assert not screenshot.exists()
