import unittest

from uthyagent.core.domain import ActionType, AgentAction, DesktopState
from uthyagent.core.verifier import state_fingerprint, verify_action


class VerifierTests(unittest.TestCase):
    def test_timestamp_does_not_make_state_look_changed(self):
        first = DesktopState(observed_at="a", active_application="firefox", ocr_text="Home")
        later = DesktopState(observed_at="b", active_application="firefox", ocr_text="Home")
        self.assertEqual(state_fingerprint(first), state_fingerprint(later))

    def test_visible_change_verifies_successful_action(self):
        before = DesktopState(active_application="firefox", ocr_text="New Tab")
        after = DesktopState(active_application="firefox", ocr_text="Example Domain")
        result = verify_action(AgentAction(ActionType.CLICK), before, after, True)
        self.assertTrue(result.verified)

    def test_expected_result_is_required_when_supplied(self):
        before = DesktopState(active_application="firefox", ocr_text="Search")
        after = DesktopState(active_application="firefox", ocr_text="Results")
        action = AgentAction(ActionType.KEY_PRESS, expected_result="no matching record")
        result = verify_action(action, before, after, True)
        self.assertFalse(result.verified)

    def test_failed_backend_never_verifies(self):
        state = DesktopState(active_application="firefox")
        result = verify_action(AgentAction(ActionType.WAIT), state, state, False)
        self.assertFalse(result.verified)


if __name__ == "__main__":
    unittest.main()
