
"""Системные toast-уведомления Support Bot."""

import os
import subprocess
import webbrowser
from datetime import datetime

from PyQt6.QtCore import (
    Qt,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    pyqtSignal,
    QObject,
)
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QGraphicsOpacityEffect,
    QSizePolicy,
)


# ============================================================
# НАСТРОЙКИ
# ============================================================

from paths import CHROME_EXE, CHROME_PROFILE
from config import load_config

_cfg = load_config()
BASE_URL = _cfg["base_url"]

WIDTH = 410
MARGIN = 22
SPACING = 10

SHOW_MS = 15000
ANIM_MS = 220

FONT = "Segoe UI"

COLORS = {
    "auto": {
        "bg": "#101F36",
        "accent": "#3977FF",
        "border": "#243D63",
        "label": "AUTO",
    },
    "suggest": {
        "bg": "#242333",
        "accent": "#FFAD32",
        "border": "#493C37",
        "label": "SUGGEST",
    },
    "escalate": {
        "bg": "#291D2B",
        "accent": "#FF4359",
        "border": "#4A293B",
        "label": "ESCALATE",
    },
}

# Обработчики назначаются главным окном приложения.
_open_callback = None
_send_callback = None
_skip_callback = None


def set_handlers(on_open=None, on_send=None, on_skip=None):
    """Подключает действия главного окна к системным уведомлениям."""
    global _open_callback, _send_callback, _skip_callback

    _open_callback = on_open
    _send_callback = on_send
    _skip_callback = on_skip


def _open_in_bot_chrome(href):
    """Открывает заявку в отдельном профиле Chrome."""
    if not href:
        return

    url = (
        href
        if href.startswith(("http://", "https://"))
        else BASE_URL.rstrip("/") + "/" + href.lstrip("/")
    )

    try:
        if os.path.isfile(CHROME_EXE):
            os.makedirs(CHROME_PROFILE, exist_ok=True)
            subprocess.Popen([
                CHROME_EXE,
                f"--user-data-dir={CHROME_PROFILE}",
                url,
            ])
        else:
            webbrowser.open(url)
    except Exception as exc:
        print(f"[notifier] Не удалось открыть заявку: {exc}")


def _invoke(callback, ticket, href):
    """Безопасно вызывает callback с номером заявки и её URL."""
    if callback is None:
        return

    try:
        callback(str(ticket), str(href))
    except TypeError:
        # Совместимость с обработчиками, принимающими только номер.
        try:
            callback(str(ticket))
        except Exception as exc:
            print(f"[notifier] Ошибка обработчика: {exc}")
    except Exception as exc:
        print(f"[notifier] Ошибка обработчика: {exc}")


# ============================================================
# TOAST
# ============================================================

class Toast(QWidget):
    closed = pyqtSignal(object)

    def __init__(self, ticket, href, action, message):
        super().__init__()

        self.ticket = str(ticket)
        self.href = str(href or "")
        self.action = str(action or "auto").lower()
        self.closing = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.setFixedWidth(WIDTH)
        self.setFont(QFont(FONT, 10))

        self._build(message)

        self.opacity = QGraphicsOpacityEffect(self)
        self.opacity.setOpacity(0.0)
        self.setGraphicsEffect(self.opacity)

        self.anim = QPropertyAnimation(self.opacity, b"opacity", self)
        self.anim.setDuration(ANIM_MS)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fade_out)
        self.timer.start(SHOW_MS)

    @staticmethod
    def _font(size, bold=False):
        font = QFont(FONT, size)
        font.setBold(bold)
        return font

    def _make_button(self, text, background, hover, border, callback):
        button = QPushButton(text)
        button.setFont(self._font(9, True))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(35)
        button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: {background};
                color: #FFFFFF;
                border: 1px solid {border};
                border-radius: 8px;
                padding: 7px 9px;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {background};
            }}
        """)
        button.clicked.connect(callback)
        return button

    def _build(self, message):
        palette = COLORS.get(self.action, COLORS["auto"])
        bg = palette["bg"]
        accent = palette["accent"]
        border = palette["border"]

        frame = QFrame(self)
        frame.setObjectName("toastFrame")
        frame.setStyleSheet(f"""
            QFrame#toastFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-left: 5px solid {accent};
                border-radius: 13px;
            }}
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 13)
        layout.setSpacing(10)

        # Шапка
        header = QHBoxLayout()
        header.setSpacing(10)

        icon = QLabel("●")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(42, 42)
        icon.setStyleSheet(f"""
            QLabel {{
                background-color: {accent};
                color: white;
                border: none;
                border-radius: 21px;
                font-size: 23px;
                font-weight: 700;
            }}
        """)
        header.addWidget(icon)

        info = QVBoxLayout()
        info.setSpacing(5)

        title = QLabel("Support Bot")
        title.setFont(self._font(12, True))
        title.setStyleSheet("color: #F4F7FF; border: none;")
        info.addWidget(title)

        meta = QHBoxLayout()
        meta.setSpacing(7)

        badge = QLabel(palette["label"])
        badge.setFont(self._font(8, True))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"""
            QLabel {{
                color: {accent};
                background-color: {bg};
                border: 1px solid {accent};
                border-radius: 7px;
                padding: 3px 7px;
            }}
        """)
        meta.addWidget(badge)

        ticket_label = QLabel(f"Заявка {self.ticket}")
        ticket_label.setFont(self._font(9))
        ticket_label.setStyleSheet("color: #A8BCDE; border: none;")
        ticket_label.setWordWrap(True)
        meta.addWidget(ticket_label, 1)

        info.addLayout(meta)
        header.addLayout(info, 1)

        right = QVBoxLayout()
        right.setSpacing(4)

        time_label = QLabel(datetime.now().strftime("%H:%M"))
        time_label.setFont(self._font(9))
        time_label.setStyleSheet("color: #91A8CF; border: none;")
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(time_label)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(25, 25)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8FA4C7;
                border: none;
                font-size: 23px;
            }
            QPushButton:hover {
                color: white;
                background: #263A58;
                border-radius: 7px;
            }
        """)
        close_btn.clicked.connect(self.fade_out)
        right.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)

        header.addLayout(right)
        layout.addLayout(header)

        # Текст
        body = QLabel(str(message))
        body.setFont(self._font(10))
        body.setWordWrap(True)
        body.setMinimumWidth(0)
        body.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        body.setStyleSheet("""
            QLabel {
                color: #DCE6F8;
                background: transparent;
                border: none;
                padding: 1px 2px;
            }
        """)
        layout.addWidget(body)

        # Открыть заявку
        open_btn = self._make_button(
            "Открыть заявку",
            accent,
            "#285BC7",
            accent,
            self.open_ticket,
        )
        layout.addWidget(open_btn)

        # Отправить / пропустить
        actions = QHBoxLayout()
        actions.setSpacing(8)

        send_btn = self._make_button(
            "✓  Отправить",
            "#12664F",
            "#168568",
            "#20A77D",
            self.send_reply,
        )

        skip_btn = self._make_button(
            "→  Пропустить",
            "#172A43",
            "#263E5F",
            "#345276",
            self.skip_ticket,
        )

        actions.addWidget(send_btn, 1)
        actions.addWidget(skip_btn, 1)
        layout.addLayout(actions)

        hint = QLabel("Нажмите на карточку, чтобы перейти в Support Bot")
        hint.setFont(self._font(8))
        hint.setStyleSheet("color: #8197BA; border: none;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def open_ticket(self):
        # Открываем окно приложения и выбираем нужную заявку.
        _invoke(_open_callback, self.ticket, self.href)

        # Дополнительно открываем ссылку заявки в браузере.
        _open_in_bot_chrome(self.href)
        self.fade_out()

    def send_reply(self):
        _invoke(_send_callback, self.ticket, self.href)
        self.fade_out()

    def skip_ticket(self):
        _invoke(_skip_callback, self.ticket, self.href)
        self.fade_out()

    def mousePressEvent(self, event):
        # Клик по свободной области карточки открывает приложение.
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())

            # Нажатия на кнопки обрабатываются их собственными сигналами.
            if not isinstance(child, QPushButton):
                _invoke(_open_callback, self.ticket, self.href)
                self.fade_out()

        super().mousePressEvent(event)

    def fade_out(self):
        if self.closing:
            return

        self.closing = True
        self.timer.stop()

        self.fade = QPropertyAnimation(self.opacity, b"opacity", self)
        self.fade.setDuration(ANIM_MS)
        self.fade.setStartValue(self.opacity.opacity())
        self.fade.setEndValue(0.0)
        self.fade.setEasingCurve(QEasingCurve.Type.InCubic)
        self.fade.finished.connect(self._finish)
        self.fade.start()

    def _finish(self):
        self.closed.emit(self)
        self.close()
        self.deleteLater()


# ============================================================
# МЕНЕДЖЕР УВЕДОМЛЕНИЙ
# ============================================================

class _ToastManager(QObject):
    request_show = pyqtSignal(str, str, str, str)

    def __init__(self):
        super().__init__()
        self.toasts = []
        self.request_show.connect(
            self._show,
            Qt.ConnectionType.QueuedConnection,
        )

    def show_toast(self, ticket, href, action, message):
        self.request_show.emit(
            str(ticket),
            str(href or ""),
            str(action or "auto"),
            str(message),
        )

    def _show(self, ticket, href, action, message):
        toast = Toast(ticket, href, action, message)
        toast.closed.connect(self._closed)

        self.toasts.append(toast)
        self._position()

        toast.show()
        toast.anim.start()

    def _closed(self, toast):
        if toast in self.toasts:
            self.toasts.remove(toast)
        self._position()

    def _position(self):
        app = QApplication.instance()
        if not app or not app.primaryScreen():
            return

        screen = app.primaryScreen().availableGeometry()
        bottom = screen.bottom() - MARGIN

        for toast in reversed(self.toasts):
            toast.adjustSize()
            height = toast.sizeHint().height()
            toast.resize(WIDTH, height)

            x = screen.right() - WIDTH - MARGIN
            y = bottom - height

            toast.move(x, y)
            bottom = y - SPACING


_manager = None


def init_manager():
    """Вызвать в главном потоке до запуска агента."""
    return _get_manager()


def _get_manager():
    global _manager

    if _manager is None:
        _manager = _ToastManager()

    return _manager


def notify(ticket, href, action, message, on_click_cb=None):
    """Показывает системное уведомление."""
    if on_click_cb is not None:
        # Обратная совместимость со старым интерфейсом.
        set_handlers(on_open=lambda ticket_id, url: on_click_cb())

    _get_manager().show_toast(ticket, href, action, message)
