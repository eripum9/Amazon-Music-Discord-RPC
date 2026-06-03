import json

from config import SENSITIVE_CONFIG_KEYS
from updater import SHA256_RE

INSTALLER_NAME = "AmazonMusicRPC_Setup.exe"
RELEASE_COMPATIBILITY_TERMS = (
    "compatibility",
    "microsoft store",
    "enhanced metadata",
    "fallback",
)


def sensitive_config_values(config):
    values = []
    for key in sorted(SENSITIVE_CONFIG_KEYS):
        value = str((config or {}).get(key, "") or "")
        if len(value) >= 6:
            values.append((key, value))
    return values


def redaction_audit(config, payloads):
    leaks = []
    for label, payload in (payloads or {}).items():
        if isinstance(payload, str):
            text = payload
        else:
            text = json.dumps(payload, sort_keys=True)
        for key, secret in sensitive_config_values(config):
            if secret in text:
                leaks.append({"key": key, "location": label})
    return {
        "ok": not leaks,
        "leaks": leaks,
        "checked_keys": [key for key, _ in sensitive_config_values(config)],
    }


def token_storage_review(config):
    return {
        "storage": "local-secret-file-dpapi",
        "present_keys": [key for key, _ in sensitive_config_values(config)],
        "redaction_required": True,
        "at_rest_protection": "DPAPI on Windows",
        "future_hardening": ["Windows Credential Manager"],
    }


def release_notes_trust_errors(notes_text, installer_sha256="", installer_name=INSTALLER_NAME):
    text = str(notes_text or "")
    lowered = text.lower()
    errors = []
    if installer_name.lower() not in lowered:
        errors.append("Release notes do not mention AmazonMusicRPC_Setup.exe")
    if not SHA256_RE.search(text):
        errors.append("Release notes do not contain a SHA256 hash")
    if installer_sha256 and installer_sha256.lower() not in lowered:
        errors.append("Release notes do not contain the installer SHA256")
    if not any(term in lowered for term in RELEASE_COMPATIBILITY_TERMS):
        errors.append("Release notes do not include a compatibility note")
    if not _has_changelog_bullet(text):
        errors.append("Release notes do not include a changelog bullet")
    return errors


def _has_changelog_bullet(text):
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")) and any(char.isalpha() for char in stripped):
            return True
    return False
