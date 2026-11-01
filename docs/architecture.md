# UthyAgent architecture

UthyAgent separates desktop observation, planning, action policy, input backends, task history, and the GTK view so that an unavailable platform capability can fail clearly without granting a model extra authority.

## Task loop

1. Validate the user request and create a local task record.
2. Observe the current desktop state through available accessibility and local fallback capabilities.
3. Ask only a configured provider for one constrained action.
4. Parse the provider response into the shared `AgentAction` data model; reject unknown action types and malformed fields.
5. Apply the user-selected run mode and application policy before execution.
6. Re-observe and compare a state fingerprint immediately before acting; discard and replan if the desktop changed while the model or user approval was pending.
7. Execute through an explicitly selected backend.
8. Observe again and record verification evidence.
9. Stop on completion with visible evidence, cancellation, a safety gate, repeated failures, a loop, or the configured step ceiling.

Provider output, accessibility labels, OCR, browser content, and connector output are untrusted input. None may change safety policy, authorize a privileged action, or introduce arbitrary shell execution.

## Components

- `core/domain.py`: shared typed data contracts.
- `core/engine.py`: bounded task orchestration.
- `core/safety.py`: explicit mode and action policy.
- `core/verifier.py`: visible-state change and expected-result checks.
- `perception/`: desktop state acquisition and capability reporting.
- `providers/`: provider-independent model interface adapters.
- `automation/`: platform-specific input backends.
- `storage/`: local SQLite task records and redaction.
- `ui/`: GTK4 interface; the view delegates task operations to callbacks.

## Platform boundary

The first input backend is X11-oriented and requires `xdotool`. Wayland is not treated as X11: this implementation must report reduced capabilities rather than attempting to defeat compositor security. AT-SPI, screenshot portals, and OCR are optional; absence should be visible in the interface and diagnostics. The engine refreshes display bounds and accessible-state fingerprints, but this alpha does not validate coordinates against a fresh screenshot; blind coordinate clicks require confirmation.

## Data leaving the device

Local observation and SQLite history stay on the device. When a user configures a hosted provider, only the request and selected compact state are sent to that provider. This first implementation does not attach screenshots. No telemetry runs by default. Remote commands, MCP tools, and voice providers are not yet implemented.
