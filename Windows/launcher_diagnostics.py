def clean_text(value):
    return " ".join(str(value or "").split())


def launcher_candidate_label(candidate):
    return f"{candidate.get('method', 'unknown')} {candidate.get('value', '')}".strip()


def classify_launcher_error(error):
    text = clean_text(error).lower()
    if not text:
        return "launch_failed"
    if "0x80073cf1" in text or "package was not found" in text or "package could not be found" in text:
        return "package_not_found"
    if "powershell" in text and ("not recognized" in text or "not found" in text or "cannot find" in text):
        return "powershell_unavailable"
    if (
        ("remote-debugging-port" in text and (
            "unknown option" in text
            or "invalid option" in text
            or "unrecognized option" in text
            or "unbekannte option" in text
            or "ungültige option" in text
            or "不明なオプション" in text
        ))
        or "does not support enhanced metadata flags" in text
    ):
        return "unsupported_debug_flag"
    if "metadata target did not appear" in text:
        return "metadata_target_missing"
    if "python" in text and ("_mei" in text or "python314.dll" in text):
        return "stale_pyinstaller_temp"
    if "system cannot find the file specified" in text or "指定されたファイルが見つかりません" in text:
        return "path_not_found"
    return "unknown"


def launcher_attempt_failure(candidate, error):
    text = clean_text(error)
    label = launcher_candidate_label(candidate)
    category = classify_launcher_error(text)
    if category == "package_not_found":
        return f"{label}: package was not found"
    if category == "unsupported_debug_flag":
        return f"{label}: launcher does not support enhanced metadata flags"
    if category == "path_not_found":
        return f"{label}: launcher path was not found"
    if not text:
        text = "launch failed"
    return f"{label}: {text}"


def launcher_failure_advice(attempts):
    categories = {classify_launcher_error(attempt) for attempt in attempts}
    if "unsupported_debug_flag" in categories:
        return "The selected Amazon Music launcher does not accept enhanced metadata flags. Install the Microsoft Store version or disable enhanced metadata."
    if "package_not_found" in categories:
        return "The selected Amazon Music Store package was not found. Install the Microsoft Store version or paste a valid launcher ID from Get-StartApps."
    if "path_not_found" in categories:
        return "The selected launcher path does not exist. Clear the launcher override or choose the installed Amazon Music launcher."
    if "powershell_unavailable" in categories:
        return "Windows PowerShell could not be started, so launcher discovery cannot run."
    if "metadata_target_missing" in categories:
        return "Amazon Music opened, but the enhanced metadata page did not appear on the selected port."
    return ""


def format_launcher_failure(attempts, help_text):
    if not attempts:
        return help_text
    advice = launcher_failure_advice(attempts)
    parts = [help_text]
    if advice:
        parts.append(advice)
    parts.append(f"Last attempts: {'; '.join(attempts[-3:])}")
    return " ".join(parts)


def pyinstaller_environment_keys(env):
    keys = []
    for key, value in dict(env or {}).items():
        upper = str(key).upper()
        text = str(value or "")
        if upper == "_MEIPASS2" or upper.startswith("_PYI_") or upper.startswith("PYINSTALLER_") or "_MEI" in text:
            keys.append(key)
    return keys


def updater_handoff_diagnostic(env):
    keys = pyinstaller_environment_keys(env)
    if not keys:
        return ""
    return f"Installer launch environment contains stale PyInstaller state: {', '.join(sorted(keys))}"
