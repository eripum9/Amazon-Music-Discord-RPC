# MIT License - Copyright (c) 2026 eripum9

import os
import subprocess
import sys


class WindowController:
    def __init__(self, tasks, script_dir, environment_factory, config_loader, rpc_snapshot, config_changed):
        self._tasks = tasks
        self._script_dir = script_dir
        self._environment_factory = environment_factory
        self._config_loader = config_loader
        self._rpc_snapshot = rpc_snapshot
        self._config_changed = config_changed
        self._settings = None
        self._diagnostics = None

    def _command(self, flag, source_file):
        if getattr(sys, "frozen", False):
            return [sys.executable, flag]
        return [sys.executable, os.path.join(self._script_dir, source_file)]

    def _spawn(self, flag, source_file, environment):
        return subprocess.Popen(
            self._command(flag, source_file),
            creationflags=0x08000000 if os.name == "nt" else 0,
            env=environment,
        )

    def open_settings(self):
        if self._settings and self._settings.poll() is None:
            return self._settings
        previous = self._config_loader()
        self._settings = self._spawn("--settings", "settings_ui.py", self._environment_factory(True))
        self._tasks.start("settings-monitor", self._monitor_settings, args=(previous,))
        return self._settings

    def _monitor_settings(self, previous):
        previous_rpc = self._rpc_snapshot(previous)
        if self._tasks.wait(2):
            return
        for _ in range(300):
            process_closed = not self._settings or self._settings.poll() is not None
            try:
                current = self._config_loader()
            except Exception:
                if process_closed:
                    return
                if self._tasks.wait(1):
                    return
                continue
            current_rpc = self._rpc_snapshot(current)
            if current != previous:
                self._config_changed(previous, current, previous_rpc, current_rpc)
                previous = dict(current)
                previous_rpc = dict(current_rpc)
            if process_closed:
                return
            if self._tasks.wait(1):
                return

    def open_diagnostics(self):
        if self._diagnostics and self._diagnostics.poll() is None:
            return self._diagnostics
        self._diagnostics = self._spawn("--diagnostics", "diagnostics_ui.py", self._environment_factory(False))
        return self._diagnostics

    def close(self):
        for process in (self._settings, self._diagnostics):
            if not process or process.poll() is not None:
                continue
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        self._settings = None
        self._diagnostics = None

    def snapshot(self):
        return {
            "settings_open": bool(self._settings and self._settings.poll() is None),
            "diagnostics_open": bool(self._diagnostics and self._diagnostics.poll() is None),
        }
