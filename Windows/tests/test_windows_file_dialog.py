# MIT License - Copyright (c) 2026 eripum9

from types import SimpleNamespace

import pytest

import windows_file_dialog


def test_dialog_decodes_non_ascii_path_as_utf8(monkeypatch):
    path = "C:\\Users\\J\u00f6rg\\\u97f3\u697d\\report.zip"

    def run(command, **kwargs):
        assert kwargs["text"] is True
        assert kwargs["encoding"] == "utf-8"
        return SimpleNamespace(returncode=0, stdout=(path + "\r\n").encode("utf-8").decode(kwargs["encoding"]), stderr="")

    monkeypatch.setattr(windows_file_dialog.subprocess, "run", run)
    assert windows_file_dialog.save_file_dialog("Export", "report.zip", "zip", "ZIP|*.zip") == path
    assert windows_file_dialog.open_file_dialog("Import", "ZIP|*.zip") == path


def test_dialog_cancellation_and_errors_preserve_contract(monkeypatch):
    monkeypatch.setattr(windows_file_dialog.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""))
    assert windows_file_dialog._run_dialog("script") == ""
    monkeypatch.setattr(windows_file_dialog.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="dialog unavailable"))
    with pytest.raises(RuntimeError, match="dialog unavailable"):
        windows_file_dialog._run_dialog("script")
