# MIT License - Copyright (c) 2026 eripum9

"""Shared PySide6 track-choice and correction dialogs.

The public helpers intentionally return plain dictionaries so callers can use
the dialogs in-process or through the Windows JSON-file subprocess protocol.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


BG = "#18191c"
CARD = "#232428"
CARD_HOVER = "#2b2d31"
INPUT = "#1e1f22"
BORDER = "#3f4147"
TEXT = "#f2f3f5"
MUTED = "#a8aeb8"
ACCENT = "#5865f2"
ACCENT_HOVER = "#4752c4"
DANGER = "#da373c"
MAX_ARTWORK_BYTES = 5 * 1024 * 1024

STYLE = f"""
QDialog, QWidget#pickerRoot {{ background: {BG}; color: {TEXT}; }}
QLabel {{ color: {TEXT}; }}
QLabel[muted="true"] {{ color: {MUTED}; }}
QFrame#trackCard {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 9px; }}
QFrame#trackCard:hover {{ background: {CARD_HOVER}; }}
QLineEdit, QDoubleSpinBox, QPlainTextEdit {{
    background: {INPUT}; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 7px;
}}
QLineEdit:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
QPushButton {{
    background: #34363c; color: {TEXT}; border: 1px solid #484b52;
    border-radius: 6px; padding: 7px 14px; font-weight: 600;
}}
QPushButton:hover {{ background: #404249; }}
QPushButton:disabled {{ color: #6d6f78; background: #25262a; }}
QPushButton[primary="true"] {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}
QPushButton[primary="true"]:hover {{ background: {ACCENT_HOVER}; }}
QCheckBox, QRadioButton {{ color: {TEXT}; spacing: 8px; }}
QScrollArea {{ border: 0; background: transparent; }}
"""


def track_payload(track):
    """Return the stable subset accepted by the correction pipeline."""
    track = track if isinstance(track, dict) else {}
    try:
        duration = max(0.0, float(track.get("duration") or 0))
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "title": str(track.get("title") or "").strip(),
        "artist": str(track.get("artist") or "").strip(),
        "album": str(track.get("album") or "").strip(),
        "art_url": str(track.get("art_url") or "").strip(),
        "track_link": str(track.get("track_link") or "").strip(),
        "duration": duration,
    }


def search_page(query, page_size, page, search_fn=None):
    """Fetch a deterministic page while supporting legacy search callables."""
    page_size = max(1, int(page_size or 5))
    offset = max(0, int(page or 0)) * page_size
    if search_fn:
        try:
            value = search_fn(query, limit=page_size, offset=offset)
        except TypeError:
            value = [] if offset else search_fn(query, limit=page_size)
        return list(value or [])
    try:
        from Windows.album_art import search_tracks
    except ImportError:
        from album_art import search_tracks
    return list(search_tracks(query, limit=page_size, offset=offset) or [])


def _application():
    app = QApplication.instance()
    owns = app is None
    if app is None:
        app = QApplication([])
        app.setApplicationName("Amazon Music RPC")
        app.setOrganizationName("eripum9")
    return app, owns


def _set_icon(widget, icon_path):
    if icon_path and Path(icon_path).is_file():
        widget.setWindowIcon(QIcon(str(icon_path)))


class TrackChoiceDialog(QDialog):
    def __init__(
        self,
        title,
        choices,
        *,
        search_query=None,
        page_size=5,
        prompt="No artist found. Select the correct track:",
        remember=True,
        search_fn=None,
        icon_path=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("pickerRoot")
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Amazon Music RPC — Choose track")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumWidth(570)
        self.setMaximumWidth(720)
        _set_icon(self, icon_path)

        self.search_query = str(search_query or "").strip()
        self.page_size = max(1, int(page_size or 5))
        self.search_fn = search_fn
        self.pages = {0: list(choices or [])}
        self.exhausted_pages = set()
        self.current_page = 0
        self.result_payload = {"index": -1, "remember": False, "track": None}
        self._network = QNetworkAccessManager(self)
        self._replies = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(10)
        heading = QLabel(f'“{str(title or "").strip()}”')
        heading.setStyleSheet("font-size: 16px; font-weight: 700;")
        heading.setWordWrap(True)
        root.addWidget(heading)
        hint = QLabel(prompt)
        hint.setProperty("muted", True)
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumHeight(250)
        self.rows = QWidget()
        self.rows.setObjectName("pickerRoot")
        self.rows_layout = QVBoxLayout(self.rows)
        self.rows_layout.setContentsMargins(0, 2, 0, 2)
        self.rows_layout.setSpacing(7)
        self.scroll.setWidget(self.rows)
        root.addWidget(self.scroll, 1)

        self.status = QLabel("")
        self.status.setProperty("muted", True)
        root.addWidget(self.status)

        self.remember = QCheckBox("Always use this result for this title")
        self.remember.setVisible(bool(remember))
        root.addWidget(self.remember)

        nav = QHBoxLayout()
        self.previous = QPushButton("Previous")
        self.previous.clicked.connect(lambda: self.load_page(self.current_page - 1))
        nav.addWidget(self.previous)
        self.page_label = QLabel("Page 1")
        self.page_label.setProperty("muted", True)
        nav.addWidget(self.page_label)
        self.next = QPushButton("Next")
        self.next.clicked.connect(lambda: self.load_page(self.current_page + 1))
        nav.addWidget(self.next)
        nav.addStretch(1)
        skip = QPushButton("Skip")
        skip.clicked.connect(self.reject)
        nav.addWidget(skip)
        self.select = QPushButton("Select")
        self.select.setProperty("primary", True)
        self.select.clicked.connect(self._select)
        nav.addWidget(self.select)
        root.addLayout(nav)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.render_choices()

    def _clear_rows(self):
        for reply in list(self._replies):
            reply.abort()
            reply.deleteLater()
        self._replies.clear()
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

    def _request_art(self, label, url):
        parsed = QUrl(str(url or ""))
        if not parsed.isValid() or parsed.scheme() not in {"https", "http"}:
            return
        reply = self._network.get(QNetworkRequest(parsed))
        self._replies.add(reply)
        reply.downloadProgress.connect(
            lambda received, total, item=reply: item.abort()
            if received > MAX_ARTWORK_BYTES or total > MAX_ARTWORK_BYTES
            else None
        )

        def done():
            self._replies.discard(reply)
            data = reply.readAll().data()
            pixmap = QPixmap()
            if data and pixmap.loadFromData(data):
                try:
                    label.setPixmap(
                        pixmap.scaled(
                            QSize(56, 56),
                            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                except RuntimeError:  # The user changed pages while artwork loaded.
                    pass
            reply.deleteLater()

        reply.finished.connect(done)

    def render_choices(self):
        self._clear_rows()
        choices = self.pages.get(self.current_page, [])
        for index, choice in enumerate(choices):
            payload = track_payload(choice)
            card = QFrame()
            card.setObjectName("trackCard")
            layout = QHBoxLayout(card)
            layout.setContentsMargins(11, 9, 12, 9)
            radio = QRadioButton()
            self.group.addButton(radio, index)
            layout.addWidget(radio)
            art = QLabel("♫")
            art.setAlignment(Qt.AlignmentFlag.AlignCenter)
            art.setFixedSize(56, 56)
            art.setStyleSheet("background: #35373c; border-radius: 6px; color: #777b84; font-size: 22px;")
            layout.addWidget(art)
            self._request_art(art, payload["art_url"])
            text = QVBoxLayout()
            title = QLabel(payload["title"] or "Untitled")
            title.setStyleSheet("font-size: 14px; font-weight: 700;")
            text.addWidget(title)
            artist = QLabel(payload["artist"] or "Unknown artist")
            text.addWidget(artist)
            album = QLabel(payload["album"] or "Album unavailable")
            album.setProperty("muted", True)
            text.addWidget(album)
            layout.addLayout(text, 1)
            card.mousePressEvent = lambda _event, button=radio: button.setChecked(True)
            self.rows_layout.addWidget(card)
        if not choices:
            empty = QLabel("No results found on this page.")
            empty.setProperty("muted", True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.rows_layout.addWidget(empty)
        self.rows_layout.addStretch(1)
        self.page_label.setText(f"Page {self.current_page + 1}")
        self.previous.setEnabled(self.current_page > 0)
        can_next = (
            bool(self.search_query)
            and self.current_page not in self.exhausted_pages
            and len(choices) >= self.page_size
        )
        self.next.setEnabled(can_next)
        self.select.setEnabled(bool(choices))

    def load_page(self, page):
        if page < 0:
            return
        if page in self.pages:
            self.current_page = page
            self.status.clear()
            self.render_choices()
            return
        if not self.search_query:
            return
        self.status.setText("Searching…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            tracks = search_page(self.search_query, self.page_size, page, self.search_fn)
        except Exception as error:
            self.status.setText(f"Search failed: {error}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        if not tracks:
            self.exhausted_pages.add(max(0, page - 1))
            self.status.setText("No more results.")
            self.render_choices()
            return
        self.pages[page] = tracks
        self.current_page = page
        if len(tracks) < self.page_size:
            self.exhausted_pages.add(page)
        self.status.clear()
        self.render_choices()

    def _select(self):
        index = self.group.checkedId()
        choices = self.pages.get(self.current_page, [])
        if not 0 <= index < len(choices):
            QMessageBox.information(self, "Choose a track", "Select a track first.")
            return
        self.result_payload = {
            "index": self.current_page * self.page_size + index,
            "remember": bool(self.remember.isVisible() and self.remember.isChecked()),
            "track": track_payload(choices[index]),
        }
        self.accept()


class TrackInputDialog(QDialog):
    def __init__(self, artist, *, search_fn=None, icon_path=None, parent=None):
        super().__init__(parent)
        self.setObjectName("pickerRoot")
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Amazon Music RPC — Find track")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumWidth(460)
        _set_icon(self, icon_path)
        self.artist = str(artist or "").strip()
        self.search_fn = search_fn
        self.result_payload = track_payload({})

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        title = QLabel(f'Artist: “{self.artist}”')
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(title)
        hint = QLabel("Could not identify the song. Enter its title to search.")
        hint.setProperty("muted", True)
        layout.addWidget(hint)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Song title")
        self.entry.returnPressed.connect(self._search)
        layout.addWidget(self.entry)
        self.status = QLabel("")
        self.status.setProperty("muted", True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        skip = QPushButton("Skip")
        skip.clicked.connect(self.reject)
        buttons.addWidget(skip)
        search = QPushButton("Search")
        search.setProperty("primary", True)
        search.clicked.connect(self._search)
        buttons.addWidget(search)
        layout.addLayout(buttons)
        QTimer.singleShot(0, self.entry.setFocus)

    def _search(self):
        title = self.entry.text().strip()
        if not title:
            self.status.setText("Enter a song title first.")
            return
        query = f"{title} {self.artist}".strip()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            tracks = search_page(query, 5, 0, self.search_fn)
        except Exception as error:
            self.status.setText(f"Search failed: {error}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        if not tracks:
            self.status.setText("No results found.")
            return
        picker = TrackChoiceDialog(
            title,
            tracks,
            search_query=query,
            page_size=5,
            prompt="Select the correct track:",
            remember=False,
            search_fn=self.search_fn,
            parent=self,
        )
        if picker.exec() == QDialog.DialogCode.Accepted and picker.result_payload["track"]:
            self.result_payload = picker.result_payload["track"]
            self.accept()


class WrongSongDialog(QDialog):
    def __init__(self, *, icon_path=None, parent=None):
        super().__init__(parent)
        self.setObjectName("pickerRoot")
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Amazon Music RPC — Correct metadata")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.choice = ""
        _set_icon(self, icon_path)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        title = QLabel("Did we make a mistake?")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        row = QHBoxLayout()
        for label, choice in (("Wrong artist", "artist"), ("Wrong song", "title")):
            button = QPushButton(label)
            button.setProperty("primary", True)
            button.clicked.connect(lambda _checked=False, value=choice: self._pick(value))
            row.addWidget(button)
        layout.addLayout(row)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

    def _pick(self, choice):
        self.choice = choice
        self.accept()


class CorrectionDialog(QDialog):
    """Edit metadata and optionally persist it as a raw-track mapping."""

    def __init__(self, raw_track, corrected=None, *, icon_path=None, parent=None):
        super().__init__(parent)
        self.setObjectName("pickerRoot")
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Amazon Music RPC — Correct this song")
        self.setMinimumWidth(560)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        _set_icon(self, icon_path)
        self.raw_track = track_payload(raw_track)
        current = track_payload(corrected or raw_track)
        self.result_payload = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        title = QLabel("Correct the detected metadata")
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        layout.addWidget(title)
        raw = QLabel(
            f"Detected as {self.raw_track['title'] or 'unknown title'}"
            f" — {self.raw_track['artist'] or 'unknown artist'}"
        )
        raw.setProperty("muted", True)
        raw.setWordWrap(True)
        layout.addWidget(raw)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        self.fields = {}
        for key, label in (
            ("title", "Title"),
            ("artist", "Artist"),
            ("album", "Album"),
            ("art_url", "Artwork URL"),
            ("track_link", "Song URL"),
        ):
            edit = QLineEdit(current[key])
            self.fields[key] = edit
            form.addRow(label, edit)
        self.duration = QDoubleSpinBox()
        self.duration.setRange(0, 86400)
        self.duration.setDecimals(1)
        self.duration.setSuffix(" seconds")
        self.duration.setValue(current["duration"])
        form.addRow("Duration", self.duration)
        layout.addLayout(form)
        self.remember = QCheckBox("Remember this correction for the detected title and artist")
        self.remember.setChecked(True)
        layout.addWidget(self.remember)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        save = buttons.button(QDialogButtonBox.StandardButton.Save)
        save.setText("Use correction")
        save.setProperty("primary", True)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._accept)
        layout.addWidget(buttons)

    def _accept(self):
        corrected = {key: edit.text().strip() for key, edit in self.fields.items()}
        corrected["duration"] = float(self.duration.value())
        if not corrected["title"]:
            QMessageBox.warning(self, "Missing title", "A corrected title is required.")
            return
        self.result_payload = {
            "accepted": True,
            "remember": self.remember.isChecked(),
            "raw_title": self.raw_track["title"],
            "raw_artist": self.raw_track["artist"],
            "track": corrected,
        }
        self.accept()


class LogConsoleWindow(QWidget):
    def __init__(self, log_file_path, *, icon_path=None):
        super().__init__()
        self.setObjectName("pickerRoot")
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Amazon Music RPC — Console")
        self.resize(760, 460)
        _set_icon(self, icon_path)
        self.path = str(log_file_path)
        self.position = 0
        layout = QVBoxLayout(self)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet("font-family: Menlo, Consolas, monospace;")
        layout.addWidget(self.text)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self.poll()

    def poll(self):
        try:
            with open(self.path, "r", encoding="utf-8", errors="replace") as handle:
                handle.seek(self.position)
                value = handle.read()
                self.position = handle.tell()
        except OSError:
            return
        if value:
            self.text.moveCursor(self.text.textCursor().MoveOperation.End)
            self.text.insertPlainText(value)
            self.text.ensureCursorVisible()


def show_choice_picker(
    title,
    choices,
    search_query=None,
    page_size=5,
    prompt="No artist found. Select the correct track:",
    remember=True,
    search_fn=None,
    icon_path=None,
    parent=None,
):
    app, _owns = _application()
    dialog = TrackChoiceDialog(
        title,
        choices,
        search_query=search_query,
        page_size=page_size,
        prompt=prompt,
        remember=remember,
        search_fn=search_fn,
        icon_path=icon_path,
        parent=parent,
    )
    dialog.exec()
    return dialog.result_payload


def show_input_picker(artist, search_fn=None, icon_path=None, parent=None):
    app, _owns = _application()
    dialog = TrackInputDialog(
        artist, search_fn=search_fn, icon_path=icon_path, parent=parent
    )
    dialog.exec()
    return dialog.result_payload


def show_wrong_song_dialog(icon_path=None, parent=None):
    app, _owns = _application()
    dialog = WrongSongDialog(icon_path=icon_path, parent=parent)
    dialog.exec()
    return {"choice": dialog.choice}


def show_correction_dialog(raw_track, corrected=None, icon_path=None, parent=None):
    app, _owns = _application()
    dialog = CorrectionDialog(
        raw_track, corrected, icon_path=icon_path, parent=parent
    )
    dialog.exec()
    return dialog.result_payload or {
        "accepted": False,
        "remember": False,
        "raw_title": str((raw_track or {}).get("title") or ""),
        "raw_artist": str((raw_track or {}).get("artist") or ""),
        "track": None,
    }


def show_console(log_file_path, icon_path=None):
    app, owns = _application()
    window = LogConsoleWindow(log_file_path, icon_path=icon_path)
    window.show()
    if owns:
        app.exec()
    return window
