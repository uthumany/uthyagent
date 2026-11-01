# Troubleshooting

## The graphical window does not start

Run `uthyagent check`. The GTK window requires GTK4/PyGObject and a logged-in graphical session. On Debian/Ubuntu/Zorin development setups, install the distribution packages `python3-gi` and `gir1.2-gtk-4.0`; create the venv with `--system-site-packages`. The CLI remains available without the GTK UI.

## The automation backend is unavailable

Check the reported session type and whether `xdotool` is installed. The current desktop input backend is X11-only; a Wayland session may expose reduced capability. Do not set environment variables to pretend Wayland is X11 or try to bypass compositor security.

## Provider test fails

Confirm the base URL, model server state, and model ID. The connection test uses `GET /models`. Local plain HTTP URLs must be `localhost` or an IP loopback address; hosted endpoints must use HTTPS. Check the provider's own model/usage status separately; UthyAgent does not guarantee quotas or pricing.

## Hosted API key cannot be saved

Install `libsecret-tools` and make sure a Secret Service keyring is running in the logged-in desktop session. The key is prompted without echo and is not accepted as a command-line argument. Avoid putting it in shell history, screenshots, or task prompts.

## A task stops for approval or does not verify

The GTK UI offers one-action approval for gated actions. The CLI does not approve actions. A stale desktop plan is discarded if the active state changes. A task can fail if the expected visible result is missing; review the local history rather than assuming the operation succeeded.

## Delete local data

Use `uthyagent history list` to find task IDs, `uthyagent history delete <task-id>` for an individual record, `uthyagent history purge --before <ISO-8601 timestamp>` to remove older records, or `uthyagent privacy clear-screenshots` for cached screenshots. Back up anything needed before deletion.
