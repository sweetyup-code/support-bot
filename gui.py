# gui.py
# Support Bot — интерфейс по предоставленному макету
# PyQt6

import sys
import queue
import threading
from datetime import datetime

from PyQt6.QtCore import (
    Qt, QObject, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve,
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QLinearGradient, QBrush, QPen,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QScrollArea, QTextEdit, QSizePolicy, QGraphicsDropShadowEffect,
)

import agent as agent_module
import notifier as notifier_module


# ============================================================
# CONFIG
# ============================================================

APP_NAME = "Support Bot"

COLORS = {
    "window": "#0B1423",
    "sidebar": "#091321",
    "surface": "#0D192B",
    "surface_light": "#122139",
    "surface_hover": "#192B45",
    "border": "#20334F",
    "border_light": "#2B4163",
    "text": "#F3F6FF",
    "muted": "#A1B3D6",
    "muted_dark": "#7388B1",
    "blue": "#3474FF",
    "blue_light": "#4C8CFF",
    "blue_dark": "#2146BA",
    "cyan": "#39D8D0",
    "green": "#36DDB6",
    "amber": "#FFAD36",
    "red": "#FF405B",
}

ACTION_COLORS = {
    "auto":     {"accent": "#397AFF", "soft": "#142B53", "label": "AUTO"},
    "suggest":  {"accent": "#FFAD36", "soft": "#39291A", "label": "SUGGEST"},
    "escalate": {"accent": "#FF405B", "soft": "#391C2B", "label": "ESCALATE"},
}

FONT = "Segoe UI"
WINDOW_MIN_WIDTH = 1240
WINDOW_MIN_HEIGHT = 760


# ============================================================
# EVENT BRIDGE
# ============================================================

class EventBridge(QObject):
    event = pyqtSignal(dict)


class QueueWrapper:
    """Передаёт события агента в GUI через Qt-сигнал."""

    def __init__(self, q, bridge):
        self.q = q
        self.bridge = bridge

    def put(self, item):
        self.q.put(item)
        self.bridge.event.emit(item)

    def get(self, *args, **kwargs):
        return self.q.get(*args, **kwargs)

    def get_nowait(self):
        return self.q.get_nowait()

    def empty(self):
        return self.q.empty()


# ============================================================
# HELPERS
# ============================================================

def make_label(text, size=12, color=None, bold=False, parent=None):
    label = QLabel(text, parent)
    label.setFont(
        QFont(FONT, size, QFont.Weight.Bold if bold else QFont.Weight.Normal)
    )
    label.setStyleSheet(f"color: {color or COLORS['text']}; background: transparent;")
    return label


def make_panel(parent=None, radius=13, background=None):
    panel = QFrame(parent)
    panel.setObjectName("panel")
    panel.setStyleSheet(f"""
        QFrame#panel {{
            background-color: {background or COLORS['surface']};
            border: 1px solid {COLORS['border']};
            border-radius: {radius}px;
        }}
    """)
    return panel


def add_shadow(widget, color="#000000", blur=24, y=5, alpha=65):
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y)
    shadow.setColor(QColor(color))
    widget.setGraphicsEffect(shadow)


def make_button(text, background, hover, foreground="#FFFFFF", border=None,
                radius=12, font_size=14, bold=True):
    button = QPushButton(text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFont(
        QFont(FONT, font_size, QFont.Weight.Bold if bold else QFont.Weight.Medium)
    )
    button.setStyleSheet(f"""
        QPushButton {{
            background-color: {background};
            color: {foreground};
            border: 1px solid {border or background};
            border-radius: {radius}px;
            padding: 10px 14px;
        }}
        QPushButton:hover {{
            background-color: {hover};
            border-color: {hover};
        }}
        QPushButton:pressed {{
            background-color: {background};
        }}
        QPushButton:disabled {{
            background-color: #142034;
            color: #536786;
            border-color: #203047;
        }}
    """)
    return button


def section_title(icon, title, count=None):
    row = QHBoxLayout()
    row.setSpacing(10)
    icon_label = make_label(icon, 19, COLORS["muted"], True)
    row.addWidget(icon_label)
    text_label = make_label(title, 15, COLORS["text"], True)
    row.addWidget(text_label)
    row.addStretch()
    if count is not None:
        badge = make_label(str(count), 11, "#FFFFFF", True)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(28, 25)
        badge.setStyleSheet(f"""
            QLabel {{
                background: {COLORS['blue_dark']};
                color: white;
                border-radius: 12px;
                padding: 0;
            }}
        """)
        row.addWidget(badge)
    return row


# ============================================================
# ANIMATED ROUND CONTROL
# ============================================================

class RoundControl(QPushButton):
    """Большая круглая кнопка управления."""

    def __init__(self, symbol, title, subtitle, mode, parent=None):
        super().__init__(parent)
        self.symbol = symbol
        self.title = title
        self.subtitle = subtitle
        self.mode = mode
        self._hovered = False
        self._pulse = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumWidth(125)
        self.setMinimumHeight(185)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._animation = QPropertyAnimation(self, b"minimumWidth", self)
        self._animation.setDuration(160)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        if mode == "start":
            self.setToolTip("Запустить работу бота")
        elif mode == "pause":
            self.setToolTip("Приостановить работу")
        else:
            self.setToolTip("Остановить бота")

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        from PyQt6.QtCore import QRectF, QPointF
        from PyQt6.QtGui import QPolygonF

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        center_x = rect.width() / 2
        button_size = min(90, rect.width() - 18)
        button_top = 14
        button_rect = (center_x - button_size / 2, button_top, button_size, button_size)

        x, y, w, h = button_rect
        circle = QRectF(x, y, w, h)

        if self.mode == "start":
            glow = QColor(COLORS["green"])
            glow.setAlpha(24 if not self._hovered else 43)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(circle.adjusted(-17, -17, 17, 17))

        if self.mode == "start":
            gradient = QLinearGradient(circle.topLeft(), circle.bottomRight())
            gradient.setColorAt(0, QColor("#55E9BC"))
            gradient.setColorAt(1, QColor("#08A9B8"))
            border_color = "#5DF3C8"
        else:
            gradient = QLinearGradient(circle.topLeft(), circle.bottomRight())
            gradient.setColorAt(0, QColor("#22344F"))
            gradient.setColorAt(1, QColor("#15243B"))
            border_color = "#2B4163"

        if self._hovered and self.mode != "start":
            gradient.setColorAt(0, QColor("#2C4365"))
            gradient.setColorAt(1, QColor("#1C304C"))

        painter.setPen(QPen(QColor(border_color), 1))
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(circle)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))

        cx = circle.center().x()
        cy = circle.center().y()

        if self.mode == "start":
            polygon = QPolygonF([
                QPointF(cx - 13, cy - 21),
                QPointF(cx - 13, cy + 21),
                QPointF(cx + 23, cy),
            ])
            painter.drawPolygon(polygon)
        elif self.mode == "pause":
            painter.drawRoundedRect(QRectF(cx - 12, cy - 14, 8, 28), 3, 3)
            painter.drawRoundedRect(QRectF(cx + 4, cy - 14, 8, 28), 3, 3)
        else:
            painter.drawRoundedRect(QRectF(cx - 12, cy - 12, 24, 24), 3, 3)

        title_font = QFont(FONT, 15, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.setPen(QColor(COLORS["text"]))
        title_y = int(button_top + button_size + 26)
        painter.drawText(
            0, title_y, rect.width(), 24,
            Qt.AlignmentFlag.AlignHCenter, self.title,
        )

        painter.setFont(QFont(FONT, 10))
        painter.setPen(QColor(COLORS["muted"]))
        painter.drawText(
            2, title_y + 24, rect.width() - 4, 28,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            self.subtitle,
        )
        painter.end()


# ============================================================
# STATISTIC CARD
# ============================================================

class StatCard(QFrame):
    def __init__(self, icon, title, action, accent, soft, parent=None):
        super().__init__(parent)
        self.accent = accent
        self.setMinimumHeight(72)
        self.setObjectName("statCard")
        self.setStyleSheet(f"""
            QFrame#statCard {{
                background-color: {soft};
                border: 1px solid {accent}65;
                border-radius: 12px;
            }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(9, 8, 9, 8)
        row.setSpacing(8)

        icon_box = QLabel(icon)
        icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_box.setFixedSize(36, 36)
        icon_box.setFont(QFont(FONT, 16, QFont.Weight.Bold))
        icon_box.setStyleSheet(
            f"background-color:{accent}38; color:{accent}; "
            f"border-radius:18px; border:none;"
        )
        row.addWidget(icon_box)

        self.value = make_label("0", 18, COLORS["text"], True)
        row.addWidget(self.value, 0, Qt.AlignmentFlag.AlignVCenter)

        self.name = make_label(title, 9, COLORS["muted"])
        self.name.setWordWrap(True)
        self.name.setMinimumWidth(0)
        row.addWidget(self.name, 1, Qt.AlignmentFlag.AlignVCenter)

    def set_value(self, value):
        self.value.setText(str(value))


# ============================================================
# NOTIFICATION CARD (кликабельная)
# ============================================================

class NotificationCard(QFrame):

    def __init__(self, timestamp, ticket, action, message, href="",
                 compact=False, parent=None, on_click=None):
        super().__init__(parent)

        self.ticket = ticket
        self.href = href
        self.action = action
        self._on_click = on_click

        if on_click is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        palette = ACTION_COLORS.get(action, ACTION_COLORS["auto"])
        accent = palette["accent"]
        soft = palette["soft"]

        self.setObjectName("notificationCard")
        self.setMinimumHeight(104 if compact else 112)
        self.setStyleSheet(f"""
            QFrame#notificationCard {{
                background-color: #0D1A2D;
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
            QFrame#notificationCard:hover {{
                border: 1px solid {accent};
                background-color: #122241;
            }}
        """)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 10, 0)
        outer.setSpacing(0)

        stripe = QFrame()
        stripe.setFixedWidth(7)
        stripe.setStyleSheet(f"""
            background-color: {accent};
            border: none;
            border-top-left-radius: 11px;
            border-bottom-left-radius: 11px;
        """)
        outer.addWidget(stripe)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(content)
        layout.setContentsMargins(10, 12, 0, 12)
        layout.setSpacing(10)

        bot_icon = QLabel("♙")
        bot_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bot_icon.setFixedSize(47, 47)
        bot_icon.setFont(QFont(FONT, 23, QFont.Weight.Bold))
        bot_icon.setStyleSheet(f"""
            background-color: {accent}30;
            color: {accent};
            border: 1px solid {accent}70;
            border-radius: 23px;
        """)
        layout.addWidget(bot_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        body = QVBoxLayout()
        body.setSpacing(5)

        header = QHBoxLayout()
        header.setSpacing(5)
        header.addWidget(make_label("Support Bot", 11, COLORS["text"], True))
        header.addStretch()
        header.addWidget(make_label(timestamp, 10, COLORS["muted"]))
        body.addLayout(header)

        meta = QHBoxLayout()
        meta.setSpacing(8)

        badge = QLabel(palette["label"])
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFont(QFont(FONT, 8, QFont.Weight.Bold))
        badge.setStyleSheet(f"""
            background-color: {soft};
            color: {accent};
            border: 1px solid {accent};
            border-radius: 10px;
            padding: 3px 8px;
        """)
        meta.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)

        meta.addWidget(make_label(f"#{ticket}", 10, COLORS["muted"]))
        meta.addStretch()
        body.addLayout(meta)

        description = make_label(message, 10, "#D6E1F8")
        description.setWordWrap(True)
        description.setMaximumHeight(38)
        body.addWidget(description)

        layout.addLayout(body, 1)

        arrow = make_label("›", 25, COLORS["muted"], False)
        arrow.setFixedWidth(17)
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(arrow)

        outer.addWidget(content, 1)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._on_click:
            try:
                self._on_click(self.ticket, self.href)
            except Exception as e:
                print(f"[NotificationCard] on_click error: {e}")
        super().mousePressEvent(event)


# ============================================================
# LOG VIEW
# ============================================================

class LogView(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAcceptRichText(False)
        self.setFont(QFont("Consolas", 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background-color: #0A1525;
                color: #C4D5F3;
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
                padding: 10px;
                selection-background-color: #264D96;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 7px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: #2A4264;
                border-radius: 3px;
                min-height: 22px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

    def add_entry(self, text, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M")
        color = {
            "INFO": "#40D9D0",
            "WARN": "#FFAD36",
            "ERROR": "#FF405B",
            "STATS": "#8D9FFF",
        }.get(level, "#40D9D0")

        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        self.append(
            f'<span style="color:#8EA7D3">{timestamp}</span> '
            f'<span style="color:{color}">[{level}]</span> '
            f'<span style="color:#C4D5F3">{safe}</span>'
        )
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


# ============================================================
# MAIN WINDOW
# ============================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1120, 720)
        self.resize(1536, 960)
        self.agent = None
        self.agent_thread = None
        self.running = False
        self.paused = False
        self.notification_count = 0
        self.cards = []
        self.stats = {"total": 0, "auto": 0, "suggest": 0, "escalate": 0}

        notifier_module.init_manager()
        notifier_module.set_handlers(
            on_open=self._on_toast_open,
            on_send=self._on_toast_send,
            on_skip=self._on_toast_skip,
        )

        self.bridge = EventBridge()
        self.bridge.event.connect(self._handle_event)

        self._build_ui()
        self._update_controls()

        self._clock = QTimer(self)
        self._clock.timeout.connect(self._update_datetime)
        self._clock.start(1000)
        self._update_datetime()

    def _apply_styles(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: {COLORS['window']}; }}
            QWidget {{ color: {COLORS['text']}; font-family: '{FONT}'; }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 7px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: #2A4162; border-radius: 3px; min-height: 28px; }}
            QScrollBar::handle:vertical:hover {{ background: #45658F; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    # ------------------------------------------------------------------
    # Уведомления-тосты (колбэки)
    # ------------------------------------------------------------------
    def _on_toast_open(self, ticket: str, href: str = ""):
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        from notifier import _open_in_bot_chrome
        if href:
            _open_in_bot_chrome(href)
        self._highlight_notification_card(str(ticket))
        self._log(f"Открыта заявка {ticket}")

    def _on_toast_send(self, ticket: str, href: str = ""):
        if not self.running or self.paused or self.agent is None:
            self._log("Нельзя отправить: бот не запущен или на паузе")
            return
        current = getattr(self.agent, "_current_id", None)
        if str(current) != str(ticket):
            self._log(f"Устаревшее уведомление: {ticket}, текущая {current}")
            return
        self.agent.send_command("send")
        self._log(f"Отправка по {ticket}")

    def _on_toast_skip(self, ticket: str, href: str = ""):
        if not self.running or self.paused or self.agent is None:
            self._log("Нельзя пропустить: бот не запущен или на паузе")
            return
        current = getattr(self.agent, "_current_id", None)
        if str(current) != str(ticket):
            self._log(f"Устаревшее уведомление: {ticket}, текущая {current}")
            return
        self.agent.send_command("next")
        self._log(f"Пропуск заявки {ticket}")

    # ------------------------------------------------------------------
    # КЛИК по карточке уведомления в GUI
    # ------------------------------------------------------------------
    def _on_notification_click(self, ticket: str, href: str = ""):
        """Клик по карточке в правой панели = как 'Открыть' в тосте."""
        self._log(f"Клик по уведомлению {ticket}")
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        if href:
            from notifier import _open_in_bot_chrome
            _open_in_bot_chrome(href)
        self._highlight_notification_card(str(ticket))

    def _highlight_notification_card(self, ticket: str):
        for card in getattr(self, "cards", []):
            if str(getattr(card, "ticket", "")) == ticket:
                old = card.styleSheet()
                card.setStyleSheet(
                    old + " QFrame#notificationCard { border: 2px solid #4C8CFF; }"
                )
                QTimer.singleShot(2000, lambda c=card, s=old: c.setStyleSheet(s))
                self.latest_scroll.ensureWidgetVisible(card)
                return

    # ------------------------------------------------------------------
    def _build_ui(self):
        self._apply_styles()
        shell = QWidget()
        shell.setObjectName("shell")
        shell.setStyleSheet(
            "QWidget#shell { background:#0B1423; border:1px solid #263955; border-radius:16px; }"
        )
        self.setCentralWidget(shell)
        root = QHBoxLayout(shell)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(18)

        center = self._build_center()
        right = self._build_right_panel()
        root.addWidget(center, 3)
        root.addWidget(right, 2)

    def _build_center(self):
        center = QWidget()
        center.setMinimumWidth(570)
        layout = QVBoxLayout(center)
        layout.setContentsMargins(4, 4, 0, 4)
        layout.setSpacing(14)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        welcome = make_label("Добро пожаловать!", 27, "#F5F7FF", True)
        subtitle = make_label(
            "Бот поддержки работает и следит за заявками", 13, COLORS["muted"]
        )
        titles.addWidget(welcome)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.date_label = make_label("", 10, COLORS["muted"])
        self.time_label = make_label("", 10, COLORS["muted"])
        header.addWidget(self.date_label, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.time_label, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header)

        controls = make_panel(radius=15, background="#0E1B2E")
        controls.setMinimumHeight(238)
        controls_row = QHBoxLayout(controls)
        controls_row.setContentsMargins(28, 14, 28, 14)
        controls_row.setSpacing(20)
        controls_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_pause = RoundControl("Ⅱ", "Пауза", "Приостановить работу", "pause")
        self.btn_start = RoundControl("▶", "Старт", "Запустить работу бота", "start")
        self.btn_stop = RoundControl("■", "Стоп", "Остановить бота", "stop")
        for button, handler in (
            (self.btn_pause, self._on_pause),
            (self.btn_start, self._on_start),
            (self.btn_stop, self._on_stop),
        ):
            button.setMinimumSize(150, 190)
            button.setMaximumHeight(205)
            button.clicked.connect(handler)
            controls_row.addWidget(button, 1)
        layout.addWidget(controls)

        actions_panel = make_panel(radius=14, background="#0D192B")
        actions_layout = QHBoxLayout(actions_panel)
        actions_layout.setContentsMargins(16, 15, 16, 15)
        actions_layout.setSpacing(12)
        self.btn_send = make_button(
            "Отправить", "#102B28", "#1AA77D",
            foreground="#D8FFF2", border="#2AC99A", radius=12, font_size=14,
        )
        self.btn_send.setMinimumHeight(68)
        self.btn_send.setStyleSheet(
            self.btn_send.styleSheet()
            + " QPushButton:hover { color:#FFFFFF; background:#15966F; border-color:#36E0AD; }"
        )
        self.btn_send.clicked.connect(self._on_send_action)

        self.btn_next = make_button(
            "Дальше", "#101F37", "#285BC7",
            foreground="#DCE8FF", border="#397AFF", radius=12, font_size=14,
        )
        self.btn_next.setMinimumHeight(68)
        self.btn_next.setStyleSheet(
            self.btn_next.styleSheet()
            + " QPushButton:hover { color:#FFFFFF; background:#244FB1; border-color:#5D96FF; }"
        )
        self.btn_next.clicked.connect(self._on_next_action)

        actions_layout.addWidget(self.btn_send, 1)
        actions_layout.addWidget(self.btn_next, 1)
        layout.addWidget(actions_panel)

        stats_panel = make_panel(radius=14, background="#0D192B")
        stats_layout = QHBoxLayout(stats_panel)
        stats_layout.setContentsMargins(10, 10, 10, 10)
        stats_layout.setSpacing(8)
        self.stat_total = StatCard("▤", "Всего обработано", "total", "#428AFF", "#132644")
        self.stat_auto = StatCard("ϟ", "Auto", "auto", "#3ADBD0", "#102631")
        self.stat_suggest = StatCard("♧", "Suggest", "suggest", "#FFB13D", "#2A2526")
        self.stat_escalate = StatCard("▲", "Escalate", "escalate", "#FF4560", "#2B202E")
        for card in (self.stat_total, self.stat_auto, self.stat_suggest, self.stat_escalate):
            card.setMinimumWidth(0)
            card.setMinimumHeight(72)
            stats_layout.addWidget(card, 1)
        layout.addWidget(stats_panel)

        log_panel = make_panel(radius=14, background="#0B1728")
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(13, 12, 13, 12)
        log_layout.setSpacing(8)
        log_header = QHBoxLayout()
        log_header.addLayout(section_title("☷", "Лог"))
        log_header.addStretch()
        self.btn_clear_log = QPushButton("Очистить")
        self.btn_clear_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_log.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{COLORS['muted']}; "
            f"border:none; padding:4px 7px; }} QPushButton:hover {{ color:white; }}"
        )
        self.btn_clear_log.clicked.connect(lambda: self.log_box.clear())
        log_header.addWidget(self.btn_clear_log)
        log_layout.addLayout(log_header)
        self.log_box = LogView()
        self.log_box.setMinimumHeight(125)
        log_layout.addWidget(self.log_box, 1)
        layout.addWidget(log_panel, 1)
        return center

    def _build_right_panel(self):
        right = QWidget()
        right.setMinimumWidth(360)
        layout = QVBoxLayout(right)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(0)

        panel = make_panel(radius=14, background="#0B1728")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(13, 14, 13, 13)
        panel_layout.setSpacing(12)

        heading = QHBoxLayout()
        heading.addLayout(section_title("♧", "Уведомления"))
        heading.addStretch()
        self.latest_count_label = make_label("0", 11, "#FFFFFF", True)
        self.latest_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.latest_count_label.setFixedSize(30, 26)
        self.latest_count_label.setStyleSheet(
            "color:white; background:#213F91; border-radius:13px;"
        )
        heading.addWidget(self.latest_count_label)
        panel_layout.addLayout(heading)

        self.latest_scroll = QScrollArea()
        self.latest_scroll.setWidgetResizable(True)
        self.latest_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.latest_scroll.setMinimumHeight(400)
        self.latest_container = QWidget()
        self.latest_container.setStyleSheet("background:transparent;")
        self.latest_layout = QVBoxLayout(self.latest_container)
        self.latest_layout.setContentsMargins(0, 0, 0, 0)
        self.latest_layout.setSpacing(10)

        self.empty_notifications = QWidget()
        empty_layout = QVBoxLayout(self.empty_notifications)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(10)
        empty_icon = QLabel("♧")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon.setFixedSize(66, 66)
        empty_icon.setFont(QFont(FONT, 27))
        empty_icon.setStyleSheet(
            "color:#A1B3D6; background:#111F34; "
            "border:1px solid #334968; border-radius:33px;"
        )
        empty_title = make_label("Пока нет уведомлений", 13, COLORS["text"], True)
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_desc = make_label(
            "Новые заявки и решения бота появятся здесь", 10, COLORS["muted"]
        )
        empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_desc.setWordWrap(True)
        empty_layout.addWidget(empty_icon, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_desc)
        self.latest_layout.addWidget(self.empty_notifications)
        self.latest_layout.addStretch(1)
        self.latest_scroll.setWidget(self.latest_container)
        panel_layout.addWidget(self.latest_scroll, 1)
        layout.addWidget(panel, 1)
        return right

    def _update_datetime(self):
        now = datetime.now()
        self.date_label.setText("▦  " + now.strftime("%d.%m.%Y"))
        self.time_label.setText("◷  " + now.strftime("%H:%M"))

    def _on_start(self):
        if self.running:
            return
        self.running = True
        self.paused = False
        self.agent = agent_module.Agent(dry_run=True, event_queue=queue.Queue())
        self.agent.events = QueueWrapper(self.agent.events, self.bridge)
        self.agent_thread = threading.Thread(
            target=self.agent.run, daemon=True, name="SupportBotAgent"
        )
        self.agent_thread.start()
        self._update_controls()
        self._log("Бот запущен")

    def _on_pause(self):
        if not self.running or self.agent is None:
            return
        if self.paused:
            self.agent.resume()
            self.paused = False
            self._log("Работа бота возобновлена")
        else:
            self.agent.pause()
            self.paused = True
            self._log("Работа бота приостановлена")
        self._update_controls()

    def _on_stop(self):
        if not self.running:
            return
        if self.agent is not None:
            self.agent.stop()
        self.running = False
        self.paused = False
        self._update_controls()
        self._log("Запрошена остановка бота")

    def _on_send_action(self):
        if not self.running or self.paused or self.agent is None:
            return
        self.agent.send_command("send")
        self.btn_send.setEnabled(False)
        self.btn_next.setEnabled(False)
        self._log("Команда: отправить ответ")

    def _on_next_action(self):
        if not self.running or self.paused or self.agent is None:
            return
        self.agent.send_command("next")
        self.btn_send.setEnabled(False)
        self.btn_next.setEnabled(False)
        self._log("Команда: следующая заявка")

    def _update_controls(self):
        self.btn_start.setEnabled(not self.running)
        self.btn_pause.setEnabled(self.running)
        self.btn_stop.setEnabled(self.running)
        if self.running and not self.paused:
            self.btn_send.setEnabled(False)
            self.btn_next.setEnabled(False)
        if hasattr(self, "status_detail"):
            self.status_detail.setText(
                "Бот работает" if self.running and not self.paused
                else "Работа приостановлена" if self.paused
                else "Ожидание запуска"
            )

    def _handle_event(self, event):
        event_type = event.get("type")
        if event_type == "log":
            self._log(event.get("text", ""))
        elif event_type == "notification":
            self._add_notification(event)
        elif event_type == "stats":
            self.stats.update(
                {key: event.get(key, 0) for key in ("total", "auto", "suggest", "escalate")}
            )
            self._update_stats()
        elif event_type == "show_buttons":
            can_send = event.get("can_send", False)
            self.btn_send.setEnabled(can_send and self.running and not self.paused)
            self.btn_next.setEnabled(self.running and not self.paused)
        elif event_type == "clear_buttons":
            self.btn_send.setEnabled(False)
            self.btn_next.setEnabled(False)

    def _add_notification(self, event):
        timestamp = datetime.now().strftime("%H:%M")
        ticket = str(event.get("ticket", "—"))
        action = event.get("action", "auto")
        message = str(event.get("message", ""))
        href = event.get("href", "")

        self.notification_count += 1
        self.empty_notifications.hide()

        card = NotificationCard(
            timestamp, ticket, action, message,
            href=href, compact=False,
            on_click=self._on_notification_click,
        )
        card.setMinimumHeight(112)
        self.latest_layout.insertWidget(0, card)
        self.cards.insert(0, card)

        while len(self.cards) > 100:
            old = self.cards.pop()
            self.latest_layout.removeWidget(old)
            old.deleteLater()

        self.latest_count_label.setText(str(min(self.notification_count, 99)))
        self._log(f"Уведомление: {ticket} ({action})")

    def _update_stats(self):
        self.stat_total.set_value(self.stats["total"])
        self.stat_auto.set_value(self.stats["auto"])
        self.stat_suggest.set_value(self.stats["suggest"])
        self.stat_escalate.set_value(self.stats["escalate"])

    def _log(self, message):
        if not hasattr(self, "log_box"):
            return
        text = str(message)
        if "ОШИБКА" in text or "ERROR" in text:
            level = "ERROR"
        elif "WARN" in text or "не удалось" in text.lower():
            level = "WARN"
        elif "STATS" in text:
            level = "STATS"
        else:
            level = "INFO"
        self.log_box.add_entry(text, level)

    def closeEvent(self, event):
        if self.agent is not None and self.running:
            self.agent.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont(FONT, 10))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()