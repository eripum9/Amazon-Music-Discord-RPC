#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
PROJECT_DIR="$(cd -- "${MACOS_DIR}/.." && pwd)"
SOURCE_ICON="${1:-${PROJECT_DIR}/Windows/icon.png}"
OUTPUT_ICON="${2:-${MACOS_DIR}/build/assets/AmazonMusicRPC.icns}"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "Icon generation requires macOS (sips and iconutil)." >&2
    exit 1
fi

for tool in /usr/bin/sips /usr/bin/iconutil; do
    if [[ ! -x "${tool}" ]]; then
        echo "Required tool is unavailable: ${tool}" >&2
        exit 1
    fi
done

if [[ ! -f "${SOURCE_ICON}" ]]; then
    echo "Source icon does not exist: ${SOURCE_ICON}" >&2
    exit 1
fi

OUTPUT_DIR="$(dirname -- "${OUTPUT_ICON}")"
/bin/mkdir -p -- "${OUTPUT_DIR}"
TEMP_DIR="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/amazon-music-rpc-icon.XXXXXX")"

cleanup() {
    /bin/rm -rf -- "${TEMP_DIR}"
}
trap cleanup EXIT

MASTER_ICON="${TEMP_DIR}/master.png"
ICONSET_DIR="${TEMP_DIR}/AmazonMusicRPC.iconset"
/bin/mkdir -- "${ICONSET_DIR}"

/usr/bin/sips -s format png "${SOURCE_ICON}" --out "${MASTER_ICON}" >/dev/null

read_dimension() {
    /usr/bin/sips -g "$1" "${MASTER_ICON}" 2>/dev/null | /usr/bin/awk -F': ' -v key="$1" '$1 ~ key {print $2}'
}

WIDTH="$(read_dimension pixelWidth)"
HEIGHT="$(read_dimension pixelHeight)"
if [[ ! "${WIDTH}" =~ ^[0-9]+$ || ! "${HEIGHT}" =~ ^[0-9]+$ ]]; then
    echo "Could not determine the source icon dimensions." >&2
    exit 1
fi
if (( WIDTH < 1024 || HEIGHT < 1024 )); then
    echo "The source icon must be at least 1024x1024; got ${WIDTH}x${HEIGHT}." >&2
    exit 1
fi

make_icon() {
    local pixels="$1"
    local filename="$2"
    /usr/bin/sips -z "${pixels}" "${pixels}" "${MASTER_ICON}" \
        --out "${ICONSET_DIR}/${filename}" >/dev/null
}

make_icon 16 icon_16x16.png
make_icon 32 icon_16x16@2x.png
make_icon 32 icon_32x32.png
make_icon 64 icon_32x32@2x.png
make_icon 128 icon_128x128.png
make_icon 256 icon_128x128@2x.png
make_icon 256 icon_256x256.png
make_icon 512 icon_256x256@2x.png
make_icon 512 icon_512x512.png
make_icon 1024 icon_512x512@2x.png

TEMP_ICNS="${TEMP_DIR}/AmazonMusicRPC.icns"
/usr/bin/iconutil -c icns "${ICONSET_DIR}" -o "${TEMP_ICNS}"
/usr/bin/install -m 0644 "${TEMP_ICNS}" "${OUTPUT_ICON}"

echo "Created ${OUTPUT_ICON} from ${SOURCE_ICON}"
