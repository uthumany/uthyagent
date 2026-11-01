# Reference audit

## Scope and conclusions

This audit records the status of the external references considered for `uthyagent`:

- `/workspace/uthyagent-reference` at commit `ce84a4710ffecea0ab1b3d9a1c16ae5d7794b199` is Android-only Flutter code. Its README describes the project as open source, but the repository has no top-level `LICENSE`; only local plugin license files were found. The README does not grant a license. This is not a sufficient basis for copying, adapting, or redistributing its code.
- `quickLiquid` at commit `fbb19b5f1cd4097e62831da44df0bee0097433ca` is MIT-licensed and supports React and vanilla DOM/SVG. Its interaction and rendering ideas may inform a Linux/GTK design, but GTK/Linux use is conceptual unless code is actually incorporated. If code is incorporated later, retain the MIT copyright and permission notice and record the copied files and changes.

## Sources inspected

- PrivateAgent repository at the requested commit: [source tree](https://github.com/orailnoor/private-agent/tree/ce84a4710ffecea0ab1b3d9a1c16ae5d7794b199), [README](https://raw.githubusercontent.com/orailnoor/private-agent/ce84a4710ffecea0ab1b3d9a1c16ae5d7794b199/README.md), and the local `lib/services/ai_service.dart`, `lib/services/task_executor.dart`, `lib/services/screen_automation_service.dart`, plus `android/app/src/main/kotlin/com/orailnoor/privateagent/AgentAccessibilityService.kt`. The README's “open-source” statement was reviewed alongside the tracked file list; no top-level license was found.
- quickLiquid at the inspected commit: [source tree](https://github.com/amarnath3003/quickLiquid/tree/fbb19b5f1cd4097e62831da44df0bee0097433ca), [MIT license](https://github.com/amarnath3003/quickLiquid/blob/fbb19b5f1cd4097e62831da44df0bee0097433ca/LICENSE), and [README](https://github.com/amarnath3003/quickLiquid/blob/fbb19b5f1cd4097e62831da44df0bee0097433ca/README.md). It describes a React and framework-free DOM/SVG implementation, not GTK components.

No third-party code has been copied into this project. In particular, this project does not reuse code from `uthyagent-reference`, and it does not imply that the Android repository's “open-source” wording is a license grant. No release or package binary is asserted by this audit.

The owner approved MIT licensing for the new project before public repository creation. `LICENSE` and `pyproject.toml` now reflect MIT. No code from the unlicensed `private-agent` repository or quickLiquid implementation was copied; the supplied logo is a project-owner asset.

## Practical guidance

1. Treat `uthyagent-reference` as a read-only reference for product or interaction understanding only. Do not copy source, assets, snippets, or generated output unless its copyright holder supplies a clear applicable license and the project records permission.
2. Treat `quickLiquid` as an MIT-licensed reference. Concepts can be reimplemented independently. If any implementation is copied, preserve the MIT notice in the appropriate distribution notices and update the inventory.
3. Keep future dependency and attribution records alongside packaging work. A dependency being public or described as open source is not, by itself, permission to redistribute its code.
4. Re-run this audit when a dependency, upstream commit, or copied implementation changes.
