# orb_widget.py
# Bu dosya, Whisper'ın görsel "beyni" olan animasyonlu orb widget'ını içerir.
# JARVIS tarzı dönen HUD çemberleri, matris halkaları ve merkezinde WHISPER yazısı barındırır.

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QRadialGradient, QConicalGradient, QBrush, QFont
import math


# Her durum için cyan / mavi HUD renk ve animasyon ayarları
STATE_CONFIGS = {
    "waiting": {
        "core_color":  QColor(0, 200, 230),     # Cyan
        "ring_color":  QColor(0, 160, 200, 180),
        "glow_color":  QColor(0, 180, 220, 70),
        "pulse_speed": 0.015,
        "ring_speed":  0.6,
        "ring_count":  3,
        "label":       "SİSTEM HAZIR",
    },
    "listening": {
        "core_color":  QColor(0, 255, 170),     # Yeşilimsi cyan
        "ring_color":  QColor(0, 220, 150, 200),
        "glow_color":  QColor(0, 240, 160, 90),
        "pulse_speed": 0.04,
        "ring_speed":  1.8,
        "ring_count":  4,
        "label":       "DİNLENİYOR",
    },
    "thinking": {
        "core_color":  QColor(0, 190, 255),     # Parlak mavi
        "ring_color":  QColor(0, 140, 240, 200),
        "glow_color":  QColor(0, 160, 255, 90),
        "pulse_speed": 0.05,
        "ring_speed":  3.0,     # Hızlı dönen HUD halkaları
        "ring_count":  5,
        "label":       "İŞLENİYOR",
    },
    "speaking": {
        "core_color":  QColor(255, 170, 0),     # Altın / Turuncu (Konuşma anı)
        "ring_color":  QColor(230, 140, 0, 200),
        "glow_color":  QColor(255, 150, 0, 90),
        "pulse_speed": 0.06,
        "ring_speed":  2.2,
        "ring_count":  4,
        "label":       "KONUŞUYOR",
    },
}


class OrbWidget(QWidget):
    """JARVIS HUD tarzı dönen halkalı ve merkezinde WHISPER yazan widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._state = "waiting"
        self._pulse_angle = 0.0
        self._ring_angle = 0.0
        self._pulse_scale = 1.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_animation)
        self._timer.start(16)

    def set_state(self, state: str):
        if state not in STATE_CONFIGS:
            return
        self._state = state

    def get_state(self) -> str:
        return self._state

    def _update_animation(self):
        cfg = STATE_CONFIGS[self._state]
        self._pulse_angle += cfg["pulse_speed"]
        self._pulse_scale = 1.0 + 0.08 * math.sin(self._pulse_angle)
        self._ring_angle = (self._ring_angle + cfg["ring_speed"]) % 360.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cfg = STATE_CONFIGS[self._state]

        cx = self.width() / 2
        cy = self.height() / 2
        base_r = min(self.width(), self.height()) * 0.35

        # ── 1. Dış Parıltı (Glow) ──────────────────────────────────────────
        glow_r = base_r * 1.7
        glow_grad = QRadialGradient(QPointF(cx, cy), glow_r)
        glow_color = cfg["glow_color"]
        glow_grad.setColorAt(0.0, glow_color)
        glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(glow_grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # ── 2. Dönen Fütüristik HUD Halkaları ─────────────────────────────
        ring_count = cfg["ring_count"]
        ring_color = cfg["ring_color"]

        for i in range(ring_count):
            # Her halka farklı yönde ve hızda döner (Jarvis efekti)
            direction = 1 if i % 2 == 0 else -1
            offset_angle = self._ring_angle * direction + i * (360.0 / ring_count)
            ring_r = base_r * (1.1 + i * 0.18)

            conic = QConicalGradient(QPointF(cx, cy), offset_angle)
            conic.setColorAt(0.0, ring_color)
            conic.setColorAt(0.5, QColor(ring_color.red(), ring_color.green(), ring_color.blue(), 20))
            conic.setColorAt(1.0, ring_color)

            painter.setBrush(Qt.BrushStyle.NoBrush)
            pen = QPen(QBrush(conic), 1.5 + (i * 0.2))
            # Kesik çizgili (dashed) HUD halkası efekti
            if i == 1:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

        # ── 3. Merkez Çekirdek (Dönen / Nefes Alan Küre) ───────────────────
        core_r = base_r * 0.85 * self._pulse_scale
        core_color = cfg["core_color"]

        core_grad = QRadialGradient(
            QPointF(cx - core_r * 0.2, cy - core_r * 0.2),
            core_r * 1.2
        )
        bright = core_color.lighter(150)
        core_grad.setColorAt(0.0, bright)
        core_grad.setColorAt(0.5, core_color)
        core_grad.setColorAt(1.0, QColor(5, 15, 30, 230))

        painter.setBrush(QBrush(core_grad))
        painter.setPen(QPen(QColor(0, 229, 255, 120), 1.5))
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # ── 4. Çekirdek Üzerinde "WHISPER" Yazısı ───────────────────────────
        font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.0)
        painter.setFont(font)
        painter.setPen(QColor(224, 248, 255, 240))
        text_rect = QRectF(cx - core_r, cy - 15, core_r * 2, 30)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignCenter, "WHISPER")

        # ── 5. Alt Durum Etiketi ──────────────────────────────────────────
        label = cfg["label"]
        label_color = QColor(core_color)
        label_color.setAlpha(220)

        lbl_font = QFont("Segoe UI", 9)
        lbl_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        painter.setFont(lbl_font)
        painter.setPen(label_color)
        label_rect = QRectF(0, cy + base_r * 1.35, self.width(), 25)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignHCenter, label)

        painter.end()