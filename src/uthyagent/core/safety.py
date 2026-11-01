"""Conservative, platform-neutral policy checks for desktop actions.

This module only decides whether an already-proposed :class:`AgentAction` may
be executed.  It never performs I/O, changes state, or interprets arbitrary
shell commands.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .domain import ActionType, AgentAction, RunMode, SafetyDecision

MAX_TEXT_LENGTH = 4_000
MAX_RATIONALE_LENGTH = 2_000
MAX_WAIT_MS = 30_000
MAX_SCROLL_DELTA = 2_000

# Deliberately conservative: these keys can close windows, expose privileged
# prompts, or otherwise escape the intended bounded UI interaction.
_SUSPICIOUS_KEYS = frozenset(
    {
        "alt+f4",
        "alt+tab",
        "ctrl+alt+delete",
        "ctrl+alt+f1",
        "ctrl+alt+f2",
        "ctrl+alt+t",
        "ctrl+shift+esc",
        "super",
        "win",
        "command",
    }
)
_RISK_WORDS = frozenset(
    {
        "delete",
        "destroy",
        "remove",
        "format",
        "shutdown",
        "reboot",
        "sudo",
        "root",
        "admin",
        "password",
        "credential",
        "secret",
        "payment",
        "purchase",
        "checkout",
        "transfer",
        "publish",
        "post",
        "send",
        "upload",
        "share",
        "public",
        "permission",
        "install",
        "uninstall",
        "confirm",
        "approve",
        "email",
        "recipient",
        "message",
        "comment",
        "submit",
        "bank",
        "card",
    }
)


def _decision(allowed: bool, reason: str, confirmation: bool = False) -> SafetyDecision:
    return SafetyDecision(allowed=allowed, reason=reason, requires_confirmation=confirmation)


def _text_is_well_formed(value: str | None, limit: int) -> bool:
    if value is None:
        return True
    if not isinstance(value, str) or len(value) > limit:
        return False
    # NUL and other control characters are not valid UI text. Newline and tab
    # are retained because they are legitimate in text fields.
    return all(ch in "\n\t\r" or ord(ch) >= 32 for ch in value)


def _risk_text(action: AgentAction) -> str:
    fields = (action.target, action.text, action.key, action.rationale, action.expected_result)
    return " ".join(value for value in fields if isinstance(value, str)).casefold()


@dataclass(frozen=True, slots=True)
class SafetyPolicy:
    """Evaluate actions without executing or mutating anything.

    ``allowed_applications`` is used only in restricted mode. Application
    names are compared case-insensitively after trimming whitespace.
    """

    allowed_applications: frozenset[str] = frozenset()
    max_text_length: int = MAX_TEXT_LENGTH
    max_wait_ms: int = MAX_WAIT_MS
    max_scroll_delta: int = MAX_SCROLL_DELTA

    def __post_init__(self) -> None:
        if self.max_text_length <= 0 or self.max_wait_ms <= 0 or self.max_scroll_delta <= 0:
            raise ValueError("safety limits must be positive")
        object.__setattr__(
            self,
            "allowed_applications",
            frozenset(
                app.strip().casefold()
                for app in self.allowed_applications
                if isinstance(app, str) and app.strip()
            ),
        )

    def evaluate(
        self,
        action: AgentAction,
        mode: RunMode = RunMode.OBSERVE,
        *,
        active_application: str | None = None,
        screen_size: tuple[int, int] | None = None,
        confirmed: bool = False,
    ) -> SafetyDecision:
        """Return a deterministic decision for one proposed action.

        ``confirmed`` represents fresh, explicit approval for this exact
        action; it is never remembered or applied to subsequent actions.
        """
        if not isinstance(action, AgentAction):
            return _decision(False, "action must be an AgentAction")
        try:
            mode = RunMode(mode)
        except (TypeError, ValueError):
            return _decision(False, "unknown run mode")

        if mode is RunMode.OBSERVE:
            return _decision(False, "observe mode never permits mutation")

        if mode is RunMode.RESTRICTED:
            app = (
                active_application.strip().casefold() if isinstance(active_application, str) else ""
            )
            if not app or app not in self.allowed_applications:
                return _decision(False, "active application is not on the restricted allowlist")

        invalid = self._validate(action, screen_size)
        if invalid:
            return _decision(False, invalid)

        risky = self._is_risky(action)
        if mode is RunMode.ASSISTED:
            if not confirmed:
                return _decision(
                    False, "assisted mode requires confirmation for every action", True
                )
            return _decision(True, "explicit confirmation received for assisted action")
        if risky:
            if not confirmed:
                return _decision(
                    False,
                    "action is destructive, privileged, financial, publication-related, or sensitive-data and requires confirmation",
                    True,
                )
            return _decision(True, "explicit confirmation received for gated action")
        return _decision(True, "bounded low-risk UI action is permitted")

    # A descriptive alias makes call sites read naturally without duplicating policy.
    decide = evaluate

    def _validate(self, action: AgentAction, screen_size: tuple[int, int] | None) -> str | None:
        if not _text_is_well_formed(action.rationale, MAX_RATIONALE_LENGTH):
            return "rationale is malformed or oversized"
        if action.type is ActionType.TYPE_TEXT:
            if not isinstance(action.text, str) or not _text_is_well_formed(
                action.text, self.max_text_length
            ):
                return "text is missing, malformed, or oversized"
        if action.type is ActionType.CLICK:
            if (
                not isinstance(action.x, int)
                or isinstance(action.x, bool)
                or not isinstance(action.y, int)
                or isinstance(action.y, bool)
            ):
                return "click requires integer coordinates"
            if (
                not isinstance(screen_size, (tuple, list))
                or len(screen_size) != 2
                or any(not isinstance(v, int) or isinstance(v, bool) or v <= 0 for v in screen_size)
            ):
                return "click requires a positive screen size"
            if not (0 <= action.x < screen_size[0] and 0 <= action.y < screen_size[1]):
                return "click coordinates are outside the screen"
            if not isinstance(action.button, str) or action.button.casefold() not in {
                "left",
                "right",
                "middle",
            }:
                return "unsupported mouse button"
        if action.type is ActionType.KEY_PRESS:
            if not isinstance(action.key, str) or not action.key.strip() or len(action.key) > 80:
                return "key press is missing or malformed"
            if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in action.key):
                return "key press contains control characters"
            if action.key.strip().casefold() in _SUSPICIOUS_KEYS:
                return "suspicious or escape-oriented key sequence"
        if action.type is ActionType.WAIT:
            if (
                not isinstance(action.wait_ms, int)
                or isinstance(action.wait_ms, bool)
                or not 0 <= action.wait_ms <= self.max_wait_ms
            ):
                return "wait is outside the permitted range"
        if action.type is ActionType.SCROLL:
            if any(
                not isinstance(v, int) or isinstance(v, bool)
                for v in (action.scroll_x, action.scroll_y)
            ):
                return "scroll deltas must be integers"
            if (
                abs(action.scroll_x) > self.max_scroll_delta
                or abs(action.scroll_y) > self.max_scroll_delta
            ):
                return "scroll delta is unreasonable"
        if action.type not in set(ActionType):
            return "unsupported action type"
        return None

    @staticmethod
    def _is_risky(action: AgentAction) -> bool:
        if action.type is ActionType.COMPLETE:
            return True  # completion can publish an external result
        if action.type is ActionType.CLICK and not action.target:
            return True  # a blind coordinate has no semantic control evidence
        if (
            action.type is ActionType.KEY_PRESS
            and action.key
            and action.key.strip().casefold() in {"enter", "return"}
        ):
            return True  # Enter can submit, send, or confirm a dialog
        if (
            action.type is ActionType.TYPE_TEXT
            and action.text
            and any(
                word in action.text.casefold()
                for word in ("password", "secret", "token", "credit card")
            )
        ):
            return True
        haystack = _risk_text(action)
        return any(word in haystack.split() or word in haystack for word in _RISK_WORDS)


def policy_for(allowed_applications: Iterable[str] = ()) -> SafetyPolicy:
    """Convenience constructor kept intentionally free of external dependencies."""
    return SafetyPolicy(frozenset(allowed_applications))
