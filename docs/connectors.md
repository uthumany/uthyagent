# Connectors and external tools

The MCP manager, Telegram connector, browser connector catalogue, and connector permissions UI described in the product specification are not implemented in this alpha. No remote sender or third-party tool can currently submit a task through UthyAgent.

The current provider adapter is separate from desktop input: it can propose only the constrained action schema defined in `core/domain.py`. Provider output, visible page text, OCR text, and accessible control labels are treated as untrusted data and do not change local policy.

Future connector work should include a transport-specific adapter, per-server credentials in Secret Service, schema validation, tool-level permission controls, timeouts, an audit trail, explicit data-flow indicators, and tests for malformed or adversarial output before a connector is advertised as supported.
