# MIT License - Copyright (c) 2026 eripum9

"""Native PySide6 settings, diagnostics, and correction UI for macOS."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices, QIcon, QKeySequence
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from . import config
except ImportError:  # Direct development execution.
    import config

from Shared.track_picker_ui import (
    show_choice_picker,
    show_correction_dialog,
    show_input_picker,
    show_wrong_song_dialog,
)


ISSUES_URL = "https://github.com/eripum9/Amazon-Music-Discord-RPC/issues/new"
RELEASES_URL = "https://github.com/eripum9/Amazon-Music-Discord-RPC/releases/latest"
LISTENBRAINZ_SETTINGS_URL = "https://listenbrainz.org/settings/"
NETWORK_HISTORY_PATH = str(Path(config.CONFIG_DIR) / "network-history.json")

COLORS = {
    "background": "#17181b",
    "surface": "#1e1f23",
    "card": "#25262b",
    "input": "#191a1e",
    "border": "#3a3c43",
    "border_light": "#494c54",
    "text": "#f2f3f5",
    "muted": "#a5a9b2",
    "accent": "#5865f2",
    "accent_hover": "#4752c4",
    "success": "#3ba55d",
    "warning": "#faa61a",
    "error": "#ed4245",
}

APP_STYLE = f"""
QMainWindow, QDialog, QWidget#appRoot {{ background: {COLORS['background']}; color: {COLORS['text']}; }}
QWidget {{ color: {COLORS['text']}; font-size: 13px; }}
QLabel[muted="true"] {{ color: {COLORS['muted']}; }}
QLabel[heading="true"] {{ font-size: 22px; font-weight: 700; }}
QLabel[cardTitle="true"] {{ font-size: 15px; font-weight: 700; }}
QFrame#card {{ background: {COLORS['card']}; border: 1px solid {COLORS['border']}; border-radius: 10px; }}
QFrame#statusCard {{ background: {COLORS['card']}; border: 1px solid {COLORS['border']}; border-radius: 10px; }}
QLineEdit, QPlainTextEdit, QComboBox, QTableWidget {{
    background: {COLORS['input']}; color: {COLORS['text']};
    border: 1px solid {COLORS['border']}; border-radius: 7px; padding: 7px;
    selection-background-color: {COLORS['accent']};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QTableWidget:focus {{ border-color: {COLORS['accent']}; }}
QComboBox::drop-down {{ border: 0; width: 24px; }}
QPushButton {{
    background: #34363c; color: {COLORS['text']}; border: 1px solid {COLORS['border_light']};
    border-radius: 7px; padding: 7px 14px; font-weight: 600;
}}
QPushButton:hover {{ background: #404249; }}
QPushButton:pressed {{ background: #2e3035; }}
QPushButton:disabled {{ background: #26272b; color: #6f737c; border-color: #303238; }}
QPushButton[primary="true"] {{ background: {COLORS['accent']}; border-color: {COLORS['accent']}; color: white; }}
QPushButton[primary="true"]:hover {{ background: {COLORS['accent_hover']}; }}
QPushButton[danger="true"] {{ background: transparent; color: #ff7376; border-color: #7a3437; }}
QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{ width: 17px; height: 17px; }}
QTabWidget::pane {{ border: 0; background: {COLORS['background']}; top: -1px; }}
QTabBar::tab {{
    color: {COLORS['muted']}; background: transparent; padding: 11px 15px;
    border-bottom: 2px solid transparent; font-weight: 600;
}}
QTabBar::tab:selected {{ color: {COLORS['text']}; border-bottom-color: {COLORS['accent']}; }}
QScrollArea {{ border: 0; background: transparent; }}
QHeaderView::section {{
    background: #2d2f34; color: {COLORS['muted']}; border: 0;
    border-bottom: 1px solid {COLORS['border']}; padding: 7px; font-weight: 600;
}}
QTableWidget {{ gridline-color: {COLORS['border']}; }}
QTableWidget::item {{ padding: 5px; }}
QStatusBar {{ background: {COLORS['surface']}; color: {COLORS['muted']}; border-top: 1px solid {COLORS['border']}; }}
QToolTip {{ background: #111215; color: {COLORS['text']}; border: 1px solid {COLORS['border_light']}; padding: 5px; }}
"""


class UIValidationError(ValueError):
    """A user-facing settings validation error."""


def _utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _string_list(value):
    if isinstance(value, str):
        value = value.replace("\n", ",").split(",")
    if not isinstance(value, (list, tuple)):
        return []
    result = []
    seen = set()
    for item in value:
        text = str(item or "").strip()
        folded = text.casefold()
        if text and folded not in seen:
            result.append(text)
            seen.add(folded)
    return result


def clean_custom_albums(value):
    """Normalize the editable custom-artwork list.

    ``value`` may be a decoded list or JSON text. Invalid JSON and invalid row
    shapes are rejected before touching the configuration file.
    """
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            raise UIValidationError(f"Custom albums JSON is invalid: {error.msg}") from error
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise UIValidationError("Custom albums must be a JSON array.")
    cleaned = []
    for index, entry in enumerate(value, start=1):
        if not isinstance(entry, dict):
            raise UIValidationError(f"Custom album row {index} must be an object.")
        album = str(entry.get("album") or "").strip()
        art_url = str(entry.get("art_url") or "").strip()
        aliases = _string_list(entry.get("aliases") or [])
        if not album and not art_url and not aliases:
            continue
        if not album:
            raise UIValidationError(f"Custom album row {index} needs an album name.")
        if not art_url:
            raise UIValidationError(f"Custom album row {index} needs an artwork URL.")
        if not art_url.lower().startswith(("https://", "http://")):
            raise UIValidationError(f"Custom album row {index} artwork must use HTTP or HTTPS.")
        cleaned.append({"album": album, "aliases": aliases, "art_url": art_url})
    return cleaned


def settings_export_payload(settings, include_secrets=False, exported_at=None):
    """Build a portable settings document with secrets opt-in."""
    settings = settings if isinstance(settings, dict) else {}
    exported = {}
    for key in config.DEFAULTS:
        if key in config.SENSITIVE_CONFIG_KEYS and not include_secrets:
            continue
        if key not in settings:
            continue
        value = settings[key]
        if key == "custom_albums":
            value = clean_custom_albums(value)
        exported[key] = value
    return {
        # Keep the Windows marker/flag for cross-platform imports while also
        # carrying an explicit format version for future migrations.
        "format": "AmazonMusicRPC.settings",
        "format_version": 1,
        "app_version": config.APP_VERSION,
        "exported_at": exported_at or _utc_timestamp(),
        "include_tokens": bool(include_secrets),
        "includes_secrets": bool(include_secrets),
        "config": exported,
    }


def settings_import_updates(payload):
    """Validate an imported settings document and return known-key updates."""
    if not isinstance(payload, dict):
        raise UIValidationError("The imported file must contain a JSON object.")
    source = payload.get("config", payload)
    if not isinstance(source, dict):
        raise UIValidationError("The imported config must be a JSON object.")
    updates = {}
    wrapped = source is not payload
    includes_secrets = bool(payload.get("include_tokens") or payload.get("includes_secrets"))
    for key, value in source.items():
        if key not in config.DEFAULTS:
            continue
        if wrapped and key in config.SENSITIVE_CONFIG_KEYS and not includes_secrets:
            continue
        default = config.DEFAULTS[key]
        if key == "custom_albums":
            updates[key] = clean_custom_albums(value)
        elif isinstance(default, bool):
            if not isinstance(value, bool):
                raise UIValidationError(f"{key} must be true or false.")
            updates[key] = value
        elif isinstance(default, int) and not isinstance(default, bool):
            try:
                updates[key] = int(value)
            except (TypeError, ValueError) as error:
                raise UIValidationError(f"{key} must be a whole number.") from error
        elif isinstance(default, dict):
            if not isinstance(value, dict):
                raise UIValidationError(f"{key} must be an object.")
            updates[key] = value
        elif isinstance(default, list):
            if not isinstance(value, list):
                raise UIValidationError(f"{key} must be an array.")
            updates[key] = value
        else:
            updates[key] = str(value or "")
    if "discord_status_display" in updates:
        updates["discord_status_display"] = config.normalize_discord_status_display(
            updates["discord_status_display"]
        )
    if "amazon_music_link_region" in updates:
        updates["amazon_music_link_region"] = config.normalize_amazon_music_link_region(
            updates["amazon_music_link_region"]
        )
    return updates


def snapshot_rows(snapshot):
    """Flatten a runtime snapshot into stable diagnostics card rows."""
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    scrobbling = snapshot.get("scrobbling") or {}
    privacy = snapshot.get("privacy") or {}
    devtools = snapshot.get("amazon_devtools") or {}
    return [
        ("Runtime", str(snapshot.get("rpc_status") or "waiting"), str(snapshot.get("source_detail") or "")),
        ("Discord", str(snapshot.get("discord_status") or snapshot.get("discord") or "waiting"), "Presence visible" if snapshot.get("presence_visible") else "Presence hidden or waiting"),
        ("Metadata", str(snapshot.get("source") or "waiting"), str(devtools.get("detail") or snapshot.get("devtools_status") or "")),
        ("Last.fm", str(scrobbling.get("lastfm") or "disabled"), "Scrobbling service"),
        ("ListenBrainz", str(scrobbling.get("listenbrainz") or "disabled"), "Scrobbling service"),
        ("Privacy", "hidden" if privacy.get("hidden") else ("private" if privacy.get("private_session") else "standard"), str(privacy.get("reason") or "No current privacy match")),
    ]


def _network_history(path=NETWORK_HISTORY_PATH):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []
    return [entry for entry in value[-50:] if isinstance(entry, dict)]


def diagnostic_document(snapshot, settings, network_events=None, generated_at=None):
    """Create a redacted, shareable diagnostic JSON document."""
    settings = settings if isinstance(settings, dict) else {}
    public_settings = {
        key: value
        for key, value in settings.items()
        if key in config.DEFAULTS and key not in config.SENSITIVE_CONFIG_KEYS
    }
    document = {
        "format": "amazon-music-rpc-diagnostics",
        "format_version": 1,
        "generated_at": generated_at or _utc_timestamp(),
        "app": {
            "name": config.APP_DISPLAY_NAME,
            "version": config.APP_VERSION,
            "bundle_identifier": config.BUNDLE_IDENTIFIER,
        },
        "system": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "frozen": bool(getattr(sys, "frozen", False)),
        },
        "runtime": snapshot if isinstance(snapshot, dict) else {},
        "settings": public_settings,
        "credential_storage": config.credential_storage_status(),
        "paths": {
            "config": config.CONFIG_PATH,
            "console_log": config.LOG_PATH,
            "event_log": config.EVENT_LOG_PATH,
            "runtime_diagnostics": config.DIAGNOSTICS_PATH,
            "network_history": NETWORK_HISTORY_PATH,
        },
        "network_history": list(network_events or []),
    }
    return config.redact_data(document, settings)


def _read_redacted_text(path, settings, max_bytes=120000):
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            value = handle.read().decode("utf-8", errors="replace")
    except OSError as error:
        return f"{Path(path).name} is unavailable: {error}"
    return config.redact_text(value, settings)


def _write_private_json(path, payload):
    """Atomically write user-exported JSON with owner-only permissions."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _status_color(status):
    status = str(status or "").casefold()
    if status in {"running", "connected", "found", "active", "standard", "on"}:
        return COLORS["success"]
    if status in {"waiting", "retrying", "paused", "private", "hidden", "not_authenticated", "missing_token"}:
        return COLORS["warning"]
    if status in {"error", "stopped", "disconnected", "unavailable", "off"}:
        return COLORS["error"]
    return COLORS["muted"]


class _WorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)


class _Worker(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = _WorkerSignals()

    def run(self):
        try:
            value = self.function()
        except Exception as error:
            self.signals.failed.emit(f"{type(error).__name__}: {error}")
        else:
            self.signals.succeeded.emit(value)


class _Card(QFrame):
    def __init__(self, title, description="", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.layout_box = QVBoxLayout(self)
        self.layout_box.setContentsMargins(18, 16, 18, 17)
        self.layout_box.setSpacing(11)
        heading = QLabel(title)
        heading.setProperty("cardTitle", True)
        self.layout_box.addWidget(heading)
        if description:
            hint = QLabel(description)
            hint.setProperty("muted", True)
            hint.setWordWrap(True)
            self.layout_box.addWidget(hint)


def _scroll_tab():
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    content.setObjectName("appRoot")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(20, 18, 20, 24)
    layout.setSpacing(14)
    scroll.setWidget(content)
    return scroll, layout


def _labelled_row(label, widget, hint=""):
    row = QWidget()
    layout = QVBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(5)
    title = QLabel(label)
    title.setStyleSheet("font-weight: 600;")
    layout.addWidget(title)
    layout.addWidget(widget)
    if hint:
        note = QLabel(hint)
        note.setProperty("muted", True)
        note.setWordWrap(True)
        layout.addWidget(note)
    return row


class SettingsWindow(QMainWindow):
    def __init__(self, coordinator):
        super().__init__()
        self.coordinator = coordinator
        self.setObjectName("appRoot")
        self.setStyleSheet(APP_STYLE)
        self.setWindowTitle(f"{config.APP_DISPLAY_NAME} — Settings")
        self.setMinimumSize(720, 620)
        if coordinator.icon:
            self.setWindowIcon(coordinator.icon)
        saved = config.load_config()
        self.resize(
            max(720, int(saved.get("settings_window_width", 800))),
            max(620, int(saved.get("settings_window_height", 760))),
        )
        self._build()
        self.load_settings(saved)

    def _build(self):
        central = QWidget()
        central.setObjectName("appRoot")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(22, 18, 22, 16)
        outer.setSpacing(10)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        heading = QLabel("Settings")
        heading.setProperty("heading", True)
        titles.addWidget(heading)
        subtitle = QLabel("Control presence, metadata, privacy, and scrobbling.")
        subtitle.setProperty("muted", True)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch(1)
        version = QLabel(config.APP_VERSION)
        version.setProperty("muted", True)
        header.addWidget(version)
        outer.addLayout(header)

        self.tabs = QTabWidget()
        self._build_general_tab()
        self._build_privacy_tab()
        self._build_scrobbling_tab()
        self._build_artwork_tab()
        self._build_advanced_tab()
        outer.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        self.status = QLabel("")
        self.status.setProperty("muted", True)
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        diagnostics = QPushButton("Diagnostics")
        diagnostics.clicked.connect(self.coordinator.show_diagnostics)
        footer.addWidget(diagnostics)
        cancel = QPushButton("Reload")
        cancel.clicked.connect(lambda: self.load_settings(config.load_config()))
        footer.addWidget(cancel)
        save = QPushButton("Save changes")
        save.setProperty("primary", True)
        save.setShortcut(QKeySequence.StandardKey.Save)
        save.clicked.connect(self.save)
        footer.addWidget(save)
        outer.addLayout(footer)
        self.setCentralWidget(central)

    def _build_general_tab(self):
        scroll, layout = _scroll_tab()
        discord = _Card(
            "Discord Rich Presence",
            "The built-in application ID works immediately. A custom Discord application ID can use your own branding.",
        )
        self.custom_client = QCheckBox("Use a custom Discord application ID")
        discord.layout_box.addWidget(self.custom_client)
        self.client_id = QLineEdit()
        self.client_id.setPlaceholderText(config.DEFAULT_CLIENT_ID)
        self.client_id.setClearButtonEnabled(True)
        discord.layout_box.addWidget(_labelled_row("Discord client ID", self.client_id, "Discord application IDs contain digits only."))
        self.status_display = QComboBox()
        for key, label in (("artist", "Artist"), ("album", "Album"), ("track", "Track"), ("application", "Application name")):
            self.status_display.addItem(label, key)
        discord.layout_box.addWidget(_labelled_row("Profile status display", self.status_display))
        self.custom_client.toggled.connect(self.client_id.setEnabled)
        layout.addWidget(discord)

        startup = _Card("Startup", "Use a per-user LaunchAgent. No administrator access is needed.")
        self.startup = QCheckBox("Start Amazon Music RPC when I log in")
        self.start_minimized = QCheckBox("Start in the menu bar without opening Settings")
        startup.layout_box.addWidget(self.startup)
        startup.layout_box.addWidget(self.start_minimized)
        layout.addWidget(startup)

        playback = _Card("Playback display")
        self.show_paused = QCheckBox("Show a paused status in Discord")
        self.song_links = QCheckBox("Add a listen button to Discord presence")
        playback.layout_box.addWidget(self.show_paused)
        playback.layout_box.addWidget(self.song_links)
        row = QHBoxLayout()
        self.link_provider = QComboBox()
        self.link_provider.addItem("Amazon Music", "amazon")
        self.link_provider.addItem("Deezer when matched", "deezer")
        row.addWidget(_labelled_row("Link provider", self.link_provider), 1)
        self.region = QComboBox()
        for region in config.AMAZON_MUSIC_LINK_REGIONS:
            self.region.addItem(f"music.amazon.{region}", region)
        row.addWidget(_labelled_row("Amazon region", self.region), 1)
        playback.layout_box.addLayout(row)
        layout.addWidget(playback)
        layout.addStretch(1)
        self.tabs.addTab(scroll, "General")

    def _build_privacy_tab(self):
        scroll, layout = _scroll_tab()
        privacy = _Card(
            "Privacy controls",
            "Privacy filtering happens before metadata is sent to Discord or a scrobbling service.",
        )
        self.private_session = QCheckBox("Private session — hide all listening activity")
        self.disable_private_scrobbling = QCheckBox("Also pause scrobbling while activity is private")
        privacy.layout_box.addWidget(self.private_session)
        privacy.layout_box.addWidget(self.disable_private_scrobbling)
        self.blocked_keywords = QPlainTextEdit()
        self.blocked_keywords.setMaximumHeight(100)
        self.blocked_keywords.setPlaceholderText("podcast, audiobook, private artist")
        privacy.layout_box.addWidget(
            _labelled_row(
                "Blocked title, artist, or album keywords",
                self.blocked_keywords,
                "Separate values with commas or new lines. Matching is case-insensitive.",
            )
        )
        layout.addWidget(privacy)

        game = _Card(
            "Game mode",
            "Suppress automatic wrong-song correction popups while active, without hiding presence.",
        )
        self.game_mode = QCheckBox("Enable game mode now")
        game.layout_box.addWidget(self.game_mode)
        self.game_processes = QPlainTextEdit()
        self.game_processes.setMaximumHeight(95)
        self.game_processes.setPlaceholderText("Minecraft, LeagueClient, steam_app_1234")
        game.layout_box.addWidget(
            _labelled_row(
                "Process names",
                self.game_processes,
                "Comma-separated executable or app process names; file extensions are optional.",
            )
        )
        layout.addWidget(game)
        layout.addStretch(1)
        self.tabs.addTab(scroll, "Privacy")

    def _build_scrobbling_tab(self):
        scroll, layout = _scroll_tab()
        lastfm = _Card(
            "Last.fm",
            "Scrobble after 50% of a song or four minutes, with a 30-second minimum.",
        )
        self.lastfm_enabled = QCheckBox("Enable Last.fm scrobbling")
        lastfm.layout_box.addWidget(self.lastfm_enabled)
        self.lastfm_status = QLabel("")
        self.lastfm_status.setProperty("muted", True)
        lastfm.layout_box.addWidget(self.lastfm_status)
        buttons = QHBoxLayout()
        authenticate = QPushButton("Authenticate in browser")
        authenticate.clicked.connect(self._lastfm_auth)
        buttons.addWidget(authenticate)
        complete = QPushButton("Complete authentication")
        complete.setProperty("primary", True)
        complete.clicked.connect(self._lastfm_complete)
        buttons.addWidget(complete)
        buttons.addStretch(1)
        clear = QPushButton("Disconnect")
        clear.setProperty("danger", True)
        clear.clicked.connect(self._clear_lastfm)
        buttons.addWidget(clear)
        lastfm.layout_box.addLayout(buttons)
        layout.addWidget(lastfm)

        brainz = _Card(
            "ListenBrainz",
            "The user token is stored in macOS Keychain and is never written to config.json.",
        )
        self.listenbrainz_enabled = QCheckBox("Enable ListenBrainz scrobbling")
        brainz.layout_box.addWidget(self.listenbrainz_enabled)
        self.listenbrainz_token = QLineEdit()
        self.listenbrainz_token.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.listenbrainz_token.setPlaceholderText("Paste your ListenBrainz user token")
        brainz.layout_box.addWidget(_labelled_row("User token", self.listenbrainz_token))
        self.listenbrainz_status = QLabel("")
        self.listenbrainz_status.setProperty("muted", True)
        brainz.layout_box.addWidget(self.listenbrainz_status)
        actions = QHBoxLayout()
        open_settings = QPushButton("Get token")
        open_settings.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(LISTENBRAINZ_SETTINGS_URL)))
        actions.addWidget(open_settings)
        validate = QPushButton("Validate token")
        validate.setProperty("primary", True)
        validate.clicked.connect(self._validate_listenbrainz)
        actions.addWidget(validate)
        actions.addStretch(1)
        brainz.layout_box.addLayout(actions)
        layout.addWidget(brainz)
        layout.addStretch(1)
        self.tabs.addTab(scroll, "Scrobbling")

    def _build_artwork_tab(self):
        scroll, layout = _scroll_tab()
        lookup = _Card(
            "Artwork lookup",
            "Amazon metadata artwork is preferred. These providers fill gaps and are contacted only when needed.",
        )
        self.deezer_lookup = QCheckBox("Allow Deezer metadata and artwork lookup")
        self.itunes_lookup = QCheckBox("Allow Apple iTunes Search artwork lookup")
        lookup.layout_box.addWidget(self.deezer_lookup)
        lookup.layout_box.addWidget(self.itunes_lookup)
        layout.addWidget(lookup)

        custom = _Card(
            "Custom album artwork",
            "Override artwork by album name. Aliases let remasters or alternate spellings share one image.",
        )
        self.custom_albums = QTableWidget(0, 3)
        self.custom_albums.setHorizontalHeaderLabels(["Album", "Aliases", "Artwork URL"])
        self.custom_albums.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.custom_albums.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.custom_albums.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.custom_albums.verticalHeader().setVisible(False)
        self.custom_albums.setMinimumHeight(240)
        custom.layout_box.addWidget(self.custom_albums)
        actions = QHBoxLayout()
        add = QPushButton("Add album")
        add.clicked.connect(self._add_album)
        actions.addWidget(add)
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove_albums)
        actions.addWidget(remove)
        actions.addStretch(1)
        custom.layout_box.addLayout(actions)
        layout.addWidget(custom)
        layout.addStretch(1)
        self.tabs.addTab(scroll, "Artwork")

    def _build_advanced_tab(self):
        scroll, layout = _scroll_tab()
        metadata = _Card(
            "Enhanced Amazon metadata",
            "Uses Chromium DevTools on a randomized loopback-only port. Turning off the checkbox stops RPC access, but an existing listener remains until Amazon Music is reopened normally.",
        )
        self.devtools_enabled = QCheckBox("Enable enhanced metadata")
        self.devtools_auto = QCheckBox("Automatically start enhanced metadata when Amazon Music is closed")
        metadata.layout_box.addWidget(self.devtools_enabled)
        metadata.layout_box.addWidget(self.devtools_auto)
        self.devtools_status = QLabel("")
        self.devtools_status.setProperty("muted", True)
        metadata.layout_box.addWidget(self.devtools_status)
        actions = QHBoxLayout()
        launch = QPushButton("Start enhanced metadata")
        launch.setProperty("primary", True)
        launch.clicked.connect(self._launch_devtools)
        actions.addWidget(launch)
        restart = QPushButton("Restart Amazon Music with DevTools")
        restart.clicked.connect(lambda: self._launch_devtools(restart=True))
        actions.addWidget(restart)
        disable = QPushButton("Disable listener & reopen normally")
        disable.clicked.connect(self._disable_devtools)
        actions.addWidget(disable)
        actions.addStretch(1)
        metadata.layout_box.addLayout(actions)
        layout.addWidget(metadata)

        updates = _Card("Updates")
        self.automatic_updates = QCheckBox("Check for updates automatically")
        updates.layout_box.addWidget(self.automatic_updates)
        check = QPushButton("Check now")
        check.clicked.connect(self.coordinator.check_updates)
        updates.layout_box.addWidget(check, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(updates)

        data = _Card(
            "Settings import and export",
            "Exports exclude Keychain credentials unless you explicitly include them.",
        )
        self.include_secrets = QCheckBox("Include Last.fm and ListenBrainz credentials in exported JSON")
        data.layout_box.addWidget(self.include_secrets)
        row = QHBoxLayout()
        export = QPushButton("Export settings…")
        export.clicked.connect(self.export_settings)
        row.addWidget(export)
        import_button = QPushButton("Import settings…")
        import_button.clicked.connect(self.import_settings)
        row.addWidget(import_button)
        row.addStretch(1)
        data.layout_box.addLayout(row)
        keychain = config.credential_storage_status()
        storage = QLabel(
            "Credential storage: macOS Keychain available"
            if keychain.get("keychain_available")
            else "Credential storage: macOS Keychain unavailable"
        )
        storage.setProperty("muted", True)
        data.layout_box.addWidget(storage)
        layout.addWidget(data)
        layout.addStretch(1)
        self.tabs.addTab(scroll, "Advanced")

    def _combo_value(self, combo):
        return combo.currentData() if combo.currentData() is not None else combo.currentText()

    def _set_combo(self, combo, value):
        index = combo.findData(value)
        if index < 0:
            index = combo.findText(str(value))
        combo.setCurrentIndex(max(0, index))

    def load_settings(self, settings):
        self.settings = dict(settings or {})
        self.custom_client.setChecked(bool(settings.get("use_custom_client_id")))
        self.client_id.setText(str(settings.get("discord_client_id") or ""))
        self.client_id.setEnabled(self.custom_client.isChecked())
        self._set_combo(self.status_display, settings.get("discord_status_display", "artist"))
        self.startup.setChecked(bool(settings.get("start_on_startup")))
        self.start_minimized.setChecked(bool(settings.get("start_minimized", True)))
        self.show_paused.setChecked(bool(settings.get("show_paused", True)))
        self.song_links.setChecked(bool(settings.get("song_link_enabled", True)))
        self._set_combo(self.link_provider, settings.get("song_link_provider", "amazon"))
        self._set_combo(self.region, settings.get("amazon_music_link_region", "com"))
        self.private_session.setChecked(bool(settings.get("privacy_private_session")))
        self.disable_private_scrobbling.setChecked(bool(settings.get("privacy_disable_scrobbling", True)))
        self.blocked_keywords.setPlainText(str(settings.get("privacy_blocked_keywords") or ""))
        self.game_mode.setChecked(bool(settings.get("game_mode_enabled")))
        self.game_processes.setPlainText(str(settings.get("game_mode_processes") or ""))
        self.lastfm_enabled.setChecked(bool(settings.get("lastfm_enabled")))
        username = str(settings.get("lastfm_username") or "")
        self.lastfm_status.setText(f"Connected as {username}" if username else "Not authenticated")
        self.listenbrainz_enabled.setChecked(bool(settings.get("listenbrainz_enabled")))
        self.listenbrainz_token.setText(str(settings.get("listenbrainz_token") or ""))
        self.listenbrainz_status.setText("Token saved in Keychain" if settings.get("listenbrainz_token") else "No token saved")
        self.deezer_lookup.setChecked(bool(settings.get("deezer_lookup_enabled", True)))
        self.itunes_lookup.setChecked(bool(settings.get("itunes_lookup_enabled", True)))
        self._load_custom_albums(settings.get("custom_albums") or [])
        self.devtools_enabled.setChecked(bool(settings.get("amazon_devtools_enabled", True)))
        self.devtools_auto.setChecked(bool(settings.get("amazon_devtools_auto_launch", False)))
        self.automatic_updates.setChecked(bool(settings.get("automatic_update_checks", True)))
        self.status.setText("Settings loaded.")

    def _load_custom_albums(self, albums):
        try:
            albums = clean_custom_albums(albums)
        except UIValidationError:
            albums = []
        self.custom_albums.setRowCount(0)
        for album in albums:
            row = self.custom_albums.rowCount()
            self.custom_albums.insertRow(row)
            self.custom_albums.setItem(row, 0, QTableWidgetItem(album["album"]))
            self.custom_albums.setItem(row, 1, QTableWidgetItem(", ".join(album["aliases"])))
            self.custom_albums.setItem(row, 2, QTableWidgetItem(album["art_url"]))

    def _custom_album_payload(self):
        rows = []
        for row in range(self.custom_albums.rowCount()):
            values = []
            for column in range(3):
                item = self.custom_albums.item(row, column)
                values.append(item.text().strip() if item else "")
            rows.append({"album": values[0], "aliases": _string_list(values[1]), "art_url": values[2]})
        return clean_custom_albums(rows)

    def _add_album(self):
        row = self.custom_albums.rowCount()
        self.custom_albums.insertRow(row)
        for column in range(3):
            self.custom_albums.setItem(row, column, QTableWidgetItem(""))
        self.custom_albums.setCurrentCell(row, 0)
        self.custom_albums.editItem(self.custom_albums.item(row, 0))

    def _remove_albums(self):
        rows = sorted({item.row() for item in self.custom_albums.selectedItems()}, reverse=True)
        for row in rows:
            self.custom_albums.removeRow(row)

    def values(self):
        client_id = self.client_id.text().strip()
        if self.custom_client.isChecked() and (not client_id.isdigit() or not 16 <= len(client_id) <= 24):
            raise UIValidationError("Custom Discord client ID must contain 16–24 digits.")
        return {
            "use_custom_client_id": self.custom_client.isChecked(),
            "discord_client_id": client_id or config.DEFAULT_CLIENT_ID,
            "discord_status_display": self._combo_value(self.status_display),
            "start_on_startup": self.startup.isChecked(),
            "start_minimized": self.start_minimized.isChecked(),
            "show_paused": self.show_paused.isChecked(),
            "song_link_enabled": self.song_links.isChecked(),
            "song_link_provider": self._combo_value(self.link_provider),
            "amazon_music_link_region": self._combo_value(self.region),
            "privacy_private_session": self.private_session.isChecked(),
            "privacy_disable_scrobbling": self.disable_private_scrobbling.isChecked(),
            "privacy_blocked_keywords": self.blocked_keywords.toPlainText().strip(),
            "game_mode_enabled": self.game_mode.isChecked(),
            "game_mode_processes": self.game_processes.toPlainText().strip(),
            "lastfm_enabled": self.lastfm_enabled.isChecked(),
            "listenbrainz_enabled": self.listenbrainz_enabled.isChecked(),
            "listenbrainz_token": self.listenbrainz_token.text().strip(),
            "deezer_lookup_enabled": self.deezer_lookup.isChecked(),
            "itunes_lookup_enabled": self.itunes_lookup.isChecked(),
            "custom_albums": self._custom_album_payload(),
            "amazon_devtools_enabled": self.devtools_enabled.isChecked(),
            "amazon_devtools_auto_launch": self.devtools_auto.isChecked(),
            "automatic_update_checks": self.automatic_updates.isChecked(),
        }

    def save(self):
        try:
            values = self.values()
            values.update(
                {
                    "intro_seen": True,
                    "setup_wizard_seen": True,
                    "setup_wizard_version": config.APP_VERSION,
                }
            )
            saved = config.update_config_fields(values)
            config.set_startup(saved.get("start_on_startup"), saved.get("start_minimized"))
            self.coordinator.runtime_reload(saved)
            self.settings = saved
        except Exception as error:
            QMessageBox.warning(self, "Could not save settings", str(error))
            self.status.setText(f"Save failed: {error}")
            return False
        self.status.setText("Settings saved. Runtime reloaded.")
        return True

    def _lastfm_auth(self):
        self.status.setText("Starting Last.fm authentication…")
        self.coordinator.lastfm_auth(
            lambda result: self.status.setText(
                "Browser opened. Approve access, then click Complete authentication."
                if result.get("ok")
                else result.get("error", "Authentication failed.")
            )
        )

    def _lastfm_complete(self):
        self.status.setText("Completing Last.fm authentication…")

        def done(result):
            if result.get("ok"):
                self.lastfm_enabled.setChecked(True)
                self.lastfm_status.setText(f"Connected as {result.get('username') or 'Last.fm user'}")
                self.load_settings(config.load_config())
            else:
                self.status.setText(result.get("error", "Authentication failed."))

        self.coordinator.lastfm_complete(done)

    def _clear_lastfm(self):
        saved = config.update_config_fields(
            {"lastfm_enabled": False, "lastfm_session_key": "", "lastfm_username": ""}
        )
        self.coordinator.runtime_reload(saved)
        self.load_settings(saved)
        self.status.setText("Last.fm disconnected.")

    def _validate_listenbrainz(self):
        token = self.listenbrainz_token.text().strip()
        if not token:
            self.listenbrainz_status.setText("Paste a token first.")
            return
        self.listenbrainz_status.setText("Validating…")

        def done(result):
            if result.get("valid"):
                self.listenbrainz_status.setText(f"Valid token for {result.get('user_name') or 'ListenBrainz user'}")
                self.listenbrainz_enabled.setChecked(True)
            else:
                self.listenbrainz_status.setText(result.get("error") or "Invalid token")

        self.coordinator.validate_listenbrainz(token, done)

    def _launch_devtools(self, restart=False):
        self.devtools_status.setText("Restarting Amazon Music…" if restart else "Starting enhanced metadata…")

        def task():
            return self.coordinator.runtime.launch_enhanced_metadata(restart_if_needed=restart)

        def done(result):
            self.devtools_status.setText(
                str(result.get("error") or result.get("detail") or result.get("status") or "Ready")
            )

        self.coordinator.run_background(task, done, lambda error: self.devtools_status.setText(error))

    def _disable_devtools(self):
        answer = QMessageBox.question(
            self,
            "Reopen Amazon Music normally?",
            "This closes Amazon Music, removes its local DevTools listener, and reopens it normally. Playback will be interrupted. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.devtools_status.setText("Reopening Amazon Music without DevTools…")

        def done(result):
            if result.get("ok"):
                self.devtools_enabled.setChecked(False)
                self.devtools_auto.setChecked(False)
            self.devtools_status.setText(
                str(
                    result.get("error")
                    or result.get("detail")
                    or result.get("status")
                    or "Disabled"
                )
            )

        self.coordinator.run_background(
            lambda: self.coordinator.runtime.disable_enhanced_metadata(relaunch=True),
            done,
            lambda error: self.devtools_status.setText(error),
        )

    def export_settings(self):
        suggested = f"AmazonMusicRPC_Settings_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Amazon Music RPC settings", str(Path.home() / "Downloads" / suggested), "JSON files (*.json)"
        )
        if not path:
            return
        try:
            payload = settings_export_payload(config.load_config(), self.include_secrets.isChecked())
            _write_private_json(path, payload)
        except Exception as error:
            QMessageBox.warning(self, "Export failed", str(error))
            return
        self.status.setText(f"Exported to {path}")

    def import_settings(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Amazon Music RPC settings", str(Path.home()), "JSON files (*.json)"
        )
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            updates = settings_import_updates(payload)
            if not updates:
                raise UIValidationError("No recognized settings were found.")
            saved = config.update_config_fields(updates)
            config.set_startup(saved.get("start_on_startup"), saved.get("start_minimized"))
            self.coordinator.runtime_reload(saved)
            self.load_settings(saved)
        except Exception as error:
            QMessageBox.warning(self, "Import failed", str(error))
            return
        self.status.setText(f"Imported settings from {path}")

    def apply_snapshot(self, snapshot):
        devtools = (snapshot or {}).get("amazon_devtools") or {}
        self.devtools_status.setText(
            str(devtools.get("detail") or (snapshot or {}).get("devtools_status") or "Waiting")
        )

    def closeEvent(self, event: QCloseEvent):
        try:
            config.update_config_fields(
                {
                    "settings_window_width": self.width(),
                    "settings_window_height": self.height(),
                }
            )
        except Exception:
            pass
        super().closeEvent(event)


class _StatusCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 13, 15, 14)
        self.label = QLabel("")
        self.label.setProperty("muted", True)
        layout.addWidget(self.label)
        self.value = QLabel("")
        self.value.setStyleSheet("font-size: 17px; font-weight: 700;")
        layout.addWidget(self.value)
        self.detail = QLabel("")
        self.detail.setProperty("muted", True)
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)

    def apply(self, label, value, detail):
        self.label.setText(label)
        self.value.setText(value.replace("_", " ").title())
        self.value.setStyleSheet(
            f"font-size: 17px; font-weight: 700; color: {_status_color(value)};"
        )
        self.detail.setText(detail or "—")


class DiagnosticsWindow(QMainWindow):
    def __init__(self, coordinator):
        super().__init__()
        self.coordinator = coordinator
        self.setObjectName("appRoot")
        self.setStyleSheet(APP_STYLE)
        self.setWindowTitle(f"{config.APP_DISPLAY_NAME} — Diagnostics")
        self.setMinimumSize(820, 580)
        if coordinator.icon:
            self.setWindowIcon(coordinator.icon)
        saved = config.load_config()
        self.resize(
            max(820, int(saved.get("diagnostics_window_width", 960))),
            max(580, int(saved.get("diagnostics_window_height", 720))),
        )
        self.snapshot = {}
        self._build()
        self.refresh()

    def _build(self):
        central = QWidget()
        central.setObjectName("appRoot")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(22, 18, 22, 18)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Diagnostics")
        title.setProperty("heading", True)
        titles.addWidget(title)
        subtitle = QLabel("Live state and redacted troubleshooting data")
        subtitle.setProperty("muted", True)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        copy = QPushButton("Copy report")
        copy.clicked.connect(self.copy_report)
        header.addWidget(copy)
        export = QPushButton("Export JSON…")
        export.setProperty("primary", True)
        export.clicked.connect(self.export_report)
        header.addWidget(export)
        layout.addLayout(header)

        self.tabs = QTabWidget()
        overview = QWidget()
        overview.setObjectName("appRoot")
        overview_layout = QVBoxLayout(overview)
        overview_layout.setContentsMargins(4, 16, 4, 8)
        self.cards_layout = QGridLayout()
        self.cards_layout.setSpacing(10)
        self.cards = []
        for index in range(6):
            card = _StatusCard()
            self.cards.append(card)
            self.cards_layout.addWidget(card, index // 3, index % 3)
        overview_layout.addLayout(self.cards_layout)
        track = _Card("Current track")
        self.track_label = QLabel("Waiting for Amazon Music")
        self.track_label.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.track_detail = QLabel("")
        self.track_detail.setProperty("muted", True)
        self.track_detail.setWordWrap(True)
        track.layout_box.addWidget(self.track_label)
        track.layout_box.addWidget(self.track_detail)
        overview_layout.addWidget(track)
        paths = _Card("Local files")
        paths_text = QPlainTextEdit()
        paths_text.setReadOnly(True)
        paths_text.setMaximumHeight(125)
        paths_text.setPlainText(
            "\n".join(
                (
                    f"Config: {config.CONFIG_PATH}",
                    f"Console: {config.LOG_PATH}",
                    f"Events: {config.EVENT_LOG_PATH}",
                    f"Runtime state: {config.DIAGNOSTICS_PATH}",
                    f"Network: {NETWORK_HISTORY_PATH}",
                )
            )
        )
        paths.layout_box.addWidget(paths_text)
        overview_layout.addWidget(paths)
        overview_layout.addStretch(1)
        self.tabs.addTab(overview, "Overview")

        network = QWidget()
        network.setObjectName("appRoot")
        network_layout = QVBoxLayout(network)
        network_layout.setContentsMargins(4, 16, 4, 8)
        self.network_table = QTableWidget(0, 5)
        self.network_table.setHorizontalHeaderLabels(["Time", "Service", "Operation", "Status", "Detail"])
        self.network_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.network_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.network_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.network_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.network_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.network_table.verticalHeader().setVisible(False)
        self.network_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        network_layout.addWidget(self.network_table)
        self.tabs.addTab(network, "Network")

        logs = QWidget()
        logs.setObjectName("appRoot")
        logs_layout = QVBoxLayout(logs)
        logs_layout.setContentsMargins(4, 16, 4, 8)
        self.log_tabs = QTabWidget()
        self.log_views = {}
        for label, path in (
            ("Console", config.LOG_PATH),
            ("Events", config.EVENT_LOG_PATH),
            ("Runtime JSON", config.DIAGNOSTICS_PATH),
        ):
            view = QPlainTextEdit()
            view.setReadOnly(True)
            view.setStyleSheet("font-family: Menlo, Consolas, monospace; font-size: 11px;")
            self.log_views[path] = view
            self.log_tabs.addTab(view, label)
        logs_layout.addWidget(self.log_tabs)
        self.tabs.addTab(logs, "Logs")
        layout.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        self.status = QLabel("")
        self.status.setProperty("muted", True)
        footer.addWidget(self.status, 1)
        correction = QPushButton("Correct current song")
        correction.clicked.connect(self.coordinator.show_correction)
        footer.addWidget(correction)
        report = QPushButton("Report issue")
        report.clicked.connect(self.coordinator.report_issue)
        footer.addWidget(report)
        layout.addLayout(footer)
        self.setCentralWidget(central)

    def apply_snapshot(self, snapshot):
        self.snapshot = dict(snapshot or {})
        for card, row in zip(self.cards, snapshot_rows(self.snapshot)):
            card.apply(*row)
        track = self.snapshot.get("track") or {}
        self.track_label.setText(track.get("title") or "Waiting for Amazon Music")
        parts = [track.get("artist"), track.get("album"), self.snapshot.get("time")]
        parts = [str(part) for part in parts if part]
        self.track_detail.setText(" • ".join(parts) or str(self.snapshot.get("source_detail") or "No active track"))
        self.status.setText(f"Updated {datetime.now().strftime('%H:%M:%S')}")

    def refresh(self):
        self.apply_snapshot(self.coordinator.runtime_snapshot())
        events = _network_history()
        self.network_table.setRowCount(0)
        for event in reversed(events):
            row = self.network_table.rowCount()
            self.network_table.insertRow(row)
            timestamp = event.get("timestamp")
            try:
                stamp = datetime.fromtimestamp(float(timestamp)).strftime("%H:%M:%S")
            except (TypeError, ValueError, OSError):
                stamp = "—"
            values = (
                stamp,
                event.get("service", ""),
                event.get("operation", ""),
                event.get("status", ""),
                event.get("detail", ""),
            )
            for column, value in enumerate(values):
                self.network_table.setItem(row, column, QTableWidgetItem(str(value or "")))
        settings = config.load_config()
        for path, view in self.log_views.items():
            view.setPlainText(_read_redacted_text(path, settings))

    def report(self):
        return diagnostic_document(
            self.coordinator.runtime_snapshot(), config.load_config(), _network_history()
        )

    def copy_report(self):
        QApplication.clipboard().setText(json.dumps(self.report(), indent=2, ensure_ascii=False))
        self.status.setText("Redacted diagnostic report copied to the clipboard.")

    def export_report(self):
        suggested = f"AmazonMusicRPC_Diagnostics_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export redacted diagnostics", str(Path.home() / "Downloads" / suggested), "JSON files (*.json)"
        )
        if not path:
            return
        try:
            _write_private_json(path, self.report())
        except OSError as error:
            QMessageBox.warning(self, "Export failed", str(error))
            return
        self.status.setText(f"Exported redacted diagnostics to {path}")

    def closeEvent(self, event: QCloseEvent):
        try:
            config.update_config_fields(
                {
                    "diagnostics_window_width": self.width(),
                    "diagnostics_window_height": self.height(),
                }
            )
        except Exception:
            pass
        super().closeEvent(event)


class MacApplicationUI(QObject):
    """Coordinator exposed to the menu-bar controller and application entrypoint."""

    snapshot_changed = Signal(dict)

    def __init__(
        self,
        app=None,
        runtime=None,
        icon_path=None,
        *,
        on_quit=None,
        on_open_amazon=None,
    ):
        app = app or QApplication.instance()
        if app is None:
            raise RuntimeError("Create QApplication before MacApplicationUI")
        super().__init__()
        self.app = app
        self.runtime = runtime
        self.icon_path = str(icon_path or "")
        self.icon = QIcon(self.icon_path) if self.icon_path and Path(self.icon_path).is_file() else QIcon()
        self.on_quit = on_quit
        self.on_open_amazon = on_open_amazon
        self.settings_window = None
        self.diagnostics_window = None
        self._lastfm_generator = None
        self._lastfm_auth_url = None
        self._workers = set()
        self._suggested_corrections = set()
        self.thread_pool = QThreadPool.globalInstance()
        self.snapshot_changed.connect(self._apply_snapshot)
        if self.runtime and hasattr(self.runtime, "add_listener"):
            self.runtime.add_listener(self._runtime_listener, emit_current=True)

    @property
    def callbacks(self):
        return {
            "settings": self.show_settings,
            "diagnostics": self.show_diagnostics,
            "wrong_song": self.show_guided_correction,
            "updates": self.check_updates,
            "launch_amazon": self.open_amazon_music,
            "quit": self.quit,
        }

    def _runtime_listener(self, snapshot):
        self.snapshot_changed.emit(dict(snapshot or {}))

    def _apply_snapshot(self, snapshot):
        if self.settings_window:
            self.settings_window.apply_snapshot(snapshot)
        if self.diagnostics_window:
            self.diagnostics_window.apply_snapshot(snapshot)
        raw = snapshot.get("raw_track") or {}
        key = f"{raw.get('title', '')}|{raw.get('artist', '')}".casefold().strip()
        if snapshot.get("correction_suggested") and key and key not in self._suggested_corrections:
            self._suggested_corrections.add(key)
            QTimer.singleShot(
                250,
                lambda value=dict(snapshot): self.show_guided_correction(value),
            )

    def runtime_snapshot(self):
        if self.runtime and hasattr(self.runtime, "snapshot"):
            return self.runtime.snapshot()
        return {}

    def runtime_reload(self, saved=None):
        if self.runtime and hasattr(self.runtime, "reload_config"):
            return self.runtime.reload_config(saved)
        return saved or config.load_config()

    def show_settings(self):
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self)
            self.settings_window.destroyed.connect(lambda: setattr(self, "settings_window", None))
        else:
            self.settings_window.load_settings(config.load_config())
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()
        return self.settings_window

    def show_diagnostics(self):
        if self.diagnostics_window is None:
            self.diagnostics_window = DiagnosticsWindow(self)
            self.diagnostics_window.destroyed.connect(lambda: setattr(self, "diagnostics_window", None))
        self.diagnostics_window.refresh()
        self.diagnostics_window.show()
        self.diagnostics_window.raise_()
        self.diagnostics_window.activateWindow()
        return self.diagnostics_window

    def show_correction(self, snapshot=None):
        snapshot = snapshot if isinstance(snapshot, dict) else self.runtime_snapshot()
        raw = snapshot.get("raw_track") or snapshot.get("track") or {}
        current = snapshot.get("track") or raw
        if not raw.get("title"):
            QMessageBox.information(
                self.diagnostics_window or self.settings_window,
                "No current song",
                "Play a song in Amazon Music before correcting metadata.",
            )
            return None
        result = show_correction_dialog(
            raw,
            current,
            icon_path=self.icon_path,
            parent=self.diagnostics_window or self.settings_window,
        )
        if result and result.get("accepted") and self.runtime:
            remember = bool(result.get("remember"))
            self.runtime.apply_correction(
                result.get("raw_title", ""),
                result.get("raw_artist", ""),
                result.get("track") or {},
                remember=remember,
            )
            if self.diagnostics_window:
                detail = (
                    "Correction remembered for this detected song."
                    if remember
                    else "Correction applied for this app session."
                )
                self.diagnostics_window.status.setText(detail)
        return result

    def _apply_picker_result(self, raw, picked, *, remember=False):
        if not picked or not self.runtime:
            return None
        result = self.runtime.apply_correction(
            raw.get("title", ""),
            raw.get("artist", ""),
            picked,
            remember=remember,
        )
        if self.diagnostics_window:
            self.diagnostics_window.status.setText(
                "Correction remembered for this detected song."
                if remember
                else "Correction applied for this app session."
            )
        return result

    def show_guided_correction(self, snapshot=None):
        """Run the same Wrong Artist/Wrong Song picker flow as Windows."""

        snapshot = snapshot if isinstance(snapshot, dict) else self.runtime_snapshot()
        raw = snapshot.get("raw_track") or snapshot.get("track") or {}
        if not raw.get("title"):
            return self.show_correction(snapshot)
        parent = self.diagnostics_window or self.settings_window
        choice = show_wrong_song_dialog(icon_path=self.icon_path, parent=parent).get(
            "choice"
        )
        if not choice:
            return None

        from Windows.album_art import search_tracks

        if choice == "title":
            picked = show_input_picker(
                raw.get("artist", ""),
                search_fn=search_tracks,
                icon_path=self.icon_path,
                parent=parent,
            )
            return self._apply_picker_result(raw, picked, remember=False)

        def search():
            return search_tracks(raw.get("title", ""), limit=5)

        def choose(choices):
            if not choices:
                QMessageBox.information(
                    parent,
                    "No matches",
                    "No matching songs were found. You can still use the manual correction fields in Diagnostics.",
                )
                return
            result = show_choice_picker(
                raw.get("title", ""),
                choices,
                search_query=raw.get("title", ""),
                page_size=5,
                prompt="Select the correct track:",
                remember=True,
                search_fn=search_tracks,
                icon_path=self.icon_path,
                parent=parent,
            )
            self._apply_picker_result(
                raw,
                result.get("track") if result else None,
                remember=bool(result and result.get("remember")),
            )

        self.run_background(
            search,
            choose,
            lambda error: QMessageBox.warning(parent, "Search failed", error),
        )
        return {"pending": True}

    def run_background(self, function, on_success=None, on_error=None):
        worker = _Worker(function)
        self._workers.add(worker)

        def finished(value=None):
            self._workers.discard(worker)
            if on_success:
                on_success(value)

        def failed(error):
            self._workers.discard(worker)
            if on_error:
                on_error(error)
            else:
                QMessageBox.warning(self.settings_window, "Operation failed", error)

        worker.signals.succeeded.connect(finished)
        worker.signals.failed.connect(failed)
        self.thread_pool.start(worker)
        return worker

    def validate_listenbrainz(self, token, callback=None):
        def task():
            import requests

            response = requests.get(
                "https://api.listenbrainz.org/1/validate-token",
                headers={"Authorization": f"Token {token}"},
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("valid"):
                return {"valid": True, "user_name": payload.get("user_name", "")}
            return {"valid": False, "error": "Invalid token. Check it and try again."}

        return self.run_background(
            task,
            callback,
            lambda error: callback({"valid": False, "error": f"Could not validate: {error}"}) if callback else None,
        )

    def lastfm_auth(self, callback=None):
        def task():
            from Windows.lastfm import get_auth_url

            settings = config.load_config()
            url, generator = get_auth_url(
                settings.get("lastfm_api_key"), settings.get("lastfm_api_secret")
            )
            self._lastfm_generator = generator
            self._lastfm_auth_url = url
            webbrowser.open(url)
            return {"ok": True, "url": url}

        return self.run_background(
            task,
            callback,
            lambda error: callback({"ok": False, "error": error}) if callback else None,
        )

    def lastfm_complete(self, callback=None):
        if not self._lastfm_generator or not self._lastfm_auth_url:
            result = {"ok": False, "error": "Start authentication in the browser first."}
            if callback:
                callback(result)
            return None

        def task():
            from Windows.lastfm import complete_auth

            session_key, username = complete_auth(self._lastfm_generator, self._lastfm_auth_url)
            self._lastfm_generator = None
            self._lastfm_auth_url = None
            saved = config.update_config_fields(
                {
                    "lastfm_session_key": session_key,
                    "lastfm_username": username,
                    "lastfm_enabled": True,
                }
            )
            self.runtime_reload(saved)
            return {"ok": True, "username": username}

        return self.run_background(
            task,
            callback,
            lambda error: callback({"ok": False, "error": error}) if callback else None,
        )

    def check_updates(self):
        parent = self.settings_window or self.diagnostics_window

        def task():
            try:
                from .updater import check_for_update
            except ImportError:
                try:
                    from updater import check_for_update
                except ImportError:
                    return None
            return check_for_update()

        def done(update):
            if update is None:
                QDesktopServices.openUrl(QUrl(RELEASES_URL))
                return
            available = bool(getattr(update, "available", False))
            error = str(getattr(update, "error", "") or "")
            if not available:
                QMessageBox.information(
                    parent,
                    "Software Update",
                    f"{config.APP_DISPLAY_NAME} {config.APP_VERSION} is up to date."
                    if not error
                    else f"Could not check for updates:\n{error}",
                )
                return
            version = str(getattr(update, "version", "new version") or "new version")
            changelog = str(getattr(update, "changelog", "") or "")[:1200]
            choice = QMessageBox.question(
                parent,
                "Update available",
                f"Amazon Music RPC {version} is available.\n\n{changelog}\n\nDownload and open the DMG?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if choice != QMessageBox.StandardButton.Yes:
                return
            if not getattr(update, "dmg_url", "") or not getattr(update, "expected_sha256", ""):
                QDesktopServices.openUrl(QUrl(str(getattr(update, "release_url", "") or RELEASES_URL)))
                return
            try:
                from .updater import download_and_open_dmg
            except ImportError:
                try:
                    from updater import download_and_open_dmg
                except ImportError:
                    QDesktopServices.openUrl(
                        QUrl(str(getattr(update, "release_url", "") or RELEASES_URL))
                    )
                    return
            self.run_background(
                lambda: download_and_open_dmg(update),
                lambda _result: QMessageBox.information(parent, "Update downloaded", "The update DMG has been opened."),
            )

        return self.run_background(task, done)

    def report_issue(self):
        snapshot = self.runtime_snapshot()
        query = urlencode(
            {
                "template": "bug_report.md",
                "title": "[macOS] ",
                "body": (
                    "<!-- Attach the redacted diagnostic JSON from the Diagnostics window. -->\n\n"
                    f"Version: {config.APP_VERSION}\n"
                    f"Metadata source: {snapshot.get('source', 'unknown')}\n"
                ),
            }
        )
        QDesktopServices.openUrl(QUrl(f"{ISSUES_URL}?{query}"))

    def open_amazon_music(self):
        if self.on_open_amazon:
            return self.on_open_amazon()
        return subprocess.Popen(["/usr/bin/open", "-a", "Amazon Music"])

    def quit(self):
        if self.on_quit:
            return self.on_quit()
        if self.runtime and hasattr(self.runtime, "stop"):
            self.runtime.stop()
        self.app.quit()

    def shutdown(self):
        if self.runtime and hasattr(self.runtime, "remove_listener"):
            self.runtime.remove_listener(self._runtime_listener)
        for window in (self.settings_window, self.diagnostics_window):
            if window:
                window.close()
