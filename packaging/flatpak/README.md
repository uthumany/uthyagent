# Flatpak packaging notes

This directory contains planning notes only. It does **not** contain a Flatpak manifest, and no Flatpak build, submission, or published package is claimed or implied.

## Intended packaging shape

A future manifest should package the Python/GTK application and install the `uthyagent` executable plus its desktop file and icon. The final runtime and SDK, Python dependencies, GTK introspection dependencies, module build steps, and application ID must be selected against the supported distribution targets and then validated with an actual Flatpak build.

The desktop launcher should use the application ID and installed icon expected by the completed manifest. Until those values are established, the Debian desktop file is best-effort metadata rather than proof of Flatpak integration.

## Access and platform caveats

- X11 prototype automation may require an `xdotool`-compatible tool and an X11 socket/display. Any Flatpak device or socket permissions must be narrowly justified and tested; do not add broad permissions merely to make automation appear to work.
- Wayland observability and automation can be restricted by the compositor and desktop security model. Portals or compositor-specific interfaces may be preferable where they provide the needed capability, but none are implemented or promised here.
- Telegram, MCP, and voice integrations are not available in the initial capability set, so no related Flatpak permissions or services should be advertised.
- A finished manifest should document why each socket, device, filesystem, or environment permission is needed and should be tested in both supported X11 and Wayland scenarios where applicable.

When packaging work begins, add a real manifest, build instructions, reproducible dependency versions, and evidence from local validation before describing Flatpak support as tested or release-ready.
