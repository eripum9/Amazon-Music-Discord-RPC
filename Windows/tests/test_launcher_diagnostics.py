# MIT License - Copyright (c) 2026 eripum9

import launcher_diagnostics


def test_launcher_diagnostics_classify_user_facing_failures():
    assert launcher_diagnostics.classify_launcher_error("Package was not found. 0x80073CF1") == "package_not_found"
    assert launcher_diagnostics.classify_launcher_error("unknown option --remote-debugging-port=52856") == "unsupported_debug_flag"
    assert launcher_diagnostics.classify_launcher_error("The system cannot find the file specified") == "path_not_found"
    assert launcher_diagnostics.launcher_attempt_failure(
        {"method": "override-aumid", "value": "Amazon.Music"},
        "unknown option --remote-debugging-port=52856",
    ) == "override-aumid Amazon.Music: launcher does not support enhanced metadata flags"


def test_launcher_failure_advice_prioritises_actionable_next_step():
    message = launcher_diagnostics.format_launcher_failure(
        [
            "auto-aumid Amazon.Music: package was not found",
            "override-aumid Amazon.Music: launcher does not support enhanced metadata flags",
        ],
        "Could not launch Amazon Music with enhanced metadata.",
    )
    assert "does not accept enhanced metadata flags" in message
    assert "Last attempts:" in message


def test_pyinstaller_environment_diagnostics_match_updater_cleanup():
    env = {
        "_PYI_APPLICATION_HOME_DIR": r"C:\Temp\_MEI123",
        "_MEIPASS2": r"C:\Temp\_MEI123",
        "SAFE_KEY": "value",
    }
    assert launcher_diagnostics.pyinstaller_environment_keys(env) == ["_PYI_APPLICATION_HOME_DIR", "_MEIPASS2"]
    assert "stale PyInstaller state" in launcher_diagnostics.updater_handoff_diagnostic(env)
