# MIT License - Copyright (c) 2026 eripum9

"""Windows adapter for the shared PySide6 correction picker.

The JSON-file CLI is retained because the Windows runtime launches picker
dialogs in a helper process to keep its polling loop responsive.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Shared.track_picker_ui import (  # noqa: E402
    show_choice_picker as _show_choice_picker,
    show_console as _show_console,
    show_correction_dialog as _show_correction_dialog,
    show_input_picker as _show_input_picker,
    show_wrong_song_dialog as _show_wrong_song_dialog,
)


DEFAULT_ICON = str(Path(__file__).with_name("icon.png"))


def show_choice_picker(*args, **kwargs):
    kwargs.setdefault("icon_path", DEFAULT_ICON)
    return _show_choice_picker(*args, **kwargs)


def show_input_picker(*args, **kwargs):
    kwargs.setdefault("icon_path", DEFAULT_ICON)
    return _show_input_picker(*args, **kwargs)


def show_wrong_song_dialog(*args, **kwargs):
    kwargs.setdefault("icon_path", DEFAULT_ICON)
    return _show_wrong_song_dialog(*args, **kwargs)


def show_correction_dialog(*args, **kwargs):
    kwargs.setdefault("icon_path", DEFAULT_ICON)
    return _show_correction_dialog(*args, **kwargs)


def show_console(*args, **kwargs):
    kwargs.setdefault("icon_path", DEFAULT_ICON)
    return _show_console(*args, **kwargs)


def run_from_file(filepath):
    with open(filepath, "r", encoding="utf-8") as handle:
        request = json.load(handle)

    mode = request.get("mode")
    if mode == "choice":
        response = show_choice_picker(
            request["title"],
            request["choices"],
            search_query=request.get("search_query") or request.get("title", ""),
            page_size=request.get("page_size", 5),
            prompt=request.get("prompt", "No artist found. Select the correct track:"),
            remember=request.get("remember", True),
        )
    elif mode == "input":
        response = show_input_picker(request["artist"])
    elif mode == "wrongsong":
        response = show_wrong_song_dialog()
    elif mode == "correction":
        response = show_correction_dialog(
            request.get("raw_track") or {}, request.get("track")
        )
    else:
        response = {}

    with open(filepath, "w", encoding="utf-8") as handle:
        json.dump(response, handle)


if __name__ == "__main__":
    if "--console" in sys.argv:
        index = sys.argv.index("--console")
        if index + 1 < len(sys.argv):
            show_console(sys.argv[index + 1])
    elif len(sys.argv) > 1:
        run_from_file(sys.argv[1])
