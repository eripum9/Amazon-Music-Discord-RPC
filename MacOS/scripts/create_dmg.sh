#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
PROJECT_DIR="$(cd -- "${MACOS_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${PROJECT_DIR}/.venv/bin/python}"
APP_PATH="${1:-${MACOS_DIR}/dist/Amazon Music RPC.app}"
OUTPUT_PATH="${2:-${MACOS_DIR}/dist/Amazon-Music-RPC.dmg}"
SETTINGS_PATH="${MACOS_DIR}/dmg_settings.py"
VOLUME_NAME="Amazon Music RPC"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "DMG creation requires macOS." >&2
    exit 1
fi
if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "Python was not found at ${PYTHON_BIN}." >&2
    exit 1
fi
if [[ ! -d "${APP_PATH}" || ! -f "${APP_PATH}/Contents/Info.plist" ]]; then
    echo "Application bundle does not exist: ${APP_PATH}" >&2
    echo "Run ${SCRIPT_DIR}/build_app.sh first." >&2
    exit 1
fi
if [[ "${OUTPUT_PATH}" != *.dmg ]]; then
    echo "Output path must end in .dmg: ${OUTPUT_PATH}" >&2
    exit 1
fi
if ! "${PYTHON_BIN}" -c 'import dmgbuild' >/dev/null 2>&1; then
    echo "dmgbuild is not installed. Run:" >&2
    echo "  ${PYTHON_BIN} -m pip install -r ${MACOS_DIR}/requirements-build.txt" >&2
    exit 1
fi
if [[ -n "${MACOS_NOTARYTOOL_PROFILE:-}" && -z "${MACOS_CODESIGN_IDENTITY:-}" ]]; then
    echo "MACOS_NOTARYTOOL_PROFILE requires MACOS_CODESIGN_IDENTITY and a Developer ID build." >&2
    exit 1
fi

/usr/bin/plutil -lint "${APP_PATH}/Contents/Info.plist" >/dev/null
/usr/bin/codesign --verify --deep --strict "${APP_PATH}"
if [[ -n "${MACOS_CODESIGN_IDENTITY:-}" ]]; then
    SIGNATURE_DETAILS="$(/usr/bin/codesign -dv --verbose=4 "${APP_PATH}" 2>&1)"
    if ! /usr/bin/grep -Fqx "Authority=${MACOS_CODESIGN_IDENTITY}" <<< "${SIGNATURE_DETAILS}"; then
        echo "The app bundle was not signed by ${MACOS_CODESIGN_IDENTITY}." >&2
        echo "Rebuild it with the same MACOS_CODESIGN_IDENTITY before creating a release DMG." >&2
        exit 1
    fi
fi

OUTPUT_DIR="$(dirname -- "${OUTPUT_PATH}")"
/bin/mkdir -p -- "${OUTPUT_DIR}"
TEMP_DIR="$(/usr/bin/mktemp -d "${OUTPUT_DIR}/.amazon-music-rpc-dmg.XXXXXX")"
TEMP_DMG="${TEMP_DIR}/Amazon-Music-RPC.dmg"

cleanup() {
    /bin/rm -rf -- "${TEMP_DIR}"
}
trap cleanup EXIT

"${PYTHON_BIN}" -m dmgbuild \
    -s "${SETTINGS_PATH}" \
    -D "app=${APP_PATH}" \
    "${VOLUME_NAME}" \
    "${TEMP_DMG}"

/usr/bin/hdiutil verify "${TEMP_DMG}" >/dev/null

if [[ -n "${MACOS_CODESIGN_IDENTITY:-}" ]]; then
    /usr/bin/codesign --force --timestamp \
        --sign "${MACOS_CODESIGN_IDENTITY}" "${TEMP_DMG}"
    /usr/bin/codesign --verify --strict --verbose=2 "${TEMP_DMG}"
fi

/bin/mv -f -- "${TEMP_DMG}" "${OUTPUT_PATH}"

if [[ -n "${MACOS_NOTARYTOOL_PROFILE:-}" ]]; then
    /usr/bin/xcrun notarytool submit "${OUTPUT_PATH}" \
        --keychain-profile "${MACOS_NOTARYTOOL_PROFILE}" --wait
    /usr/bin/xcrun stapler staple "${OUTPUT_PATH}"
    /usr/bin/xcrun stapler validate "${OUTPUT_PATH}"
fi

CHECKSUM_PATH="${OUTPUT_PATH}.sha256"
CHECKSUM_TEMP="${TEMP_DIR}/$(basename -- "${CHECKSUM_PATH}")"
CHECKSUM_VALUE="$(/usr/bin/shasum -a 256 "${OUTPUT_PATH}" | /usr/bin/awk '{print $1}')"
/usr/bin/printf '%s  %s\n' "${CHECKSUM_VALUE}" "$(basename -- "${OUTPUT_PATH}")" > "${CHECKSUM_TEMP}"
/bin/mv -f -- "${CHECKSUM_TEMP}" "${CHECKSUM_PATH}"

echo "Created ${OUTPUT_PATH}"
echo "Created ${CHECKSUM_PATH}"
