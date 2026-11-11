# MIT License - Copyright (c) 2026 eripum9

import argparse
import json
import re
import sys
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

WINDOWS_DIR = Path(__file__).resolve().parent
if str(WINDOWS_DIR) not in sys.path:
    sys.path.insert(0, str(WINDOWS_DIR))

from config import APP_VERSION
from security_trust import release_notes_trust_errors
from updater import _extract_sha256, file_sha256
from release_artifact import embedded_pillow_version

VERSION_RE = re.compile(r'#define\s+MyAppVersion\s+"([^"]+)"')


def declared_pillow_version(path=None):
    requirements = Path(path) if path is not None else WINDOWS_DIR / "requirements.txt"
    matches = []
    for line in requirements.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith(("#", "-")):
            continue
        requirement = Requirement(line)
        if requirement.name.casefold() == "pillow":
            matches.append(requirement)
    if len(matches) != 1:
        raise ValueError("Requirements must declare exactly one Pillow version")
    pins = list(matches[0].specifier)
    if len(pins) != 1 or pins[0].operator != "==" or "*" in pins[0].version:
        raise ValueError("Requirements must pin an exact Pillow version")
    return str(Version(pins[0].version))


def installer_version():
    script = WINDOWS_DIR / "installer.iss"
    match = VERSION_RE.search(script.read_text(encoding="utf-8"))
    return match.group(1) if match else ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", default=str(WINDOWS_DIR / "installer_output" / "AmazonMusicRPC_Setup.exe"))
    parser.add_argument("--release-notes", default="")
    parser.add_argument("--checksum", default="")
    parser.add_argument("--allow-missing-installer", action="store_true")
    parser.add_argument("--executable", default="")
    parser.add_argument("--expected-pillow", default="")
    args = parser.parse_args()

    errors = []
    smoke = {
        "app_version": APP_VERSION,
        "installer_version": installer_version(),
        "installer": str(Path(args.installer)),
        "checksum": "",
        "sha256": "",
        "embedded_pillow": "",
    }

    if smoke["app_version"] != smoke["installer_version"]:
        errors.append(f"Version mismatch: config={smoke['app_version']} installer={smoke['installer_version'] or 'missing'}")

    installer = Path(args.installer)
    if installer.exists():
        smoke["sha256"] = file_sha256(installer)
        checksum = Path(args.checksum) if args.checksum else Path(str(installer) + ".sha256")
        smoke["checksum"] = str(checksum)
        if not checksum.exists():
            errors.append(f"Checksum file not found: {checksum}")
        else:
            declared_sha256 = _extract_sha256(checksum.read_text(encoding="utf-8"), installer.name)
            if not declared_sha256:
                errors.append(f"Checksum file does not contain a SHA256 hash: {checksum}")
            elif declared_sha256 != smoke["sha256"]:
                errors.append(f"Checksum mismatch: expected {smoke['sha256']}, found {declared_sha256}")
    elif not args.allow_missing_installer:
        errors.append(f"Installer not found: {installer}")

    if args.executable:
        expected_pillow = args.expected_pillow
        if not expected_pillow:
            try:
                expected_pillow = declared_pillow_version()
            except (OSError, ValueError) as error:
                errors.append(f"Could not read required Pillow version: {error}")
        executable = Path(args.executable)
        if not executable.exists():
            errors.append(f"Executable not found: {executable}")
        else:
            try:
                smoke["embedded_pillow"] = embedded_pillow_version(executable)
            except Exception as error:
                errors.append(f"Could not inspect packaged Pillow: {error}")
            if expected_pillow and smoke["embedded_pillow"] != expected_pillow:
                errors.append(
                    f"Packaged Pillow mismatch: expected {expected_pillow}, found {smoke['embedded_pillow'] or 'unknown'}"
                )

    if args.release_notes:
        notes = Path(args.release_notes)
        if not notes.exists():
            errors.append(f"Release notes not found: {notes}")
        else:
            errors.extend(release_notes_trust_errors(notes.read_text(encoding="utf-8")))

    print(json.dumps(smoke, indent=2))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
