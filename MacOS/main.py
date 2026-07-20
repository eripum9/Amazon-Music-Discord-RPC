# MIT License - Copyright (c) 2026 eripum9

"""macOS menu-bar application entrypoint."""

from __future__ import annotations

import signal
import sys
from pathlib import Path


if __package__ in (None, ""):
    PROJECT_DIR = Path(__file__).resolve().parent.parent
    if str(PROJECT_DIR) not in sys.path:
        sys.path.insert(0, str(PROJECT_DIR))
    from MacOS import config
    from MacOS.runtime import MacRuntime
    from MacOS.single_instance import SingleInstance
    from MacOS.ui import MacApplicationUI
else:
    from . import config
    from .runtime import MacRuntime
    from .single_instance import SingleInstance
    from .ui import MacApplicationUI

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from Windows.qt_tray_ui import QtTrayController
from Windows.structured_logging import StructuredLogTee, rotate_logs


class _CommandBridge(QObject):
    command_received = Signal(str)


def _icon_path():
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidates = (root / "icon.png", root / "Resources" / "icon.png")
    else:
        candidates = (Path(__file__).resolve().parent.parent / "Windows" / "icon.png",)
    return str(next((path for path in candidates if path.is_file()), candidates[0]))


def _install_logging():
    Path(config.CONFIG_DIR).mkdir(parents=True, exist_ok=True)
    try:
        rotate_logs(config.CONFIG_DIR, Path(config.LOG_PATH).name, 5)
        rotate_logs(config.CONFIG_DIR, Path(config.EVENT_LOG_PATH).name, 5)
    except OSError:
        pass
    original_out, original_err = sys.stdout, sys.stderr
    redaction_config = config.load_config()
    try:
        sys.stdout = StructuredLogTee(
            original_out,
            config.LOG_PATH,
            config.EVENT_LOG_PATH,
            "stdout",
            lambda value: config.redact_text(value, redaction_config),
        )
        sys.stderr = StructuredLogTee(
            original_err,
            config.LOG_PATH,
            config.EVENT_LOG_PATH,
            "stderr",
            lambda value: config.redact_text(value, redaction_config),
        )
    except OSError:
        sys.stdout, sys.stderr = original_out, original_err


def _secondary_command(arguments):
    if "--diagnostics" in arguments:
        return "diagnostics"
    return "settings"


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--version" in arguments:
        print(config.APP_VERSION)
        return 0

    _install_logging()
    app = QApplication.instance() or QApplication([sys.argv[0], *arguments])
    app.setApplicationName(config.APP_DISPLAY_NAME)
    app.setApplicationDisplayName(config.APP_DISPLAY_NAME)
    app.setOrganizationName("eripum9")
    app.setQuitOnLastWindowClosed(False)
    icon_path = _icon_path()
    if Path(icon_path).is_file():
        app.setWindowIcon(QIcon(icon_path))

    bridge = _CommandBridge()
    instance = SingleInstance(lambda command: bridge.command_received.emit(command))
    if not instance.acquire():
        instance.notify(_secondary_command(arguments))
        instance.close()
        return 0

    runtime = MacRuntime()
    tray_holder = {"controller": None}
    shutting_down = {"value": False}

    def open_amazon():
        import subprocess

        return subprocess.Popen(
            ["/usr/bin/open", "-a", "Amazon Music"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )

    def shutdown():
        if shutting_down["value"]:
            return
        shutting_down["value"] = True
        print("[App] Shutting down.")
        runtime.stop()
        ui.shutdown()
        instance.close()
        tray = tray_holder.get("controller")
        if tray:
            tray.stop()
        else:
            app.quit()

    ui = MacApplicationUI(
        app,
        runtime,
        icon_path,
        on_quit=shutdown,
        on_open_amazon=open_amazon,
    )

    callbacks = dict(ui.callbacks)
    callbacks.update(
        {
            "private": lambda: runtime.set_private_session(
                not bool(config.load_config().get("privacy_private_session"))
            ),
            "game_mode": lambda: runtime.set_game_mode(
                not bool(config.load_config().get("game_mode_enabled"))
            ),
            "toggle_rpc": lambda: runtime.set_rpc_enabled(not runtime.rpc_enabled),
        }
    )
    tray = QtTrayController(icon_path, callbacks, runtime.snapshot())
    tray_holder["controller"] = tray
    runtime.add_listener(tray.update_state, emit_current=True)

    def handle_command(command):
        if command in {"activate", "settings"}:
            ui.show_settings()
        elif command == "diagnostics":
            ui.show_diagnostics()
        elif command == "quit":
            shutdown()

    bridge.command_received.connect(handle_command)

    def signal_shutdown(_signal_number, _frame):
        QTimer.singleShot(0, shutdown)

    signal.signal(signal.SIGTERM, signal_shutdown)
    signal.signal(signal.SIGINT, signal_shutdown)
    app.aboutToQuit.connect(lambda: instance.close())

    runtime.start()
    saved = config.load_config()
    first_run = not saved.get("intro_seen") or not saved.get("setup_wizard_seen")
    if "--diagnostics" in arguments:
        QTimer.singleShot(0, ui.show_diagnostics)
    elif "--settings" in arguments or first_run or not saved.get("start_minimized", True):
        QTimer.singleShot(0, ui.show_settings)

    if saved.get("automatic_update_checks", True):
        def automatic_update_check():
            from MacOS.updater import check_for_update

            def done(update):
                if getattr(update, "available", False):
                    ui.check_updates()

            ui.run_background(check_for_update, done, lambda _error: None)

        QTimer.singleShot(5000, automatic_update_check)

    print(f"[App] {config.APP_DISPLAY_NAME} {config.APP_VERSION} started.")
    return tray.run()


if __name__ == "__main__":
    raise SystemExit(main())
