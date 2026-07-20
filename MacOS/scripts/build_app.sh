#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
PROJECT_DIR="$(cd -- "${MACOS_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${PROJECT_DIR}/.venv/bin/python}"
SPEC_PATH="${MACOS_DIR}/AmazonMusicRPC.spec"
DIST_DIR="${MACOS_DIR}/dist"
WORK_DIR="${MACOS_DIR}/build/pyinstaller"
APP_PATH="${DIST_DIR}/Amazon Music RPC.app"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "The macOS application bundle must be built on macOS." >&2
    exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "Python was not found at ${PYTHON_BIN}. Set PYTHON_BIN to a Python 3.12 executable." >&2
    exit 1
fi

if [[ ! -f "${MACOS_DIR}/main.py" ]]; then
    echo "Application entrypoint is missing: ${MACOS_DIR}/main.py" >&2
    exit 1
fi

if ! "${PYTHON_BIN}" -c 'import PyInstaller' >/dev/null 2>&1; then
    echo "PyInstaller is not installed. Run:" >&2
    echo "  ${PYTHON_BIN} -m pip install -r ${MACOS_DIR}/requirements-build.txt" >&2
    exit 1
fi

if [[ -z "${APP_VERSION:-}" ]]; then
    APP_VERSION="$(git -C "${PROJECT_DIR}" describe --tags --abbrev=0 2>/dev/null | /usr/bin/sed 's/^v//' || true)"
    APP_VERSION="${APP_VERSION:-0.1.0}"
fi
if [[ -z "${APP_BUILD:-}" ]]; then
    APP_BUILD="$(git -C "${PROJECT_DIR}" rev-list --count HEAD 2>/dev/null || true)"
    APP_BUILD="${APP_BUILD:-1}"
fi

if [[ ! "${APP_VERSION}" =~ ^[0-9]+([.][0-9]+){0,2}$ ]]; then
    echo "APP_VERSION must contain one to three dot-separated integers; got ${APP_VERSION}." >&2
    exit 1
fi
if [[ ! "${APP_BUILD}" =~ ^[0-9]+([.][0-9]+){0,2}$ ]]; then
    echo "APP_BUILD must contain one to three dot-separated integers; got ${APP_BUILD}." >&2
    exit 1
fi

export APP_VERSION APP_BUILD
export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-12.0}"
export PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR=1

"${SCRIPT_DIR}/generate_icon.sh"
/bin/mkdir -p -- "${DIST_DIR}" "${WORK_DIR}"

echo "Building Amazon Music RPC ${APP_VERSION} (${APP_BUILD})"
echo "Python architecture: $("${PYTHON_BIN}" -c 'import platform; print(platform.machine())')"
if [[ -n "${MACOS_CODESIGN_IDENTITY:-}" ]]; then
    echo "Signing identity: ${MACOS_CODESIGN_IDENTITY}"
else
    echo "Signing identity: ad hoc (prototype only)"
fi

"${PYTHON_BIN}" -m PyInstaller \
    --noconfirm \
    --clean \
    --workpath "${WORK_DIR}" \
    --distpath "${DIST_DIR}" \
    "${SPEC_PATH}"

/usr/bin/plutil -lint "${APP_PATH}/Contents/Info.plist"
/usr/bin/codesign --verify --deep --strict --verbose=2 "${APP_PATH}"

BUNDLE_ID="$(/usr/bin/plutil -extract CFBundleIdentifier raw "${APP_PATH}/Contents/Info.plist")"
BUNDLE_VERSION="$(/usr/bin/plutil -extract CFBundleShortVersionString raw "${APP_PATH}/Contents/Info.plist")"
BUNDLE_BUILD="$(/usr/bin/plutil -extract CFBundleVersion raw "${APP_PATH}/Contents/Info.plist")"
BUNDLE_AGENT="$(/usr/bin/plutil -extract LSUIElement raw "${APP_PATH}/Contents/Info.plist")"
if [[ "${BUNDLE_ID}" != "io.github.eripum9.amazon-music-rpc" ]]; then
    echo "Unexpected bundle identifier: ${BUNDLE_ID}" >&2
    exit 1
fi
if [[ "${BUNDLE_VERSION}" != "${APP_VERSION}" || "${BUNDLE_BUILD}" != "${APP_BUILD}" ]]; then
    echo "Built bundle version does not match APP_VERSION/APP_BUILD." >&2
    exit 1
fi
if [[ "${BUNDLE_AGENT}" != "true" ]]; then
    echo "LSUIElement must remain enabled for the menu-bar application." >&2
    exit 1
fi
if [[ -n "${MACOS_CODESIGN_IDENTITY:-}" ]]; then
    SIGNATURE_DETAILS="$(/usr/bin/codesign -dv --verbose=4 "${APP_PATH}" 2>&1)"
    if ! /usr/bin/grep -Fqx "Authority=${MACOS_CODESIGN_IDENTITY}" <<< "${SIGNATURE_DETAILS}"; then
        echo "The app bundle was not signed by ${MACOS_CODESIGN_IDENTITY}." >&2
        exit 1
    fi
fi

echo "Built ${APP_PATH}"
