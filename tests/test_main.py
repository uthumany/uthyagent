from __future__ import annotations

from unittest.mock import patch

from uthyagent.main import _build_parser, _provider, _provider_status_label
from uthyagent.providers.config import ProviderConfig, save_config


def test_provider_status_shows_local_or_remote_route(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert _provider_status_label() == "No model configured · no remote inference"
    save_config(ProviderConfig("http://localhost:11434/v1", "llama"))
    assert _provider_status_label() == "Local model · localhost"
    save_config(ProviderConfig("https://api.example.test/v1", "model"))
    assert _provider_status_label() == "Remote inference · api.example.test"


def test_cli_defaults_to_observe_mode():
    args = _build_parser().parse_args(["run", "inspect this desktop"])
    assert args.mode == "observe"


def test_local_model_does_not_receive_a_stored_remote_key(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_config(ProviderConfig("http://localhost:11434/v1", "llama"))
    with (
        patch("uthyagent.main.SecretServiceStore.available", return_value=True),
        patch("uthyagent.main.SecretServiceStore.get_secret", return_value="not-for-local-model"),
        patch("uthyagent.main.OpenAICompatibleProvider") as provider,
    ):
        _provider()
    assert provider.call_args.kwargs["key"] is None


def test_hosted_provider_uses_scoped_secret_without_printing_it(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_config(ProviderConfig("https://api.example.test/v1", "remote-model"))
    with (
        patch("uthyagent.main.SecretServiceStore.available", return_value=True),
        patch("uthyagent.main.SecretServiceStore.get_secret", return_value="opaque-test-secret"),
        patch("uthyagent.main.OpenAICompatibleProvider") as provider,
    ):
        _provider()
    assert provider.call_args.kwargs["key"] == "opaque-test-secret"


def test_local_model_over_loopback_ipv6_is_classified_local(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_config(ProviderConfig("http://[::1]:11434/v1", "local"))
    assert _provider_status_label() == "Local model · ::1"
