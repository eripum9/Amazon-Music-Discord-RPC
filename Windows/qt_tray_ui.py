# MIT License - Copyright (c) 2026 eripum9

import os

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QFontMetrics, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QAbstractButton,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)


DRAWER_WIDTH = 336
DRAWER_HEIGHT = 464
TRAY_COMMANDS = {
    "settings",
    "diagnostics",
    "launch_amazon",
    "private",
    "game_mode",
    "wrong_song",
    "toggle_rpc",
    "updates",
    "quit",
}

COLORS = {
    "background": "#202020",
    "card": "#2d2d2d",
    "button": "#383838",
    "border": "#3d3d3d",
    "border_light": "#4a4a4a",
    "accent": "#5865f2",
    "success": "#43b581",
    "warning": "#faa61a",
    "error": "#f04747",
    "muted": "#999999",
    "muted_dark": "#888888",
    "text": "#f2f2f2",
}


def _clean(value):
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()


def _status_color(status):
    text = str(status or "").lower()
    if text in {"running", "connected", "found", "visible", "on", "standard", "amazon metadata"}:
        return COLORS["success"]
    if text in {"paused", "private", "waiting", "retrying", "hidden", "notification fallback"}:
        return COLORS["warning"]
    if text in {"error", "unavailable", "stopped", "off", "disconnected"}:
        return COLORS["error"]
    return COLORS["muted_dark"]


def drawer_geometry(anchor_x, anchor_y, screen_rect):
    screen_x, screen_y, screen_w, screen_h = screen_rect
    margin = 10
    x = int(anchor_x) - DRAWER_WIDTH + 24
    y = int(anchor_y) - DRAWER_HEIGHT - 8
    if y < screen_y + margin:
        y = int(anchor_y) + 8
    x = max(screen_x + margin, min(x, screen_x + screen_w - DRAWER_WIDTH - margin))
    y = max(screen_y + margin, min(y, screen_y + screen_h - DRAWER_HEIGHT - margin))
    return x, y, DRAWER_WIDTH, DRAWER_HEIGHT


def drawer_payload(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    private = bool(snapshot.get("private"))
    rpc_on = str(snapshot.get("rpc") or "").lower() == "on"
    source = _clean(snapshot.get("source") or "Waiting")
    status_label = "Private" if private else ("Paused" if source.lower() == "paused" else ("Running" if rpc_on else "Stopped"))
    title = _clean(snapshot.get("title"))
    artist = _clean(snapshot.get("artist"))
    album = _clean(snapshot.get("album"))
    time_label = _clean(snapshot.get("time"))
    if private:
        title = "Private session"
        artist = "Discord presence is hidden"
    elif not title:
        title = "Waiting for Amazon Music"
        artist = _clean(snapshot.get("source_detail") or "Amazon Music transport had no title")
    detail = artist or _clean(snapshot.get("source_detail") or source)
    meta = ""
    if album and time_label:
        meta = f"Album: {album} • Time: {time_label}"
    elif album:
        meta = f"Album: {album}"
    elif time_label:
        meta = f"Time: {time_label}"
    else:
        meta = source
    diagnostics = [
        ("RPC", "Running" if rpc_on else "Stopped"),
        ("Discord", _clean(snapshot.get("discord") or "Waiting")),
        ("DevTools", _clean(snapshot.get("devtools_status") or snapshot.get("devtools") or "Waiting")),
        ("Source", source),
        ("Privacy", "Private" if private else "Standard"),
    ]
    return {
        "status": status_label,
        "title": title,
        "detail": detail,
        "meta": meta,
        "private": private,
        "game_mode": str(snapshot.get("game_mode") or "").lower() == "on",
        "rpc_on": rpc_on,
        "diagnostics": diagnostics,
    }


class ElideLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._text = text
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def setText(self, text):
        self._text = str(text or "")
        super().setText(self._text)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        metrics = QFontMetrics(self.font())
        text = metrics.elidedText(self._text, Qt.TextElideMode.ElideRight, self.width())
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(self.rect(), self.alignment() | Qt.TextFlag.TextSingleLine, text)


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(48, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = COLORS["accent"] if self.isChecked() else "#666666"
        painter.setBrush(bg)
        painter.setPen(QPen("#777777" if not self.isChecked() else COLORS["accent"], 1))
        painter.drawRoundedRect(1, 1, 46, 24, 12, 12)
        knob_x = 24 if self.isChecked() else 3
        painter.setBrush("#ffffff")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(knob_x, 3, 20, 20)


class ActionButton(QPushButton):
    def __init__(self, text, command, bridge, parent=None):
        super().__init__(text, parent)
        self.command = command
        self.bridge = bridge
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(30)
        self.clicked.connect(self._clicked)

    def _clicked(self):
        self.bridge.command_requested.emit(self.command)


class TrayBridge(QObject):
    state_changed = Signal(dict)
    command_requested = Signal(str)
    hide_requested = Signal()
    stop_requested = Signal()


class TrayDrawer(QWidget):
    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.payload = drawer_payload({})
        self.setFixedSize(DRAWER_WIDTH, DRAWER_HEIGHT)
        self.setObjectName("drawer")
        self.setStyleSheet(self._style())
        self._build()
        self.bridge.state_changed.connect(self.apply_state)

    def _style(self):
        return f"""
        QWidget#drawer {{
            background: {COLORS["background"]};
            color: {COLORS["text"]};
            font-family: Segoe UI;
            font-size: 12px;
        }}
        QFrame#card {{
            background: {COLORS["card"]};
            border: 1px solid {COLORS["border"]};
            border-radius: 8px;
        }}
        QLabel#title {{
            font-size: 15px;
            font-weight: 700;
        }}
        QLabel#section {{
            color: {COLORS["muted"]};
            font-size: 11px;
            font-weight: 700;
        }}
        QLabel#muted {{
            color: {COLORS["muted"]};
            font-size: 11px;
        }}
        QLabel#value {{
            font-weight: 700;
        }}
        QPushButton {{
            background: {COLORS["button"]};
            border: 1px solid {COLORS["border_light"]};
            border-radius: 8px;
            color: {COLORS["text"]};
            font-size: 11px;
            font-weight: 700;
            padding: 4px 6px;
        }}
        QPushButton:hover {{
            background: #424242;
            border-color: {COLORS["accent"]};
        }}
        QPushButton:pressed {{
            background: {COLORS["accent"]};
        }}
        QPushButton#danger {{
            color: #ffd9d9;
        }}
        """

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        self.name_label = QLabel("Amazon Music RPC")
        self.name_label.setObjectName("title")
        self.status_pill = QLabel("Waiting")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_pill.setFixedHeight(22)
        self.status_pill.setMinimumWidth(72)
        header.addWidget(self.name_label)
        header.addStretch()
        header.addWidget(self.status_pill)
        root.addLayout(header)

        track_card = QFrame()
        track_card.setObjectName("card")
        track_layout = QVBoxLayout(track_card)
        track_layout.setContentsMargins(12, 10, 12, 10)
        track_layout.setSpacing(4)
        self.track_title = ElideLabel()
        self.track_title.setObjectName("title")
        self.track_detail = ElideLabel()
        self.track_detail.setObjectName("muted")
        self.track_meta = ElideLabel()
        self.track_meta.setObjectName("muted")
        track_layout.addWidget(self.track_title)
        track_layout.addWidget(self.track_detail)
        track_layout.addWidget(self.track_meta)
        root.addWidget(track_card)

        privacy_card = QFrame()
        privacy_card.setObjectName("card")
        privacy_layout = QHBoxLayout(privacy_card)
        privacy_layout.setContentsMargins(12, 9, 12, 9)
        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        privacy_title = QLabel("Private session")
        privacy_title.setObjectName("value")
        privacy_help = QLabel("Hide Discord presence while enabled")
        privacy_help.setObjectName("muted")
        text_box.addWidget(privacy_title)
        text_box.addWidget(privacy_help)
        self.private_toggle = ToggleSwitch()
        self.private_toggle.clicked.connect(self._private_clicked)
        privacy_layout.addLayout(text_box)
        privacy_layout.addStretch()
        privacy_layout.addWidget(self.private_toggle)
        root.addWidget(privacy_card)

        section = QLabel("MINI DIAGNOSTICS")
        section.setObjectName("section")
        root.addWidget(section)

        self.diagnostic_rows = []
        for label, value in self.payload["diagnostics"]:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            dot = QLabel("●")
            dot.setFixedWidth(12)
            name = QLabel(label)
            name.setObjectName("muted")
            val = ElideLabel(value)
            val.setObjectName("value")
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(dot)
            row.addWidget(name)
            row.addStretch()
            row.addWidget(val)
            root.addLayout(row)
            self.diagnostic_rows.append((dot, name, val))

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {COLORS['border']};")
        root.addWidget(divider)

        actions_label = QLabel("ACTIONS")
        actions_label.setObjectName("section")
        root.addWidget(actions_label)

        self.action_grid = QGridLayout()
        self.action_grid.setHorizontalSpacing(6)
        self.action_grid.setVerticalSpacing(6)
        actions = [
            ("Settings", "settings"),
            ("Diagnostics", "diagnostics"),
            ("Amazon", "launch_amazon"),
            ("Wrong Song", "wrong_song"),
            ("Stop RPC", "toggle_rpc"),
            ("Updates", "updates"),
            ("Game Mode", "game_mode"),
            ("Quit", "quit"),
        ]
        self.buttons = {}
        for index, (text, command) in enumerate(actions):
            button = ActionButton(text, command, self.bridge)
            if command == "quit":
                button.setObjectName("danger")
            self.buttons[command] = button
            self.action_grid.addWidget(button, index // 3, index % 3)
        root.addLayout(self.action_grid)

        root.addStretch(1)
        self.apply_state({})

    def _private_clicked(self):
        self.private_toggle.setEnabled(False)
        self.bridge.command_requested.emit("private")
        QTimer.singleShot(450, lambda: self.private_toggle.setEnabled(True))

    def apply_state(self, snapshot):
        self.payload = drawer_payload(snapshot)
        self.status_pill.setText(self.payload["status"])
        color = _status_color(self.payload["status"])
        self.status_pill.setStyleSheet(f"background: {color}; color: #101010; border-radius: 11px; font-size: 11px; font-weight: 800; padding: 0 8px;")
        self.track_title.setText(self.payload["title"])
        self.track_detail.setText(self.payload["detail"])
        self.track_meta.setText(self.payload["meta"])
        self.private_toggle.blockSignals(True)
        self.private_toggle.setChecked(bool(self.payload["private"]))
        self.private_toggle.blockSignals(False)
        self.buttons["toggle_rpc"].setText("Stop RPC" if self.payload["rpc_on"] else "Start RPC")
        self.buttons["game_mode"].setText("Game Mode On" if self.payload["game_mode"] else "Game Mode")
        for index, (label, value) in enumerate(self.payload["diagnostics"]):
            dot, name, val = self.diagnostic_rows[index]
            dot.setStyleSheet(f"color: {_status_color(value)};")
            name.setText(label)
            val.setText(value)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.bridge.hide_requested.emit()
            return
        super().keyPressEvent(event)


class QtTrayController(QObject):
    def __init__(self, icon_path, callbacks, initial_state=None):
        super().__init__()
        self.app = QApplication.instance() or QApplication([])
        self.app.setQuitOnLastWindowClosed(False)
        self.callbacks = callbacks
        self.bridge = TrayBridge()
        self.drawer = TrayDrawer(self.bridge)
        self.bridge.state_changed.connect(self._apply_state)
        self.bridge.command_requested.connect(self._run_command)
        self.bridge.hide_requested.connect(self._hide_menu)
        self.bridge.stop_requested.connect(self._stop_from_qt)
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self._icon(icon_path))
        self.tray.setToolTip("Amazon Music RPC")
        self.menu = self._drawer_menu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._activated)
        self.tray.show()
        if initial_state:
            self.update_state(initial_state)

    def _icon(self, icon_path):
        if icon_path and os.path.exists(icon_path):
            return QIcon(icon_path)
        return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)

    def _drawer_menu(self):
        menu = QMenu()
        menu.setObjectName("trayDrawerMenu")
        menu.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, False)
        menu.setStyleSheet(f"""
        QMenu#trayDrawerMenu {{
            background: {COLORS["background"]};
            border: 1px solid {COLORS["border"]};
            border-radius: 8px;
            padding: 0;
            margin: 0;
        }}
        QMenu#trayDrawerMenu::item {{
            padding: 0;
            margin: 0;
            background: transparent;
        }}
        """)
        action = QWidgetAction(menu)
        action.setDefaultWidget(self.drawer)
        menu.addAction(action)
        return menu

    def _activated(self, reason):
        name = getattr(reason, "name", str(reason))
        print(f"[Tray] Activation: {name}")
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_drawer()

    def _screen_tuple(self, point):
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        rect = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        return rect.x(), rect.y(), rect.width(), rect.height()

    def _anchor_point(self):
        rect = self.tray.geometry()
        if rect and rect.isValid() and rect.width() > 0 and rect.height() > 0:
            return rect.center()
        return QCursor.pos()

    def toggle_drawer(self):
        if self.menu.isVisible():
            self.menu.hide()
            return
        point = self._anchor_point()
        self._show_menu(point)

    def _show_menu(self, point=None):
        point = point or self._anchor_point()
        x, y, width, height = drawer_geometry(point.x(), point.y(), self._screen_tuple(point))
        self.menu.setFixedSize(width, height)
        self.menu.popup(QPoint(x, y))

    def _hide_menu(self):
        self.menu.hide()

    def update_state(self, snapshot):
        self.bridge.state_changed.emit(dict(snapshot or {}))

    def _apply_state(self, snapshot):
        title = str(snapshot.get("tooltip") or "") if isinstance(snapshot, dict) else ""
        if not title and isinstance(snapshot, dict):
            track_title = snapshot.get("title") or ""
            artist = snapshot.get("artist") or ""
            title = f"{track_title} - {artist}" if track_title and artist else (track_title or "Amazon Music RPC")
        self.tray.setToolTip(title or "Amazon Music RPC")

    def _run_command(self, command):
        command = str(command or "").strip()
        if command not in TRAY_COMMANDS:
            return
        self.menu.hide()
        callback = self.callbacks.get(command)
        if callback:
            callback()

    def run(self):
        return self.app.exec()

    def stop(self):
        self.bridge.stop_requested.emit()

    def _stop_from_qt(self):
        self.menu.hide()
        self.tray.hide()
        self.app.quit()


def tray_available():
    app = QApplication.instance() or QApplication([])
    return QSystemTrayIcon.isSystemTrayAvailable()
