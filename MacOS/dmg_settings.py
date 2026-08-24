# MIT License - Copyright (c) 2026 eripum9

import os
import plistlib
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    defines: dict[str, str] = {}

application = os.path.abspath(defines["app"])  # noqa: F821 - injected by dmgbuild
app_name = os.path.basename(application)


def app_icon(app_path):
    plist_path = os.path.join(app_path, "Contents", "Info.plist")
    with open(plist_path, "rb") as plist_file:
        bundle_info = plistlib.load(plist_file)
    icon_name = bundle_info["CFBundleIconFile"]
    if not os.path.splitext(icon_name)[1]:
        icon_name += ".icns"
    return os.path.join(app_path, "Contents", "Resources", icon_name)


format = "UDZO"
filesystem = "HFS+"
files = [application]
symlinks = {"Applications": "/Applications"}
icon = app_icon(application)

background = "builtin-arrow"
window_rect = ((200, 200), (600, 400))
default_view = "icon-view"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
show_icon_preview = True
include_icon_view_settings = True
arrange_by = None
icon_size = 128
text_size = 14
icon_locations = {
    app_name: (150, 190),
    "Applications": (450, 190),
}

# Do not ask dmgbuild to toggle the signed app's Finder-extension bit. That
# writes Finder metadata to the bundle after signing, and strict codesign
# verification then rejects the mounted copy as containing detritus.
