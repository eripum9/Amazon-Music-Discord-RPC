# MIT License - Copyright (c) 2026 eripum9

import sys

import pytest

import release_smoke


def test_pillow_expectation_follows_declared_pin(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_text("requests==2.34.2\nPillow==14.0.1\n", encoding="utf-8")
    assert release_smoke.declared_pillow_version(path) == "14.0.1"


@pytest.mark.parametrize("declaration", [
    "requests==2.34.2",
    "Pillow",
    "Pillow>=13",
    "Pillow==13.*",
    "Pillow==13.0.0\nPillow==14.0.0",
])
def test_pillow_expectation_rejects_ambiguous_or_missing_pin(tmp_path, declaration):
    path = tmp_path / "requirements.txt"
    path.write_text(declaration, encoding="utf-8")
    with pytest.raises(ValueError):
        release_smoke.declared_pillow_version(path)


@pytest.mark.parametrize("embedded, expected_exit", [("14.0.1", 0), ("13.0.0", 1)])
def test_packaged_smoke_checks_source_pin_without_manual_version(
    monkeypatch, tmp_path, embedded, expected_exit, capsys
):
    (tmp_path / "requirements.txt").write_text("Pillow==14.0.1", encoding="utf-8")
    executable = tmp_path / "AmazonMusicRPC.exe"
    executable.touch()
    monkeypatch.setattr(release_smoke, "WINDOWS_DIR", tmp_path)
    monkeypatch.setattr(release_smoke, "installer_version", lambda: release_smoke.APP_VERSION)
    monkeypatch.setattr(release_smoke, "embedded_pillow_version", lambda path: embedded)
    monkeypatch.setattr(sys, "argv", ["release_smoke", "--allow-missing-installer", "--executable", str(executable)])
    assert release_smoke.main() == expected_exit
    if expected_exit:
        assert "Packaged Pillow mismatch: expected 14.0.1, found 13.0.0" in capsys.readouterr().err
