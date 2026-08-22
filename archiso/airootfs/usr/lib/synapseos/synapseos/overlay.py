"""Super+S overlay. Thin client of synapse-core."""

from __future__ import annotations

import base64
import os
import signal
import subprocess
import sys
from pathlib import Path

from .client import ClientError, CoreClient
from .paths import cache_dir, overlay_pidfile

# Catppuccin Macchiato
CRUST = "#181926"
MANTLE = "#1e2030"
BASE = "#24273a"
SURFACE0 = "#363a4f"
TEXT = "#cad3f5"
SUBTEXT = "#a5adcb"
OVERLAY_C = "#6e738d"
MAUVE = "#c6a0f6"
GREEN = "#a6da95"
RED = "#ed8796"
BLUE = "#8aadf4"
YELLOW = "#eed49f"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--pause"]:
        try:
            with CoreClient() as cli:
                cli.call("synapse/set_paused", {"paused": True})
            return 0
        except ClientError as exc:
            print(exc, file=sys.stderr)
            return 1
    if argv == ["--resume"]:
        try:
            with CoreClient() as cli:
                cli.call("synapse/set_paused", {"paused": False})
            return 0
        except ClientError as exc:
            print(exc, file=sys.stderr)
            return 1

    if _toggle_existing():
        return 0

    try:
        from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread
        from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
        from PySide6.QtWidgets import (
            QApplication,
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as exc:
        print(f"synapseos-overlay needs PySide6: {exc}", file=sys.stderr)
        return 1

    os.environ.setdefault("QT_WAYLAND_APP_ID", "org.synapseos.overlay")
    app = QApplication(sys.argv)
    app.setApplicationName("Synapse")
    app.setDesktopFileName("synapseos-assistant")
    app.setQuitOnLastWindowClosed(True)

    win = Overlay()
    _write_pid()
    signal.signal(signal.SIGUSR1, lambda *_: win.toggle())
    win.show_centered()
    code = app.exec()
    _clear_pid()
    return code


def _toggle_existing() -> bool:
    path = overlay_pidfile()
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    if pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        os.kill(pid, signal.SIGUSR1)
        return True
    except OSError:
        return False


def _write_pid() -> None:
    overlay_pidfile().write_text(str(os.getpid()), encoding="utf-8")


def _clear_pid() -> None:
    try:
        overlay_pidfile().unlink()
    except OSError:
        pass


# Imported only after PySide6 is confirmed present.
def _qt():
    from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread
    from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
    return {
        "Qt": Qt, "QTimer": QTimer, "Signal": Signal, "QObject": QObject,
        "QThread": QThread, "QColor": QColor, "QFont": QFont,
        "QPainter": QPainter, "QPainterPath": QPainterPath, "QPen": QPen,
        "QApplication": QApplication, "QFrame": QFrame,
        "QHBoxLayout": QHBoxLayout, "QLabel": QLabel, "QLineEdit": QLineEdit,
        "QPushButton": QPushButton, "QTextEdit": QTextEdit,
        "QVBoxLayout": QVBoxLayout, "QWidget": QWidget,
    }


class Overlay:  # noqa: PLR0904 — UI surface
    def __init__(self):
        qt = _qt()
        Qt = qt["Qt"]
        QWidget = qt["QWidget"]
        QVBoxLayout = qt["QVBoxLayout"]
        QHBoxLayout = qt["QHBoxLayout"]
        QLabel = qt["QLabel"]
        QLineEdit = qt["QLineEdit"]
        QPushButton = qt["QPushButton"]
        QTextEdit = qt["QTextEdit"]
        QFont = qt["QFont"]
        QTimer = qt["QTimer"]
        Signal = qt["Signal"]
        QObject = qt["QObject"]
        QThread = qt["QThread"]
        QColor = qt["QColor"]
        QPainter = qt["QPainter"]
        QPainterPath = qt["QPainterPath"]
        QPen = qt["QPen"]

        class Card(QWidget):
            def paintEvent(self, event):  # noqa: ARG002
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing)
                path = QPainterPath()
                path.addRoundedRect(1, 1, self.width() - 2, self.height() - 2, 22, 22)
                painter.fillPath(path, QColor(MANTLE))
                pen = QPen(QColor(MAUVE))
                pen.setWidth(2)
                painter.setPen(pen)
                painter.drawPath(path)

        class Win(Card):
            toggled = Signal()

            def __init__(self):
                super().__init__()
                self.setWindowFlags(
                    Qt.FramelessWindowHint
                    | Qt.WindowStaysOnTopHint
                    | Qt.Tool
                    | Qt.Dialog
                )
                self.setAttribute(Qt.WA_TranslucentBackground)
                self.setAttribute(Qt.WA_ShowWithoutActivating, False)
                self.setWindowTitle("Synapse")
                self.setFixedWidth(720)
                self.setMinimumHeight(320)

        self._qt = qt
        self.win = Win()
        self.client: CoreClient | None = None
        self.last_ask = ""
        self.consent_id = ""
        self.recorder: subprocess.Popen | None = None
        self.wav_path = cache_dir() / "utt.wav"
        self._busy = False

        root = QVBoxLayout(self.win)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(10)

        top = QHBoxLayout()
        brand = QLabel("SYNAPSE")
        brand.setStyleSheet(f"color: {MAUVE}; font-weight: 700; letter-spacing: 2px;")
        brand.setFont(QFont("Inter", 10))
        self.chip = QLabel("…")
        self.chip.setStyleSheet(self._chip_css(GREEN))
        top.addWidget(brand)
        top.addStretch()
        top.addWidget(self.chip)
        root.addLayout(top)

        self.hint = QLabel("YOU ASKED")
        self.hint.setStyleSheet(f"color: {OVERLAY_C}; font-weight: 700; font-size: 11px;")
        root.addWidget(self.hint)

        self.asked = QLabel("What should the machine do?")
        self.asked.setWordWrap(True)
        self.asked.setStyleSheet(f"color: {TEXT}; font-size: 22px; font-weight: 600;")
        root.addWidget(self.asked)

        self.body = QTextEdit()
        self.body.setReadOnly(True)
        self.body.setFrameStyle(0)
        self.body.setStyleSheet(
            f"QTextEdit {{ background: {CRUST}; color: {TEXT}; border: none; "
            f"border-radius: 12px; padding: 10px; font-size: 14px; }}"
        )
        self.body.setFixedHeight(150)
        self.body.setPlaceholderText("Answer and proposed actions show up here.")
        root.addWidget(self.body)

        self.consent_row = QHBoxLayout()
        self.btn_allow = self._button("Allow once", GREEN, CRUST)
        self.btn_deny = self._button("Deny", RED, TEXT, outline=True)
        self.btn_allow.clicked.connect(lambda: self._decide(True))
        self.btn_deny.clicked.connect(lambda: self._decide(False))
        self.consent_row.addWidget(self.btn_allow)
        self.consent_row.addWidget(self.btn_deny)
        self.consent_row.addStretch()
        self.btn_allow.hide()
        self.btn_deny.hide()
        root.addLayout(self.consent_row)

        self.key_row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Paste XAI_API_KEY and press Enter")
        self.key_edit.setStyleSheet(self._input_css())
        self.key_edit.returnPressed.connect(self._save_key)
        self.key_row.addWidget(self.key_edit)
        root.addLayout(self.key_row)

        bottom = QHBoxLayout()
        self.mic = self._button("  hold to talk  ", MAUVE, CRUST)
        self.mic.setCheckable(False)
        self.mic.pressed.connect(self._mic_down)
        self.mic.released.connect(self._mic_up)
        self.input = QLineEdit()
        self.input.setPlaceholderText("open firefox · what’s running · why is it hot")
        self.input.setStyleSheet(self._input_css())
        self.input.returnPressed.connect(self._submit)
        bottom.addWidget(self.mic)
        bottom.addWidget(self.input, 1)
        root.addLayout(bottom)

        foot = QLabel("Esc dismisses   ·   Super+S toggles   ·   Ctrl+Alt+S pauses everything")
        foot.setStyleSheet(f"color: {OVERLAY_C}; font-size: 11px;")
        root.addWidget(foot)

        self.win.keyPressEvent = self._key  # type: ignore[method-assign]

        self._refresh_status()
        QTimer.singleShot(0, self.input.setFocus)

    def _button(self, label: str, bg: str, fg: str, outline: bool = False):
        qt = self._qt
        btn = qt["QPushButton"](label)
        if outline:
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {bg}; "
                f"border: 1px solid {bg}; border-radius: 18px; padding: 8px 16px; "
                f"font-weight: 600; }}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background: {bg}; color: {fg}; border: none; "
                f"border-radius: 18px; padding: 8px 16px; font-weight: 700; }}"
                f"QPushButton:pressed {{ opacity: 0.8; }}"
            )
        return btn

    def _input_css(self) -> str:
        return (
            f"QLineEdit {{ background: {SURFACE0}; color: {TEXT}; border: none; "
            f"border-radius: 14px; padding: 10px 14px; font-size: 14px; }}"
        )

    def _chip_css(self, color: str) -> str:
        return (
            f"color: {color}; background: {SURFACE0}; border-radius: 11px; "
            f"padding: 3px 10px; font-weight: 700; font-size: 11px;"
        )

    def show_centered(self) -> None:
        self.win.adjustSize()
        screen = self.win.screen()
        geo = screen.availableGeometry() if screen else None
        if geo:
            x = geo.x() + (geo.width() - self.win.width()) // 2
            y = geo.y() + int(geo.height() * 0.18)
            self.win.move(x, y)
        self.win.show()
        self.win.raise_()
        self.win.activateWindow()

    def toggle(self) -> None:
        if self.win.isVisible():
            self.win.hide()
        else:
            self.show_centered()

    def _key(self, event) -> None:
        Qt = self._qt["Qt"]
        if event.key() == Qt.Key_Escape:
            self.win.hide()
            self._qt["QApplication"].quit()
            return
        type(self.win).keyPressEvent(self.win, event)

    def _cli(self) -> CoreClient:
        if self.client is None:
            self.client = CoreClient()
            self.client.connect()
        return self.client

    def _refresh_status(self) -> None:
        try:
            st = self._cli().call("synapse/status")
        except ClientError as exc:
            self.chip.setText("CORE DOWN")
            self.chip.setStyleSheet(self._chip_css(RED))
            self.body.setPlainText(str(exc))
            return
        if st.get("paused"):
            self.chip.setText("PAUSED")
            self.chip.setStyleSheet(self._chip_css(RED))
        else:
            self.chip.setText(str(st.get("mode") or "assist").upper())
            self.chip.setStyleSheet(self._chip_css(GREEN if st.get("has_key") else YELLOW))
        self.key_edit.setVisible(not bool(st.get("has_key")))

    def _save_key(self) -> None:
        key = self.key_edit.text().strip()
        if not key:
            return
        try:
            self._cli().call("synapse/set_key", {"key": key})
        except ClientError as exc:
            self.body.setPlainText(str(exc))
            return
        self.key_edit.clear()
        self.key_edit.hide()
        self._refresh_status()
        self.body.setPlainText("API key saved. Ask something.")

    def _submit(self) -> None:
        text = self.input.text().strip()
        if not text or self._busy:
            return
        self.input.clear()
        self._ask(text)

    def _ask(self, text: str) -> None:
        self.last_ask = text
        self.asked.setText(text)
        self.body.setPlainText("…")
        self._hide_consent()
        self._busy = True
        try:
            result = self._cli().call(
                "synapse/ask",
                {"text": text},
                on_event=self._on_event,
            )
        except ClientError as exc:
            self.body.setPlainText(str(exc))
            self._busy = False
            self._refresh_status()
            return
        self._busy = False
        self._apply_result(result)

    def _on_event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "text":
            current = self.body.toPlainText()
            if current == "…":
                current = ""
            self.body.setPlainText(current + str(event.get("text") or ""))
        elif kind == "tool" and event.get("phase") == "start":
            current = self.body.toPlainText()
            if current == "…":
                current = ""
            self.body.setPlainText(current + f"\n→ {event.get('name')}")

    def _apply_result(self, result: dict) -> None:
        status = result.get("status")
        if status == "needs_key":
            self.key_edit.show()
            self.key_edit.setFocus()
            self.body.setPlainText("Paste an xAI API key to let Synapse talk to the model.")
            return
        if status == "needs_consent":
            self.consent_id = str(result.get("consent_id") or "")
            summary = str(result.get("summary") or "Allow this action?")
            existing = result.get("text") or ""
            self.body.setPlainText((existing + "\n\n" if existing else "") + summary)
            self.btn_allow.show()
            self.btn_deny.show()
            return
        if status == "error":
            self.body.setPlainText(str(result.get("error") or "error"))
            return
        text = str(result.get("text") or "").strip()
        if text:
            self.body.setPlainText(text)
        self._refresh_status()

    def _hide_consent(self) -> None:
        self.btn_allow.hide()
        self.btn_deny.hide()
        self.consent_id = ""

    def _decide(self, allow: bool) -> None:
        if not self.consent_id:
            return
        try:
            result = self._cli().call("synapse/consent", {
                "id": self.consent_id,
                "decision": "allow" if allow else "deny",
                "continue_text": self.last_ask if allow else "",
            })
        except ClientError as exc:
            self.body.setPlainText(str(exc))
            self._hide_consent()
            return
        self._hide_consent()
        if not allow:
            self.body.setPlainText("Denied.")
            return
        self._apply_result(result)

    def _mic_down(self) -> None:
        if self.recorder is not None:
            return
        self.wav_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.recorder = subprocess.Popen(
                [
                    "pw-record", "--format=s16", "--rate=16000", "--channels=1",
                    str(self.wav_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            self.recorder = subprocess.Popen(
                ["parecord", "--raw", "--rate=16000", "--channels=1", str(self.wav_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ) if _which("parecord") else None
        self.mic.setText("  listening…  ")

    def _mic_up(self) -> None:
        self.mic.setText("  hold to talk  ")
        rec = self.recorder
        self.recorder = None
        if rec is None:
            return
        rec.send_signal(signal.SIGINT)
        try:
            rec.wait(timeout=2)
        except subprocess.TimeoutExpired:
            rec.kill()
        if not self.wav_path.is_file() or self.wav_path.stat().st_size < 64:
            self.body.setPlainText("Didn’t catch that.")
            return
        audio = self.wav_path.read_bytes()
        try:
            result = self._cli().call("synapse/transcribe", {
                "audio_b64": base64.b64encode(audio).decode("ascii"),
            })
        except ClientError as exc:
            self.body.setPlainText(str(exc))
            return
        if not result.get("ok"):
            self.body.setPlainText(str(result.get("error") or "transcription failed"))
            return
        text = str(result.get("text") or "").strip()
        if not text:
            self.body.setPlainText("Didn’t catch that.")
            return
        self.input.setText(text)
        self._ask(text)


def _which(name: str) -> bool:
    from shutil import which
    return which(name) is not None


# Bind Overlay methods that close over Qt after main() imported it.
# The class above is constructed only from main() so imports succeed.
