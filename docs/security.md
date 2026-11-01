# Security and privacy

UthyAgent controls other applications through the logged-in desktop session. It is a local application, not a sandbox or a security boundary. Use a separate test account and non-sensitive data while evaluating it.

## Defaults and data flow

- No provider, model, API key, telemetry, Telegram bot, or MCP server is enabled by default.
- `observe` mode is read-only. The CLI defaults task runs to observe mode.
- A configured hosted model receives the request and compact desktop text/state needed to plan. OCR text is included only when OCR is explicitly enabled. Screenshots are not attached to provider requests in this alpha.
- The GTK header shows whether the configured endpoint is classified as local loopback or remote. Confirm the endpoint before starting a task.
- Provider credentials are stored in Secret Service via `secret-tool`, not in command-line arguments or the provider JSON settings. Provider request bodies and API error bodies are not logged.
- A configured remote endpoint must use HTTPS. Plain HTTP is permitted only for `localhost` and loopback IPs. Redirects are refused.

## Action boundaries

- The action policy receives a constrained action object; arbitrary shell commands are not a supported action.
- Observe mode never permits mutation.
- Assisted mode requires per-action approval in the GTK UI. Approval applies to one proposed action and is not remembered.
- Autonomous mode still gates destructive/privileged/financial/publication/sensitive actions, blind coordinate clicks, Enter/Return submissions, and communication fields detected by the policy.
- The engine re-observes and fingerprints accessible desktop state before acting. A changed state discards the stale proposal and triggers replanning. This alpha does not validate target coordinates against a fresh screenshot; blind coordinate clicks therefore require confirmation.
- Restricted mode is usable only with a CLI `--allowed-app` allowlist. The GTK setting for a restricted allowlist is not yet implemented, so the UI refuses that mode.
- X11 `xdotool` can send input to applications visible in the current session. This broad capability is not equivalent to sandboxing and must not bypass OS or application prompts.

## Local records and artifacts

Task history is stored in SQLite under the user's XDG data directory. Exports redact common credential patterns, but pattern-based redaction cannot guarantee removal of every secret. Review exports before sharing them.

When screenshot/OCR capture is enabled, screenshots are local files under the user's XDG cache directory. The directory is permission-restricted and files are owner-readable/writable. There is no automatic age-based retention yet. Delete them with:

```bash
uthyagent privacy clear-screenshots
```

Task history can be inspected, exported, deleted by ID, or purged by timestamp using `uthyagent history`. Avoid sharing database files or screenshots from real personal sessions.

## Not implemented

Telegram remote commands, MCP tools, voice, arbitrary terminal actions, a Wayland input backend, application sandboxing, signed releases, and Flathub are not available in this alpha. No claim of resistance to a compromised local user account or malicious application content is made.
