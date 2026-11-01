"""Minimal GNOME Secret Service adapter using the distribution's secret-tool."""

from __future__ import annotations

import shutil
import subprocess


class SecretStoreError(RuntimeError):
    pass


class SecretServiceStore:
    """Store provider tokens in Secret Service via ``secret-tool``.

    The secret is supplied on stdin to `secret-tool store`, never as an argv
    field. A missing keyring or executable produces a clear failure.
    """

    def __init__(self, *, app_id: str = "uthyagent", profile: str = "default") -> None:
        self.app_id = app_id
        self.profile = profile

    @staticmethod
    def available() -> bool:
        return shutil.which("secret-tool") is not None

    def set_secret(self, secret: str) -> None:
        if not isinstance(secret, str) or not secret.strip() or len(secret) > 16_384:
            raise ValueError("Secret must be non-empty and at most 16384 characters")
        executable = shutil.which("secret-tool")
        if not executable:
            raise SecretStoreError(
                "secret-tool is unavailable; install libsecret-tools and enable a Secret Service keyring"
            )
        try:
            result = subprocess.run(
                [
                    executable,
                    "store",
                    "--label=UthyAgent provider credential",
                    "app",
                    self.app_id,
                    "profile",
                    self.profile,
                ],
                input=secret,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SecretStoreError("Could not store the provider secret in Secret Service") from exc
        if result.returncode != 0:
            raise SecretStoreError("Secret Service did not accept the provider secret")

    def get_secret(self) -> str | None:
        executable = shutil.which("secret-tool")
        if not executable:
            raise SecretStoreError(
                "secret-tool is unavailable; install libsecret-tools and enable a Secret Service keyring"
            )
        try:
            result = subprocess.run(
                [executable, "lookup", "app", self.app_id, "profile", self.profile],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SecretStoreError(
                "Could not read the provider secret from Secret Service"
            ) from exc
        if result.returncode != 0:
            return None
        secret = result.stdout.rstrip("\n")
        return secret or None

    def clear(self) -> bool:
        executable = shutil.which("secret-tool")
        if not executable:
            raise SecretStoreError(
                "secret-tool is unavailable; install libsecret-tools and enable a Secret Service keyring"
            )
        try:
            result = subprocess.run(
                [executable, "clear", "app", self.app_id, "profile", self.profile],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SecretStoreError(
                "Could not clear the provider secret from Secret Service"
            ) from exc
        return result.returncode == 0
