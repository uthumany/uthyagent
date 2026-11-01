# Permissions and platform capabilities

`uthyagent` is intended to be a Linux-first Python/GTK desktop application. These notes describe the initial prototype boundary; they are not a claim that every capability is implemented.

## Current prototype boundary

- The initial interaction prototype targets X11 and uses `xdotool` where available for desktop input automation.
- X11 automation can require an installed external utility and an active X11 session. Users should be able to understand and approve any action that sends input or interacts with another application.
- Wayland intentionally has no blanket promise of equivalent observability or automation. Compositor and desktop security policies can restrict window inspection, global input injection, screenshots, and other cross-application operations. A Wayland session may therefore expose fewer capabilities or require compositor/portal-specific integrations.
- Telegram integration is not available yet.
- MCP integration is not available yet.
- Voice input/output is not available yet.

## User and system permissions

The application should request only the access needed for an explicitly enabled feature. In particular, desktop automation and observation can affect other applications and may expose on-screen content; they should be opt-in, visible in the UI, and easy to stop. Do not describe X11 `xdotool` support as a security boundary or as permission to bypass another application's access controls.

A future implementation may need distribution- or desktop-specific access such as an executable `xdotool`, GTK runtime libraries, or portal/compositor permissions. Those requirements must be documented and tested for the target distribution before being added to package metadata. No Telegram, MCP, or voice permission is claimed here because those features do not exist yet.

## Honest support statement

Capability is session-dependent: “Linux support” does not guarantee identical behavior on X11 and Wayland. The application should report unavailable backends and failed permission checks clearly instead of silently claiming success. These limitations should be revisited as native Wayland, portal, Telegram, MCP, or voice integrations are implemented and verified.
