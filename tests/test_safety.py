from __future__ import annotations

import unittest

from uthyagent.core.domain import ActionType, AgentAction, RunMode
from uthyagent.core.safety import SafetyPolicy


class SafetyPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = SafetyPolicy(frozenset({"Calculator", "Text Editor"}))

    def test_default_and_observe_never_allow_mutation(self) -> None:
        action = AgentAction(ActionType.CLICK, x=2, y=3)
        self.assertFalse(self.policy.evaluate(action).allowed)
        self.assertIn("observe", self.policy.evaluate(action).reason)
        self.assertFalse(self.policy.evaluate(action, RunMode.OBSERVE).allowed)

    def test_assisted_requires_confirmation_for_every_valid_action(self) -> None:
        decision = self.policy.evaluate(AgentAction(ActionType.WAIT, wait_ms=10), RunMode.ASSISTED)
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.requires_confirmation)
        confirmed = self.policy.evaluate(
            AgentAction(ActionType.WAIT, wait_ms=10), RunMode.ASSISTED, confirmed=True
        )
        self.assertTrue(confirmed.allowed)

    def test_autonomous_allows_bounded_low_risk_actions(self) -> None:
        for action in (
            AgentAction(ActionType.CLICK, target="Reload", x=10, y=10),
            AgentAction(ActionType.TYPE_TEXT, target="Search field", text="hello"),
            AgentAction(ActionType.KEY_PRESS, key="tab"),
            AgentAction(ActionType.SCROLL, scroll_y=300),
            AgentAction(ActionType.WAIT, wait_ms=500),
        ):
            self.assertTrue(
                self.policy.evaluate(action, RunMode.AUTONOMOUS, screen_size=(100, 100)).allowed
            )

    def test_autonomous_gates_blind_clicks_submission_keys_and_sensitive_fields(self):
        actions = (
            AgentAction(ActionType.CLICK, x=10, y=10),
            AgentAction(ActionType.KEY_PRESS, key="enter"),
            AgentAction(ActionType.TYPE_TEXT, target="Email message body", text="hello"),
        )
        for action in actions:
            decision = self.policy.evaluate(action, RunMode.AUTONOMOUS, screen_size=(100, 100))
            self.assertFalse(decision.allowed)
            self.assertTrue(decision.requires_confirmation)

    def test_autonomous_gates_risky_actions_until_explicit_confirmation(self) -> None:
        action = AgentAction(ActionType.CLICK, rationale="submit payment", x=10, y=10)
        blocked = self.policy.evaluate(action, RunMode.AUTONOMOUS, screen_size=(100, 100))
        self.assertFalse(blocked.allowed)
        self.assertTrue(blocked.requires_confirmation)
        self.assertTrue(
            self.policy.evaluate(
                action, RunMode.AUTONOMOUS, screen_size=(100, 100), confirmed=True
            ).allowed
        )

    def test_restricted_requires_allowlisted_active_application(self) -> None:
        action = AgentAction(ActionType.WAIT, wait_ms=1)
        self.assertFalse(
            self.policy.evaluate(action, RunMode.RESTRICTED, active_application="Browser").allowed
        )
        self.assertTrue(
            self.policy.evaluate(
                action, RunMode.RESTRICTED, active_application=" calculator "
            ).allowed
        )
        self.assertFalse(self.policy.evaluate(action, RunMode.RESTRICTED).allowed)

    def test_click_requires_coordinates_and_on_screen_bounds(self) -> None:
        missing = self.policy.evaluate(
            AgentAction(ActionType.CLICK), RunMode.AUTONOMOUS, screen_size=(100, 100)
        )
        outside = self.policy.evaluate(
            AgentAction(ActionType.CLICK, x=100, y=0), RunMode.AUTONOMOUS, screen_size=(100, 100)
        )
        no_screen = self.policy.evaluate(
            AgentAction(ActionType.CLICK, x=1, y=1), RunMode.AUTONOMOUS
        )
        self.assertFalse(missing.allowed)
        self.assertFalse(outside.allowed)
        self.assertFalse(no_screen.allowed)

    def test_text_and_timing_limits_reject_malformed_or_oversized_values(self) -> None:
        oversized = AgentAction(ActionType.TYPE_TEXT, text="x" * 4_001)
        malformed = AgentAction(ActionType.TYPE_TEXT, text="ok\x00bad")
        too_long = AgentAction(ActionType.WAIT, wait_ms=30_001)
        too_far = AgentAction(ActionType.SCROLL, scroll_y=2_001)
        for action in (oversized, malformed, too_long, too_far):
            self.assertFalse(self.policy.evaluate(action, RunMode.AUTONOMOUS).allowed)

    def test_suspicious_key_sequences_are_rejected(self) -> None:
        for key in ("ctrl+alt+t", "Alt+F4", "ctrl+shift+esc"):
            decision = self.policy.evaluate(
                AgentAction(ActionType.KEY_PRESS, key=key), RunMode.AUTONOMOUS
            )
            self.assertFalse(decision.allowed)
            self.assertIn("key", decision.reason)

    def test_invalid_action_and_unknown_mode_are_safe(self) -> None:
        self.assertFalse(self.policy.evaluate(object()).allowed)  # type: ignore[arg-type]
        self.assertFalse(self.policy.evaluate(AgentAction(ActionType.WAIT), "unknown").allowed)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
