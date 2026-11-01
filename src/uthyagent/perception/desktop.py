"""Best-effort Linux desktop perception.

All integrations in this module are optional. Observation must remain useful on
headless systems and must never require installing packages or escalating
privileges.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uthyagent.core.domain import AccessibleControl, DesktopState, Rect

_MAX_CONTROLS = 200
_MAX_DEPTH = 6
_MAX_LABEL = 240
_MAX_OCR = 6000


def detect_session_type() -> str:
    """Return ``wayland``, ``x11``, ``headless``, or ``unknown``.

    ``XDG_SESSION_TYPE`` is preferred, while display variables provide a useful
    fallback for minimal sessions and tests. This is detection only; it does
    not imply that any particular automation API is available.
    """
    value = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    if value in {"wayland", "x11"}:
        return value
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "headless" if value in {"", "tty", "console"} else "unknown"


def _clean(value: Any, limit: int = _MAX_LABEL) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    return " ".join(text.split())[:limit]


def _cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    path = Path(base).expanduser() / "uthyagent" / "screenshots"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


class DesktopObserver:
    """Collect accessible controls and optional local visual evidence."""

    def __init__(
        self,
        *,
        capture_screenshot: bool = False,
        ocr: bool = False,
        screenshot_timeout: float = 5.0,
        ocr_timeout: float = 5.0,
    ) -> None:
        self.capture_screenshot = capture_screenshot
        self.ocr = ocr
        self.screenshot_timeout = max(0.1, min(float(screenshot_timeout), 15.0))
        self.ocr_timeout = max(0.1, min(float(ocr_timeout), 15.0))

    @staticmethod
    def clear_screenshots() -> int:
        """Delete only PNG files from UthyAgent's private screenshot cache."""
        directory = _cache_dir()
        deleted = 0
        for path in directory.glob("*.png"):
            try:
                path.unlink()
                deleted += 1
            except OSError:
                continue
        return deleted

    def observe(self) -> DesktopState:
        session = detect_session_type()
        warnings: list[str] = []
        controls: list[AccessibleControl] = []
        active_application: str | None = None
        window_title: str | None = None

        if session == "wayland":
            warnings.append("Wayland limits global window metadata and screenshot availability.")
        elif session == "x11":
            warnings.append(
                "X11 metadata is best-effort and depends on local accessibility support."
            )
        elif session == "headless":
            warnings.append(
                "No graphical session detected; desktop controls and screenshots are unavailable."
            )

        try:
            controls, active_application, window_title = self._atspi_snapshot()
        except Exception as exc:  # optional integration must never break observation
            warnings.append(f"AT-SPI unavailable: {_clean(type(exc).__name__, 80)}.")

        screenshot_path: str | None = None
        ocr_text = ""
        if self.capture_screenshot and session != "headless":
            screenshot_path, capture_warning = self._capture_screenshot(session)
            if capture_warning:
                warnings.append(capture_warning)
            if screenshot_path and self.ocr:
                ocr_text, ocr_warning = self._read_ocr(screenshot_path)
                if ocr_warning:
                    warnings.append(ocr_warning)
        elif self.ocr:
            warnings.append("OCR skipped because screenshot capture is disabled.")

        return DesktopState(
            session_type=session,
            active_application=active_application,
            window_title=window_title,
            controls=tuple(controls[:_MAX_CONTROLS]),
            ocr_text=ocr_text[:_MAX_OCR],
            screenshot_path=screenshot_path,
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def _atspi_snapshot(self) -> tuple[list[AccessibleControl], str | None, str | None]:
        try:
            from gi.repository import Atspi  # type: ignore
        except (ImportError, ValueError) as exc:
            raise RuntimeError("GI/AT-SPI dependency missing") from exc

        desktop = Atspi.get_desktop()
        controls: list[AccessibleControl] = []
        focused: list[Any] = []

        def visit(node: Any, depth: int) -> None:
            if depth > _MAX_DEPTH or len(controls) >= _MAX_CONTROLS:
                return
            name = _clean(getattr(node, "get_name", lambda: "")())
            role_obj = getattr(node, "get_role", lambda: None)()
            role = _clean(getattr(role_obj, "value_name", role_obj), 100).lower()
            states: list[str] = []
            try:
                state = node.get_state_set()
                for state_name in ("FOCUSED", "VISIBLE", "SHOWING", "ENABLED"):
                    member = getattr(Atspi.StateType, state_name, None)
                    if member is not None and state.contains(member):
                        states.append(state_name.lower())
                if "focused" in states:
                    focused.append(node)
            except Exception:
                pass
            rect = None
            try:
                component = node.get_component(0)
                box = component.get_extents(0)
                if all(hasattr(box, attr) for attr in ("x", "y", "width", "height")):
                    rect = Rect(
                        int(box.x), int(box.y), max(0, int(box.width)), max(0, int(box.height))
                    )
            except Exception:
                pass
            if name or role:
                controls.append(
                    AccessibleControl(name=name, role=role, rect=rect, states=tuple(states))
                )
            try:
                count = min(int(node.get_child_count()), _MAX_CONTROLS)
                for index in range(count):
                    child = node.get_child_at_index(index)
                    if child is not None:
                        visit(child, depth + 1)
            except Exception:
                return

        try:
            count = min(int(desktop.get_child_count()), _MAX_CONTROLS)
            for index in range(count):
                child = desktop.get_child_at_index(index)
                if child is not None:
                    visit(child, 0)
        except Exception:
            pass

        app = title = None
        if focused:
            focused_node = focused[0]
            title = _clean(getattr(focused_node, "get_name", lambda: "")()) or None
            try:
                parent = focused_node
                for _ in range(_MAX_DEPTH):
                    parent = parent.get_parent()
                    if parent is None:
                        break
                    role = _clean(
                        getattr(getattr(parent, "get_role", lambda: None)(), "value_name", ""), 100
                    ).lower()
                    if "application" in role:
                        app = _clean(getattr(parent, "get_name", lambda: "")()) or None
                        break
            except Exception:
                pass
        return controls, app, title

    def _capture_screenshot(self, session: str) -> tuple[str | None, str | None]:
        commands: list[list[str]] = []
        if session == "wayland":
            commands.append(["grim"])
        if session == "x11":
            commands.extend([["gnome-screenshot", "-f"], ["import", "-window", "root"]])
        for command in commands:
            executable = shutil.which(command[0])
            if not executable:
                continue
            target = _cache_dir() / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".png")
            args = [executable, *command[1:]]
            if command[0] in {"grim", "gnome-screenshot"}:
                args.append(str(target))
            else:
                args.append(str(target))
            try:
                result = subprocess.run(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=self.screenshot_timeout,
                    check=False,
                )
                if result.returncode == 0 and target.is_file() and target.stat().st_size > 0:
                    try:
                        target.chmod(0o600)
                    except OSError:
                        pass
                    return str(target), None
            except (OSError, subprocess.SubprocessError):
                continue
        return None, "Screenshot utility unavailable or capture failed."

    def _read_ocr(self, screenshot_path: str) -> tuple[str, str | None]:
        executable = shutil.which("tesseract")
        if not executable:
            return "", "Tesseract not available; OCR skipped."
        try:
            result = subprocess.run(
                [executable, screenshot_path, "stdout", "--psm", "6"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=self.ocr_timeout,
                check=False,
            )
            if result.returncode == 0:
                return _clean(result.stdout, _MAX_OCR), None
        except (OSError, subprocess.SubprocessError):
            pass
        return "", "OCR failed or timed out."
