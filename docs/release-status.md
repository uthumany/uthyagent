# Release status

UthyAgent is an early alpha source tree. It is not an initial release and is not ready for general users.

## Verified here

- Python package installs in a project-local development environment.
- Unit tests pass in the development environment.
- Source and wheel distributions build.
- The command-line diagnostic and version/help entry points run.
- The app logo is included as a package resource.

## Not verified or not available

- The project has not been run on Zorin OS 18.1 Core or a physical supported Linux desktop.
- GTK4 window construction has not been smoke-tested with PyGObject in this sandbox.
- No end-to-end UI action was performed on a real user's desktop.
- X11 automation has unit tests but no desktop integration test against Firefox, GNOME Files, Settings, Terminal, or an IDE.
- Wayland interaction is unsupported beyond conservative capability reporting.
- No `.deb`, RPM, AppImage, Flatpak, signatures, checksums, release manifest, release tag, or tested upgrade/uninstall path exists.
- Voice, Telegram, MCP, workflows, background services, and application connector management are not implemented.
- MIT licensing and public publication to `uthumany/uthyagent` have been approved by the project owner; initial repository creation/push is in progress.
- Flathub submission has not been prepared or filed.

Do not label the project stable or advertise the missing capabilities until they have working implementations, tests, and release evidence.
