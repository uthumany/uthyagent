from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from uthyagent.providers.config import (
    ProviderConfig,
    is_loopback_url,
    load_config,
    provider_key_profile,
    save_config,
)


class ProviderConfigTests(unittest.TestCase):
    def test_plain_http_is_only_allowed_for_loopback(self) -> None:
        ProviderConfig("http://localhost:11434/v1", "llama")
        ProviderConfig("http://[::1]:1234/v1", "local")
        self.assertTrue(is_loopback_url("https://127.0.0.1/v1"))
        with self.assertRaises(ValueError):
            ProviderConfig("http://models.example.test/v1", "model")

    def test_secret_profiles_are_scoped_to_provider_origin(self) -> None:
        one = provider_key_profile("https://one.example.test/v1")
        same_origin = provider_key_profile("https://one.example.test/compatible/v1")
        other = provider_key_profile("https://two.example.test/v1")
        self.assertEqual(one, same_origin)
        self.assertNotEqual(one, other)
        self.assertNotIn("one.example.test", one)

    def test_config_round_trip_contains_no_secret_field_and_is_private(self) -> None:
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "private" / "provider.json"
            save_config(ProviderConfig("https://api.example.test/v1", "model-x", 19), target)
            loaded = load_config(target)
            self.assertEqual(loaded, ProviderConfig("https://api.example.test/v1", "model-x", 19))
            self.assertNotIn("api_key", json.loads(target.read_text(encoding="utf-8")))
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(target.parent.stat().st_mode & 0o077, 0)


if __name__ == "__main__":
    unittest.main()
