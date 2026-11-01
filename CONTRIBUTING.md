# Contributing

UthyAgent is an early Linux-first alpha. Contributions should be small, testable, and explicit about which distribution/session they were verified on. The Android `private-agent` repository is an unlicensed reference and is not a source of code to copy. Do not add code, assets, or generated output from it without a written license grant.

## Development

```bash
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
pytest -q
```

Keep GTK optional for core imports and unit tests. Add fake collaborators for engine tests; do not send input to the developer's real desktop during ordinary CI. Do not commit API keys, local provider configuration, SQLite histories, screenshots, or private task transcripts.

## Changes and tests

- Explain observable behavior and relevant safety boundaries.
- Add unit tests for failure cases and denial paths, not only successful actions.
- Keep remote provider errors, credentials, and user data out of logs.
- Record new dependencies and their licenses before packaging.
- Do not claim Wayland or distribution support without a real test on that environment.
- For UI work, check keyboard access, focus visibility, contrast, and reduced-motion behavior.

The project is MIT-licensed as approved by its owner. Public contributions are welcome through GitHub pull requests; follow the pull-request template and do not submit unlicensed code, private information, or unsupported platform claims.
