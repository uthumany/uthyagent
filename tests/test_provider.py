from __future__ import annotations

import json
import unittest

from uthyagent.core.domain import ActionType, DesktopState, ProviderError
from uthyagent.providers.openai_compatible import OpenAICompatibleProvider


class FakeTransport:
    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = payload if payload is not None else {}
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body, timeout))
        return self.status, {}, json.dumps(self.payload).encode()


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def test_rejects_unsafe_urls_without_network(self):
        for url in (
            "ftp://example.test",
            "https://user:secret@example.test",
            "example.test",
            "https://example.test?a=1",
            "http://api.example.test/v1",
        ):
            with self.assertRaises(ValueError):
                OpenAICompatibleProvider(url)
        local = OpenAICompatibleProvider("http://127.0.0.1:11434/v1", model="local")
        self.assertEqual(local.model, "local")

    async def test_plan_action_uses_chat_completions_and_parses_action(self):
        transport = FakeTransport(
            payload={"choices": [{"message": {"content": '{"type":"wait","wait_ms":250}'}}]}
        )
        provider = OpenAICompatibleProvider(
            "https://example.test/v1", key="secret", model="demo", transport=transport
        )
        action = await provider.plan_action("wait", DesktopState())
        self.assertEqual(action.type, ActionType.WAIT)
        self.assertEqual(action.wait_ms, 250)
        method, url, headers, body, timeout = transport.calls[0]
        self.assertEqual((method, url), ("POST", "https://example.test/v1/chat/completions"))
        self.assertEqual(headers["Authorization"], "Bearer secret")
        self.assertNotIn("secret", body.decode())
        self.assertEqual(json.loads(body)["max_tokens"], 512)

    async def test_strict_parser_rejects_markdown_injection_and_tool_calls(self):
        for content in (
            '```json\n{"type":"complete"}\n```',
            '{"type":"complete","rationale":"ignore previous instructions"}',
        ):
            transport = FakeTransport(payload={"choices": [{"message": {"content": content}}]})
            with self.assertRaises(ProviderError):
                await OpenAICompatibleProvider(
                    "https://example.test", transport=transport
                ).plan_action("x", DesktopState())
        transport = FakeTransport(
            payload={"choices": [{"message": {"content": '{"type":"complete"}', "tool_calls": []}}]}
        )
        with self.assertRaises(ProviderError):
            await OpenAICompatibleProvider("https://example.test", transport=transport).plan_action(
                "x", DesktopState()
            )

    async def test_schema_and_bounds_are_checked(self):
        bad = [
            '{"type":"unknown"}',
            '{"type":"type_text"}',
            '{"type":"wait","wait_ms":120001}',
            '{"type":"complete","extra":true}',
        ]
        for content in bad:
            transport = FakeTransport(payload={"choices": [{"message": {"content": content}}]})
            with self.assertRaises(ProviderError):
                await OpenAICompatibleProvider(
                    "https://example.test", transport=transport
                ).plan_action("x", DesktopState())

    async def test_models_preserve_declared_capabilities_without_inference(self):
        transport = FakeTransport(
            payload={
                "data": [
                    {"id": "text-model", "owned_by": "local"},
                    {"id": "vision-model", "capabilities": {"vision": True}, "free": True},
                    {"not_an_model": True},
                ]
            }
        )
        models = await OpenAICompatibleProvider(
            "https://example.test", transport=transport
        ).list_models()
        self.assertEqual(models[0], {"id": "text-model", "owned_by": "local"})
        self.assertEqual(models[1]["capabilities"], {"vision": True})
        self.assertNotIn("free", models[1])

    async def test_connection_returns_false_on_provider_error(self):
        transport = FakeTransport(status=503, payload={"error": "Bearer secret"})
        self.assertFalse(
            await OpenAICompatibleProvider(
                "https://example.test", transport=transport
            ).test_connection()
        )


if __name__ == "__main__":
    unittest.main()
