"""Command-line and optional GTK application entry point."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import importlib.util
import json
import sys
import threading
from typing import Any

from uthyagent import __version__
from uthyagent.automation.backend import X11Backend, backend_availability
from uthyagent.core.domain import RunMode, TaskStatus
from uthyagent.core.engine import TaskEngine
from uthyagent.core.safety import SafetyPolicy
from uthyagent.perception.desktop import DesktopObserver, detect_session_type
from uthyagent.providers.config import (
    ProviderConfig,
    config_path,
    is_loopback_url,
    load_config,
    provider_key_profile,
    save_config,
    validate_base_url,
)
from uthyagent.providers.openai_compatible import OpenAICompatibleProvider
from uthyagent.storage.secret_store import SecretServiceStore, SecretStoreError
from uthyagent.storage.task_store import TaskStore, default_path


def _provider() -> OpenAICompatibleProvider:
    config = load_config()
    if config is None:
        raise RuntimeError("No provider is configured. Run `uthyagent provider configure` first.")
    secrets = SecretServiceStore(profile=provider_key_profile(config.base_url))
    key = (
        secrets.get_secret()
        if secrets.available() and not is_loopback_url(config.base_url)
        else None
    )
    return OpenAICompatibleProvider(
        config.base_url, key=key, model=config.model, timeout=config.timeout
    )


def _provider_status_label() -> str:
    config = load_config()
    if config is None:
        return "No model configured · no remote inference"
    parts = validate_base_url(config.base_url)
    host = (parts.hostname or "provider").casefold()
    local = is_loopback_url(config.base_url)
    route = "Local model" if local else "Remote inference"
    return f"{route} · {host}"


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _command_check(_args: argparse.Namespace) -> int:
    config = load_config()
    report = {
        "application": "UthyAgent",
        "version": __version__,
        "python": sys.version.split()[0],
        "session_type": detect_session_type(),
        "automation_backend": backend_availability().as_dict(),
        "gtk4_python_bindings_detected": importlib.util.find_spec("gi") is not None,
        "secret_tool_detected": SecretServiceStore.available(),
        "provider_configured": config is not None,
        "provider_config_path": str(config_path()) if config is not None else None,
        "local_task_history": str(default_path()),
        "note": "Diagnostics do not grant permissions or perform desktop actions.",
    }
    _print_json(report)
    return 0


def _command_observe(args: argparse.Namespace) -> int:
    state = DesktopObserver(capture_screenshot=args.ocr, ocr=args.ocr).observe()
    _print_json(state.compact())
    return 0


def _command_run(args: argparse.Namespace) -> int:
    mode = RunMode(args.mode)
    store = TaskStore()
    observer = DesktopObserver(capture_screenshot=args.ocr, ocr=args.ocr)
    planner = None
    automation = None
    if mode is not RunMode.OBSERVE:
        planner = _provider()
        automation = X11Backend()
        policy = SafetyPolicy(frozenset(args.allowed_app or ()))
    else:
        policy = SafetyPolicy()

    engine = TaskEngine(
        observer=observer,
        planner=planner,
        automation=automation,
        safety=policy,
        store=store,
        max_steps=args.max_steps,
    )
    task = asyncio.run(engine.run(args.request, mode))
    _print_json(
        {
            "task_id": task.task_id,
            "status": task.status.value,
            "mode": task.mode.value,
            "result": task.result,
            "error": task.error,
            "retry_count": task.retry_count,
            "step_count": len(task.steps),
            "note": "This CLI does not approve gated actions. Use the GTK interface for action-by-action approval.",
        }
    )
    return 0 if task.status is TaskStatus.COMPLETED else 2


def _command_provider_configure(args: argparse.Namespace) -> int:
    config = ProviderConfig(args.base_url, args.model, args.timeout)
    saved_to = save_config(config)
    store = SecretServiceStore(profile=provider_key_profile(config.base_url))
    if args.no_key:
        if store.available():
            store.clear()
        print(f"Provider settings saved without an API key for this endpoint: {saved_to}")
        return 0
    if not store.available():
        raise SecretStoreError(
            "secret-tool is unavailable. Install libsecret-tools and enable a Secret Service keyring, or configure a local provider without a key."
        )
    secret = getpass.getpass("Provider API key (leave blank for a local/no-key endpoint): ")
    if secret:
        store.set_secret(secret)
        print("Provider settings saved; API key stored in Secret Service.")
    else:
        print("Provider settings saved without an API key.")
    return 0


def _command_provider_test(_args: argparse.Namespace) -> int:
    provider = _provider()
    ok = asyncio.run(provider.test_connection())
    _print_json(
        {
            "reachable": ok,
            "provider": load_config().base_url,
            "message": "Connection test passed."
            if ok
            else "Connection test failed; provider details were withheld.",
        }
    )
    return 0 if ok else 2


def _command_provider_models(_args: argparse.Namespace) -> int:
    provider = _provider()
    models = asyncio.run(provider.list_models())
    _print_json({"models": models})
    return 0


def _command_history_list(args: argparse.Namespace) -> int:
    records = TaskStore().list(status=args.status, limit=args.limit)
    _print_json(
        [
            {
                "task_id": task.task_id,
                "status": task.status.value,
                "mode": task.mode.value,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
                "request": task.request[:180],
                "step_count": len(task.steps),
                "result": task.result,
                "error": task.error,
            }
            for task in records
        ]
    )
    return 0


def _command_history_export(args: argparse.Namespace) -> int:
    print(TaskStore().export(task_id=args.task_id))
    return 0


def _command_history_delete(args: argparse.Namespace) -> int:
    deleted = TaskStore().delete(args.task_id)
    _print_json({"deleted": deleted, "task_id": args.task_id})
    return 0 if deleted else 1


def _command_history_purge(args: argparse.Namespace) -> int:
    statuses = [TaskStatus(value) for value in args.status] if args.status else None
    deleted = TaskStore().purge(older_than=args.before, statuses=statuses)
    _print_json({"deleted_records": deleted, "before": args.before})
    return 0


def _command_privacy_clear_screenshots(_args: argparse.Namespace) -> int:
    deleted = DesktopObserver.clear_screenshots()
    _print_json({"deleted_screenshots": deleted})
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uthyagent", description="Local-first Linux desktop computer-use agent"
    )
    parser.add_argument("--version", action="version", version=f"UthyAgent {__version__}")
    commands = parser.add_subparsers(dest="command")

    check = commands.add_parser(
        "check", help="inspect session and optional capability availability"
    )
    check.set_defaults(handler=_command_check)

    observe = commands.add_parser("observe", help="inspect accessible desktop state without acting")
    observe.add_argument(
        "--ocr",
        action="store_true",
        help="capture a local screenshot and run Tesseract OCR when available",
    )
    observe.set_defaults(handler=_command_observe)

    run = commands.add_parser("run", help="run a task with a selected safety mode")
    run.add_argument("request", help="natural-language task request")
    run.add_argument(
        "--mode", choices=[mode.value for mode in RunMode], default=RunMode.OBSERVE.value
    )
    run.add_argument(
        "--allowed-app",
        action="append",
        help="application name allowed in restricted mode (repeatable)",
    )
    run.add_argument("--max-steps", type=int, default=20)
    run.add_argument(
        "--ocr", action="store_true", help="capture a local screenshot and run OCR when available"
    )
    run.set_defaults(handler=_command_run)

    provider = commands.add_parser("provider", help="configure and test an AI provider")
    provider_commands = provider.add_subparsers(dest="provider_command", required=True)
    configure = provider_commands.add_parser(
        "configure", help="save endpoint/model and an optional keyring secret"
    )
    configure.add_argument("--base-url", required=True)
    configure.add_argument("--model", required=True)
    configure.add_argument("--timeout", type=float, default=30.0)
    configure.add_argument(
        "--no-key", action="store_true", help="do not prompt for or save an API key"
    )
    configure.set_defaults(handler=_command_provider_configure)
    test = provider_commands.add_parser("test", help="test provider model-list endpoint")
    test.set_defaults(handler=_command_provider_test)
    models = provider_commands.add_parser(
        "models", help="list provider models and declared metadata"
    )
    models.set_defaults(handler=_command_provider_models)

    history = commands.add_parser("history", help="search, export, and delete local task history")
    history_commands = history.add_subparsers(dest="history_command", required=True)
    list_cmd = history_commands.add_parser("list", help="list task summaries")
    list_cmd.add_argument("--status", choices=[status.value for status in TaskStatus])
    list_cmd.add_argument("--limit", type=int, default=50)
    list_cmd.set_defaults(handler=_command_history_list)
    export_cmd = history_commands.add_parser("export", help="export redacted JSON history")
    export_cmd.add_argument("--task-id")
    export_cmd.set_defaults(handler=_command_history_export)
    delete_cmd = history_commands.add_parser("delete", help="delete one task by ID")
    delete_cmd.add_argument("task_id")
    delete_cmd.set_defaults(handler=_command_history_delete)
    purge_cmd = history_commands.add_parser(
        "purge", help="delete records older than an ISO timestamp"
    )
    purge_cmd.add_argument(
        "--before",
        required=True,
        help="ISO-8601 timestamp (records updated before this are deleted)",
    )
    purge_cmd.add_argument(
        "--status", action="append", choices=[status.value for status in TaskStatus]
    )
    purge_cmd.set_defaults(handler=_command_history_purge)

    privacy = commands.add_parser("privacy", help="delete local visual artifacts")
    privacy_commands = privacy.add_subparsers(dest="privacy_command", required=True)
    clear_screenshots = privacy_commands.add_parser(
        "clear-screenshots", help="delete cached UthyAgent screenshots"
    )
    clear_screenshots.set_defaults(handler=_command_privacy_clear_screenshots)
    return parser


def _launch_desktop() -> int:
    try:
        import gi  # type: ignore

        gi.require_version("Gtk", "4.0")
        from gi.repository import GLib, Gtk  # type: ignore

        from uthyagent.ui.window import UthyWindow
    except (ImportError, ValueError, RuntimeError) as exc:
        print(f"Cannot start the graphical interface: {exc}", file=sys.stderr)
        print(
            "Install GTK4 and PyGObject from your Linux distribution, then run `uthyagent` in a graphical session.",
            file=sys.stderr,
        )
        return 2

    application = Gtk.Application(application_id="com.uthyagent.Desktop")
    view_holder: dict[str, Any] = {
        "view": None,
        "thread": None,
        "event": None,
        "loop": None,
        "pending": None,
    }

    def activate(app: Any) -> None:
        def on_update(task: Any, message: str) -> None:
            def update() -> bool:
                view = view_holder["view"]
                if view is not None:
                    view.set_status(f"{task.status.value}: {message[:120]}")
                    view.set_desktop_status(
                        f"Active application: {task.active_application or 'not identified'}"
                    )
                    view.add_timeline(message)
                return GLib.SOURCE_REMOVE

            GLib.idle_add(update)

        async def approve_action(action: Any, decision: Any, state: Any, index: int) -> bool:
            event = threading.Event()
            view = view_holder["view"]
            if view is None:
                return False
            view_holder["pending"] = event
            details = action.type.value
            if action.target:
                details += f" on {action.target[:80]}"
            elif action.x is not None and action.y is not None:
                details += f" at ({action.x}, {action.y})"
            if action.type.value == "type_text":
                details += f" ({len(action.text or '')} characters; content hidden)"
            if action.rationale:
                details += f" — {action.rationale[:160]}"

            def show() -> bool:
                view.set_status("Approval required")
                view.set_approval_pending(True)
                view.add_timeline(f"Proposed action {index}: {details}. {decision.reason}")
                return GLib.SOURCE_REMOVE

            GLib.idle_add(show)
            approved = await asyncio.to_thread(event.wait, 90.0)
            GLib.idle_add(view.set_approval_pending, False)
            if view_holder.get("pending") is event:
                view_holder["pending"] = None
            return approved

        def approve() -> None:
            event = view_holder.get("pending")
            if event is not None:
                view_holder["view"].set_approval_pending(False)
                event.set()

        def stop() -> None:
            loop = view_holder.get("loop")
            event = view_holder.get("event")
            if loop is not None and event is not None:
                loop.call_soon_threadsafe(event.set)
            view = view_holder.get("view")
            if view is not None:
                view.set_status("Stop requested")

        def submit(request: str, mode_value: str) -> None:
            if not request.strip():
                view.set_status("Enter a task request first")
                return
            current = view_holder.get("thread")
            if current is not None and current.is_alive():
                view.set_status("A task is already running")
                return
            mode = RunMode(mode_value)
            try:
                planner = None if mode is RunMode.OBSERVE else _provider()
                backend = None if mode is RunMode.OBSERVE else X11Backend()
                if mode is RunMode.RESTRICTED:
                    raise RuntimeError(
                        "Restricted mode needs an application allowlist; configure it in settings before using this mode."
                    )
                engine = TaskEngine(
                    observer=DesktopObserver(),
                    planner=planner,
                    automation=backend,
                    safety=SafetyPolicy(),
                    store=TaskStore(),
                    approval_callback=approve_action,
                    on_update=on_update,
                )
            except Exception as exc:
                view.set_status(f"Setup error: {type(exc).__name__}: {exc}")
                return

            def worker() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                cancel_event = asyncio.Event()
                view_holder["loop"] = loop
                view_holder["event"] = cancel_event
                try:
                    result = loop.run_until_complete(
                        engine.run(request, mode, cancel_event=cancel_event)
                    )
                    on_update(result, result.result or result.error or result.status.value)
                finally:
                    view_holder["event"] = None
                    view_holder["loop"] = None
                    loop.close()

            thread = threading.Thread(target=worker, name="uthyagent-task", daemon=True)
            view_holder["thread"] = thread
            view.set_status("Task queued")
            thread.start()

        view = UthyWindow(application=app, on_submit=submit, on_stop=stop, on_approve=approve)
        view_holder["view"] = view
        try:
            view.set_provider_status(_provider_status_label())
        except (OSError, ValueError, RuntimeError):
            view.set_provider_status("Provider status unavailable")
        view.present()

    application.connect("activate", activate)
    return int(application.run([]))


def main(argv: list[str] | None = None) -> int:
    args_list = sys.argv[1:] if argv is None else argv
    parser = _build_parser()
    if not args_list:
        return _launch_desktop()
    args = parser.parse_args(args_list)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    try:
        return int(handler(args))
    except (ValueError, RuntimeError, SecretStoreError, OSError) as exc:
        print(f"uthyagent: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
