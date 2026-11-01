"""Conservative, evidence-backed checks after UI actions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from uthyagent.core.domain import ActionType, AgentAction, DesktopState


@dataclass(frozen=True, slots=True)
class VerificationResult:
    verified: bool
    explanation: str
    before_fingerprint: str
    after_fingerprint: str


def state_fingerprint(state: DesktopState) -> str:
    """Hash only visible state fields; timestamps and artifact paths are excluded."""
    compact = state.compact()
    compact.pop("observed_at", None)
    compact.pop("warnings", None)
    compact.pop("screenshot_path", None)
    encoded = json.dumps(compact, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_action(
    action: AgentAction, before: DesktopState, after: DesktopState, backend_succeeded: bool
) -> VerificationResult:
    before_hash = state_fingerprint(before)
    after_hash = state_fingerprint(after)
    if not backend_succeeded:
        return VerificationResult(
            False, "Automation backend reported failure.", before_hash, after_hash
        )

    expected = (action.expected_result or "").strip()
    if expected:
        visible = "\n".join(
            [after.ocr_text, after.window_title or "", after.active_application or ""]
            + [f"{control.name} {control.role}" for control in after.controls]
        ).casefold()
        if expected.casefold() in visible:
            return VerificationResult(
                True,
                f"Expected text/control was observed: {expected[:160]}",
                before_hash,
                after_hash,
            )
        return VerificationResult(
            False, f"Expected result was not observed: {expected[:160]}", before_hash, after_hash
        )

    if action.type in {ActionType.WAIT, ActionType.COMPLETE}:
        return VerificationResult(
            True, "Non-mutating control step completed.", before_hash, after_hash
        )
    if before_hash != after_hash:
        return VerificationResult(
            True, "Visible desktop state changed after the action.", before_hash, after_hash
        )
    return VerificationResult(
        False,
        "Backend accepted the action, but no visible state change was detected.",
        before_hash,
        after_hash,
    )
