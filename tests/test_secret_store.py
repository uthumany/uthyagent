from __future__ import annotations

import unittest
from unittest.mock import patch

from uthyagent.storage.secret_store import SecretServiceStore


class SecretStoreTests(unittest.TestCase):
    def test_store_uses_stdin_and_never_command_line_secret(self) -> None:
        seen = {}

        def fake_run(args, **kwargs):
            seen["args"] = args
            seen.update(kwargs)

            class Result:
                returncode = 0

            return Result()

        with (
            patch(
                "uthyagent.storage.secret_store.shutil.which", return_value="/usr/bin/secret-tool"
            ),
            patch("uthyagent.storage.secret_store.subprocess.run", side_effect=fake_run),
        ):
            SecretServiceStore().set_secret("do-not-print-this")
        self.assertNotIn("do-not-print-this", seen["args"])
        self.assertEqual(seen["input"], "do-not-print-this")
        self.assertEqual(seen["stderr"], -3)


if __name__ == "__main__":
    unittest.main()
