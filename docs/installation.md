# Installation and development setup

UthyAgent is currently an alpha source project. It has **not** been tested on Zorin OS 18.1 Core or packaged as a `.deb`, RPM, or AppImage. Do not treat this guide as a stable-release installation procedure.

## Debian, Ubuntu, and Zorin development environment

Install the operating-system libraries from the distribution. `xdotool`, GTK/PyGObject, Secret Service, AT-SPI, screenshot capture, and OCR are optional capabilities; only install what you intend to use.

```bash
sudo apt install python3 python3-venv python3-gi gir1.2-gtk-4.0 xdotool libsecret-tools at-spi2-core tesseract-ocr gnome-screenshot
```

From the checked-out project directory:

```bash
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
uthyagent check
pytest -q
```

`--system-site-packages` is used so the distribution's `python3-gi` bindings can be found in the venv. If GTK bindings are unavailable, the CLI and core package still import; the graphical interface will report the missing runtime dependency.

## Run the application

Run `uthyagent` in a logged-in graphical session to open the GTK window. Use `uthyagent check` to inspect detected session/backend capabilities. `uthyagent observe` gathers a read-only desktop summary. The application defaults to observe mode; mutating tasks require an explicit mode selection.

X11 input is supported only when `xdotool` and an X11 display are available. General Wayland input automation is not implemented. Never test automation against sensitive accounts or documents until its behavior has been reviewed.

## What is not packaged

There is no supported system installer or uninstaller yet. No reproducible `.deb`, RPM, AppImage, Flatpak, Zorin-tested package, signed release, checksum manifest, or upgrade procedure is available. These must be completed and tested on each target distribution before the project can claim release readiness.
