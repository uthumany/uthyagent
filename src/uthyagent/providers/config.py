"""Provider endpoint configuration without credentials."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit


def validate_base_url(value: str):
    if not isinstance(value, str) or not value.strip() or len(value) > 2_048:
        raise ValueError("Provider URL is required and must be at most 2048 characters")
    parts = urlsplit(value.strip())
    if (
        parts.scheme not in {"http", "https"}
        or not parts.netloc
        or parts.username is not None
        or parts.password is not None
    ):
        raise ValueError("Provider URL must be HTTP(S) without embedded credentials")
    if parts.query or parts.fragment:
        raise ValueError("Provider URL must not include a query or fragment")
    try:
        _ = parts.port
    except ValueError as exc:
        raise ValueError("Provider URL has an invalid port") from exc
    if parts.scheme == "http":
        host = (parts.hostname or "").casefold().rstrip(".")
        try:
            is_loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            is_loopback = host == "localhost"
        if not is_loopback:
            raise ValueError(
                "Unencrypted HTTP is allowed only for localhost/loopback model servers"
            )
    return parts


def is_loopback_url(value: str) -> bool:
    parts = validate_base_url(value)
    host = (parts.hostname or "").casefold().rstrip(".")
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def provider_key_profile(value: str) -> str:
    """Return a non-secret Secret Service profile scoped to the endpoint origin."""
    parts = validate_base_url(value)
    host = (parts.hostname or "").casefold().rstrip(".")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    origin = f"{parts.scheme.casefold()}://{host}:{port}"
    return "provider-" + hashlib.sha256(origin.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    base_url: str
    model: str
    timeout: float = 30.0

    def __post_init__(self) -> None:
        validate_base_url(self.base_url)
        if not isinstance(self.model, str) or not self.model.strip() or len(self.model) > 256:
            raise ValueError("Model ID is required and must be at most 256 characters")
        if (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, (int, float))
            or not 0 < self.timeout <= 300
        ):
            raise ValueError("Timeout must be between 0 and 300 seconds")


def config_path() -> Path:
    root = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(root) / "uthyagent" / "provider.json"


def save_config(config: ProviderConfig, path: str | os.PathLike[str] | None = None) -> Path:
    target = Path(path) if path is not None else config_path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temp.chmod(0o600)
    temp.replace(target)
    target.chmod(0o600)
    return target


def load_config(path: str | os.PathLike[str] | None = None) -> ProviderConfig | None:
    target = Path(path) if path is not None else config_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Provider configuration is unreadable or malformed") from exc
    if not isinstance(data, dict) or set(data) - {"base_url", "model", "timeout"}:
        raise ValueError("Provider configuration has unexpected fields")
    try:
        return ProviderConfig(**data)
    except (TypeError, ValueError) as exc:
        raise ValueError("Provider configuration is invalid") from exc
