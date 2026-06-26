# MIT License - Copyright (c) 2026 eripum9

import argparse
import json
import re
import sys
from pathlib import Path

WINDOWS_DIR = Path(__file__).resolve().parent
if str(WINDOWS_DIR) not in sys.path:
    sys.path.insert(0, str(WINDOWS_DIR))

from config import APP_VERSION
from security_trust import release_notes_trust_errors
from updater import file_sha256

VERSION_RE = re.compile(r'#define\s+MyAppVersion\s+"([^"]+)"')


def installer_version():
    script = WINDOWS_DIR / "installer.iss"
    match = VERSION_RE.search(script.read_text(encoding="utf-8"))
    return match.group(1) if match else ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", default=str(WINDOWS_DIR / "installer_output" / "AmazonMusicRPC_Setup.exe"))
    parser.add_argument("--release-notes", default="")
    parser.add_argument("--allow-missing-installer", action="store_true")
    args = parser.parse_args()

    errors = []
    smoke = {
        "app_version": APP_VERSION,
        "installer_version": installer_version(),
        "installer": str(Path(args.installer)),
        "sha256": "",
    }

    if smoke["app_version"] != smoke["installer_version"]:
        errors.append(f"Version mismatch: config={smoke['app_version']} installer={smoke['installer_version'] or 'missing'}")

    installer = Path(args.installer)
    if installer.exists():
        smoke["sha256"] = file_sha256(installer)
    elif not args.allow_missing_installer:
        errors.append(f"Installer not found: {installer}")

    if args.release_notes:
        notes = Path(args.release_notes)
        if not notes.exists():
            errors.append(f"Release notes not found: {notes}")
        else:
            errors.extend(release_notes_trust_errors(notes.read_text(encoding="utf-8"), smoke["sha256"]))

    print(json.dumps(smoke, indent=2))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
