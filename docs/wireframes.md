# Current dashboard layout

The GTK4 alpha window has one working Home screen:

- A left rail with the supplied UthyAgent logo, Home, disabled Task History and Settings entries, and a light/dark theme toggle.
- A central task composer with Observe, Assisted, Autonomous, and Restricted mode selection, Run and Stop controls, and a step timeline.
- A right status pane with active-application text, inference route, approval state, and a pending-action approval button.

Task History and Settings entries are disabled because their full views are not implemented. Provider setup, task export/deletion, screenshot cleanup, and environment diagnostics are available via the CLI. Workflows, agent chat, connector management, screenshots/target highlights, voice, and onboarding mockups are not implemented.

The interface uses translucent GTK surfaces and restrained contrast styling. GTK does not provide a universal backdrop-blur effect across desktops, so this alpha does not claim a compositor-independent Liquid Glass blur. No continuous animation is used.
