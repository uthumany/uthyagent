# UthyAgent

UthyAgent is a local-first Linux desktop computer-use agent in early development, initially targeting Zorin OS 18.1 Core and compatible GNOME desktops. This local source tree contains a tested foundation for a cautious observe–plan–act–verify loop, a GTK4 dashboard with the supplied logo and light/dark themes, an OpenAI-compatible provider adapter, local task history, and an X11 automation path when the required desktop tools are installed.

This is an alpha implementation, not the complete product described in the project specification. General Wayland input automation, full AT-SPI coverage, computer vision, voice, Telegram, MCP management, workflows, automatic screenshot retention, installer artifacts, AppImage/RPM release builds, and Flathub publication are not represented as completed features. GTK window construction and Zorin OS 18.1 compatibility have not been verified in this sandbox.

## Current implementation

- **Observe mode** is read-only and does not invoke an action backend.
- **Assisted, autonomous, and restricted modes** pass proposed UI actions through an explicit policy check; actions requiring approval stop until approved.
- **The execution loop** bounds step count, supports cancellation, records outcomes, detects repeated actions, and reinspects the desktop after actions.
- **Provider adapter** targets OpenAI-compatible chat-completions APIs and validates structured actions before they can reach the policy layer. No provider or API key is configured by default.
- **Task history** is stored locally in SQLite; exported and persisted user content is redacted by the history layer.
- **GTK4 UI** is optional at import time and requires distribution-provided PyGObject/GTK4 bindings at runtime.
- **Run modes** default to Observe; the GTK UI supports per-action Assisted approvals. Restricted mode is intentionally unavailable in the UI until an allowlist editor exists; the CLI requires `--allowed-app` for restricted tasks.
- **X11 automation** is available only where a supported `xdotool` backend is detected. This does not bypass OS permissions or application security prompts.
- **Wayland** capability is reported conservatively; the prototype does not promise general Wayland input control.

See [architecture](docs/architecture.md), [permissions and limits](docs/permissions.md), [security notes](docs/security.md), [provider setup](docs/providers.md), [installation](docs/installation.md), and the [reference audit](docs/reference-audit.md).

## Development setup

Use Python 3.11 or newer and a virtual environment. On Debian/Ubuntu/Zorin, install the desktop bindings from the distribution rather than trying to build PyGObject with pip:

```bash
sudo apt install python3 python3-venv python3-gi gir1.2-gtk-4.0 xdotool libsecret-tools at-spi2-core tesseract-ocr gnome-screenshot
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

The system `python3-gi` package may not be visible inside an isolated venv unless it is created with `--system-site-packages`. Alternatively, install the Python package without the UI bindings to run core tests and command-line checks.

Run tests:

```bash
python -m unittest discover -s tests -v
# or, when pytest is installed:
pytest
```

Run the environment diagnostic and help:

```bash
uthyagent check
uthyagent --help
```

The desktop application requires an active graphical session. Do not run unreviewed automation against production accounts or sensitive data.

## Configure a model

The app has no provider configured by default. Local OpenAI-compatible endpoints can use loopback HTTP:

```bash
uthyagent provider configure --base-url http://localhost:11434/v1 --model <model-id> --no-key
uthyagent provider test
uthyagent provider models
```

For hosted providers, use their documented HTTPS base URL and model ID. UthyAgent prompts for the API key without echo and stores it in Secret Service. Remote inference is identified in the UI; availability and pricing are controlled by the provider. See [provider setup](docs/providers.md).

## Privacy and safety

The default mode is observe-only. A configured remote model receives the task prompt and compact desktop state needed to plan; OCR text is included only when OCR is explicitly enabled. Screenshots are not included in model requests in this alpha. Configure only a provider you trust, keep credentials in the operating system's Secret Service, and avoid entering passwords, payment data, or other sensitive information into tasks. The current prototype has no telemetry.

Screenshot capture, when OCR is requested, remains in the user's private cache. There is no automatic expiry yet; remove cached images with `uthyagent privacy clear-screenshots`. Task records can be reviewed or removed with `uthyagent history list`, `uthyagent history delete <task-id>`, and `uthyagent history purge --before <ISO-8601 timestamp>`.

The new project is licensed under MIT as approved by the project owner; see [LICENSE](LICENSE). The logo was supplied by the project owner. The reference Android repository was inspected but not reused because no top-level license grant was present. The MIT-licensed quickLiquid project informed visual direction only; no code from it has been incorporated.

## Status

The public repository is being initialized from this alpha tree. There is no published software release, `.deb`, RPM, AppImage, Flatpak listing, or stable Zorin compatibility claim. See [release status](docs/release-status.md) for what is implemented and checked.
