# main.py
# Uygulamanın ana dosyası.
# - Açılışta sistem kontrolü yapar ve sesli selam verir.
# - Sürekli dinler (düğmeyle açılıp kapanır), Whisper konuşurken mikrofon durur.
# - Metin/ses alır, Gemini'ye gönderir, cevabı sesli okur.

import whisper_loader
whisper_loader.preload()

import re
import sys

import pygame
import sounddevice as sd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLineEdit, QPushButton, QLabel,
    QFrame, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, pyqtSlot

from orb_widget import OrbWidget
from ai_engine import AIEngine
from voice_output import TTSWorker, init_audio, stop_audio
from voice_input import VoiceInputWorker


# ──────────────────────────────────────────────────────────────
# Renk ve stil sabitleri
# ──────────────────────────────────────────────────────────────
DARK_BG      = "#0a0e1a"
PANEL_BG     = "#111827"
CARD_BG      = "#1a2235"
BORDER_COLOR = "#1e3a5f"
ACCENT       = "#00c8e0"
USER_BUBBLE  = "#0d2137"
AI_BUBBLE    = "#0f1f14"
TEXT_PRIMARY = "#e0f0ff"
TEXT_MUTED   = "#5a7a9a"
GREEN        = "#00e87a"
RED          = "#ff4455"

MAIN_STYLESHEET = f"""
    QMainWindow, QWidget#central {{
        background-color: {DARK_BG};
    }}
    QWidget#history_panel {{
        background-color: {PANEL_BG};
        border: 1px solid {BORDER_COLOR};
        border-radius: 12px;
    }}
    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: {PANEL_BG};
        width: 6px;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER_COLOR};
        border-radius: 3px;
        min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QLineEdit#input_box {{
        background-color: {CARD_BG};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_COLOR};
        border-radius: 22px;
        padding: 10px 18px;
        font-size: 14px;
        font-family: 'Segoe UI';
        selection-background-color: {ACCENT};
    }}
    QLineEdit#input_box:focus {{
        border: 1.5px solid {ACCENT};
    }}
    QPushButton#send_btn {{
        background-color: {ACCENT};
        color: #000d1a;
        border: none;
        border-radius: 22px;
        padding: 10px 22px;
        font-size: 14px;
        font-weight: 700;
        font-family: 'Segoe UI';
        min-width: 90px;
    }}
    QPushButton#send_btn:hover {{ background-color: #00e5ff; }}
    QPushButton#send_btn:pressed {{ background-color: #0099b5; }}
    QPushButton#send_btn:disabled {{
        background-color: #1a3040;
        color: {TEXT_MUTED};
    }}
    QPushButton#listen_btn {{
        background-color: transparent;
        color: {GREEN};
        border: 1.5px solid {GREEN};
        border-radius: 22px;
        padding: 10px 16px;
        font-size: 13px;
        font-weight: 700;
        font-family: 'Segoe UI';
        min-width: 110px;
    }}
    QPushButton#listen_btn:hover {{
        background-color: rgba(0, 232, 122, 0.10);
    }}
    QPushButton#listen_btn:pressed {{
        background-color: rgba(0, 232, 122, 0.22);
    }}
    QPushButton#listen_btn:disabled {{
        color: #1a4a30;
        border-color: #1a4a30;
    }}
    QPushButton#listen_btn[recording="true"] {{
        color: {RED};
        border-color: {RED};
    }}
    QPushButton#sound_btn {{
        background-color: transparent;
        color: {ACCENT};
        border: 1.5px solid {ACCENT};
        border-radius: 22px;
        padding: 10px 13px;
        font-size: 16px;
        min-width: 46px;
        max-width: 46px;
    }}
    QPushButton#sound_btn:hover {{
        background-color: rgba(0, 200, 224, 0.10);
    }}
    QPushButton#sound_btn[muted="true"] {{
        color: {TEXT_MUTED};
        border-color: #1e3a5f;
    }}
    QLabel#title_label {{
        color: {ACCENT};
        font-size: 22px;
        font-weight: 700;
        font-family: 'Segoe UI';
        letter-spacing: 4px;
    }}
    QLabel#subtitle_label {{
        color: {TEXT_MUTED};
        font-size: 10px;
        font-family: 'Segoe UI';
        letter-spacing: 2px;
    }}
"""

# Ses tanıma bazen sessizlikte/gürültüde bu tür saçma cümleler uydurur
SAHTE_METIN_BASLANGICLARI = ("altyazı", "abone ol", "izlediğiniz için")


def metin_gurultu_mu(text: str) -> bool:
    """Çok kısa veya bilinen 'uydurma' ses tanıma çıktılarını eler."""
    t = re.sub(r"[^\w\s]", "", text.lower()).strip()
    if len(t) < 3:
        return True
    return t.startswith(SAHTE_METIN_BASLANGICLARI) and len(t.split()) <= 4


# ──────────────────────────────────────────────────────────────
# Açılış sistem kontrolü
# ──────────────────────────────────────────────────────────────
class StartupCheckWorker(QThread):
    """Açılışta internet/yapay zeka, mikrofon, hoparlör ve ses tanımayı kontrol eder."""
    done = pyqtSignal(bool, str)

    def __init__(self, ai, parent=None):
        super().__init__(parent)
        self._ai = ai

    def run(self):
        sorunlar = []

        # 1) Yapay zeka sunucusu (kota harcamayan basit bir sorgu)
        try:
            self._ai._client.models.get(model=self._ai._model_name)
        except Exception as e:
            hata = str(e)
            print(f"[Kontrol] Yapay zeka: {hata[:200]}", flush=True)
            if "429" not in hata and "RESOURCE_EXHAUSTED" not in hata:
                sorunlar.append("yapay zeka sunucusuna bağlanılamıyor")

        # 2) Mikrofon
        try:
            sd.query_devices(kind="input")
        except Exception as e:
            print(f"[Kontrol] Mikrofon: {e}", flush=True)
            sorunlar.append("mikrofon bulunamadı")

        # 3) Ses çıkışı
        if not pygame.mixer.get_init():
            sorunlar.append("ses çıkışı başlatılamadı")

        # 4) Ses tanıma modeli
        if whisper_loader.get_model() is None:
            sorunlar.append("ses tanıma modeli yüklenemedi")

        if sorunlar:
            self.done.emit(
                False,
                "Merhaba efendim. Sistemde sorun var: "
                + ", ".join(sorunlar)
                + ". Yine de size nasıl yardımcı olabilirim?",
            )
        else:
            self.done.emit(
                True,
                "Merhaba efendim. Sistem hazır, sorun yok. "
                "Size nasıl yardımcı olabilirim?",
            )


# ──────────────────────────────────────────────────────────────
# Mesaj Balonu
# ──────────────────────────────────────────────────────────────
class MessageBubble(QFrame):
    """Tek bir sohbet mesajını gösteren renkli balonlu widget."""

    def __init__(self, text: str, sender: str, parent=None):
        super().__init__(parent)
        is_user = (sender == "user")

        bg     = USER_BUBBLE if is_user else AI_BUBBLE
        border = "#0a3a5a"   if is_user else "#0a2a14"
        prefix_color = ACCENT   if is_user else GREEN
        prefix = "Sen"          if is_user else "Whisper"

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 12px;
                margin: 2px 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        sender_label = QLabel(prefix)
        sender_label.setStyleSheet(
            f"color:{prefix_color}; font-size:10px; font-weight:700; "
            f"letter-spacing:1px; font-family:'Segoe UI'; "
            f"background:transparent; border:none;"
        )
        sender_label.setAlignment(
            Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft
        )

        msg_label = QLabel(text)
        msg_label.setWordWrap(True)
        msg_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        msg_label.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:13px; font-family:'Segoe UI'; "
            f"background:transparent; border:none; line-height:1.5;"
        )
        msg_label.setAlignment(
            Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft
        )

        layout.addWidget(sender_label)
        layout.addWidget(msg_label)


# ──────────────────────────────────────────────────────────────
# Ana Pencere
# ──────────────────────────────────────────────────────────────
class WhisperWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("WHISPER — Kişisel Asistan")
        self.setMinimumSize(700, 820)
        self.resize(800, 900)
        self.setStyleSheet(MAIN_STYLESHEET)

        # Ses sistemi (pygame — ana thread'de başlatılmalı)
        init_audio()

        # Durum değişkenleri
        self._ai = AIEngine()
        self._ai_ready = False
        self._tts_enabled = True
        self._tts_worker = None
        self._voice_worker = None
        self._check_worker = None
        self._retired = []          # durdurulan ama henüz bitmemiş thread'ler
        self._auto_listen = True    # sürekli dinleme açık mı
        self._thinking = False      # Gemini cevap hazırlıyor mu
        self._speaking = False      # Whisper konuşuyor mu

        # ── Düzen ───────────────────────────────────────────
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(0)

        # Başlık
        header = QWidget()
        hlay = QVBoxLayout(header)
        hlay.setContentsMargins(0, 0, 0, 10)
        hlay.setSpacing(2)
        hlay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("WHISPER")
        title.setObjectName("title_label")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("KİŞİSEL YAPAY ZEKA ASISTANI")
        subtitle.setObjectName("subtitle_label")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hlay.addWidget(title)
        hlay.addWidget(subtitle)
        root.addWidget(header)

        # Orb
        self._orb = OrbWidget()
        self._orb.setFixedHeight(300)
        root.addWidget(self._orb, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addSpacing(8)

        # Konuşma geçmişi paneli
        history_panel = QWidget()
        history_panel.setObjectName("history_panel")
        hpanel_lay = QVBoxLayout(history_panel)
        hpanel_lay.setContentsMargins(4, 8, 4, 8)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._msg_container = QWidget()
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._msg_layout.setSpacing(6)
        self._msg_layout.setContentsMargins(4, 4, 4, 4)

        self._scroll.setWidget(self._msg_container)
        hpanel_lay.addWidget(self._scroll)
        root.addWidget(history_panel, stretch=1)
        root.addSpacing(12)

        # ── Giriş Satırı: [Dinle] [metin kutusu] [Gönder] [Ses] ──────
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._listen_btn = QPushButton()
        self._listen_btn.setObjectName("listen_btn")
        self._listen_btn.setToolTip("Sürekli dinlemeyi aç / kapat")
        self._listen_btn.clicked.connect(self._on_toggle_listen)
        self._set_listen_button(self._auto_listen)

        self._input = QLineEdit()
        self._input.setObjectName("input_box")
        self._input.setPlaceholderText("Whisper'a bir şey sor...")
        self._input.returnPressed.connect(self._on_send)

        self._send_btn = QPushButton("Gönder")
        self._send_btn.setObjectName("send_btn")
        self._send_btn.clicked.connect(self._on_send)

        self._sound_btn = QPushButton("🔊")
        self._sound_btn.setObjectName("sound_btn")
        self._sound_btn.setToolTip("Sesi Aç / Kapat")
        self._sound_btn.clicked.connect(self._on_toggle_sound)

        input_row.addWidget(self._listen_btn)
        input_row.addWidget(self._input, stretch=1)
        input_row.addWidget(self._send_btn)
        input_row.addWidget(self._sound_btn)
        root.addLayout(input_row)

        # AI motorunu başlat
        self._initialize_ai()

    # ── Başlangıç ────────────────────────────────────────────
    def _initialize_ai(self):
        """AI motorunu başlatır, sonra sistem kontrolünü ve selamı çalıştırır."""
        try:
            self._ai.initialize()
            self._ai_ready = True
            self._orb.set_state("waiting")
            self._add_system_message("Sistem kontrol ediliyor...")

            self._check_worker = StartupCheckWorker(self._ai)
            self._check_worker.done.connect(self._on_startup_done)
            self._check_worker.start()
        except ValueError as e:
            self._ai_ready = False
            self._auto_listen = False
            self._add_system_message(
                f"⚠️  {e}\n\nLütfen .env dosyasına GEMINI_API_KEY ekleyin "
                "ve uygulamayı yeniden başlatın."
            )
            self._set_ui_busy(True)
            self._listen_btn.setEnabled(False)
            self._orb.set_state("waiting")

    @pyqtSlot(bool, str)
    def _on_startup_done(self, ok: bool, message: str):
        """Sistem kontrolü bitince selamı yazar ve sesli söyler."""
        self._add_message(message, "ai")
        if self._tts_enabled:
            self._speak(message)
        else:
            self._maybe_listen()

    # ── Metin Gönderme ───────────────────────────────────────
    @pyqtSlot()
    def _on_send(self):
        if not self._ai_ready:
            return
        text = self._input.text().strip()
        if not text:
            return

        self._stop_listening()
        self._add_message(text, "user")
        self._input.clear()
        self._thinking = True
        self._set_ui_busy(True)
        self._orb.set_state("thinking")

        self._ai.send_message(
            text,
            on_response=self._on_ai_response,
            on_error=self._on_ai_error,
        )

    @pyqtSlot(str)
    def _on_ai_response(self, response_text: str):
        """Gemini'den cevap gelince çalışır."""
        self._thinking = False
        self._add_message(response_text, "ai")
        self._set_ui_busy(False)

        if self._tts_enabled:
            self._speak(response_text)
        else:
            self._orb.set_state("waiting")
            self._maybe_listen()

    @pyqtSlot(str)
    def _on_ai_error(self, error_text: str):
        self._thinking = False
        self._add_system_message(f"⚠️ {error_text}")
        self._set_ui_busy(False)
        self._orb.set_state("waiting")
        QTimer.singleShot(300, self._maybe_listen)

    # ── Sesli Çıktı (TTS) ────────────────────────────────────
    def _speak(self, text: str):
        """Metni sesli okur. Konuşurken mikrofon kapalıdır."""
        self._stop_listening()

        if self._tts_worker and self._tts_worker.isRunning():
            self._tts_worker.requestInterruption()
            stop_audio()
            self._keep_alive(self._tts_worker)

        self._speaking = True
        self._orb.set_state("speaking")

        worker = TTSWorker(text)
        worker.finished.connect(lambda w=worker: self._on_tts_finished(w))
        self._tts_worker = worker
        worker.start()

    def _on_tts_finished(self, worker):
        """Konuşma bitince (eski bir worker'ın sinyalini yok say)."""
        if worker is not self._tts_worker:
            return
        self._speaking = False
        if not self._thinking:
            self._orb.set_state("waiting")
            # Kendi sesinin yankısını duymamak için kısa bekle
            QTimer.singleShot(500, self._maybe_listen)

    @pyqtSlot()
    def _on_toggle_sound(self):
        """Sesi açar / kapatır."""
        self._tts_enabled = not self._tts_enabled

        if self._tts_enabled:
            self._sound_btn.setText("🔊")
            self._sound_btn.setProperty("muted", False)
        else:
            self._sound_btn.setText("🔇")
            self._sound_btn.setProperty("muted", True)
            if self._tts_worker and self._tts_worker.isRunning():
                self._tts_worker.requestInterruption()
                stop_audio()

        self._sound_btn.style().unpolish(self._sound_btn)
        self._sound_btn.style().polish(self._sound_btn)

    # ── Sürekli Dinleme (STT) ────────────────────────────────
    def _set_listen_button(self, on: bool):
        """Dinleme düğmesinin görünümünü günceller."""
        self._listen_btn.setText("🔴  Dinliyor" if on else "🎤  Dinle")
        self._listen_btn.setProperty("recording", on)
        self._listen_btn.style().unpolish(self._listen_btn)
        self._listen_btn.style().polish(self._listen_btn)

    @pyqtSlot()
    def _on_toggle_listen(self):
        """Sürekli dinlemeyi açar veya kapatır."""
        if not self._ai_ready:
            return
        self._auto_listen = not self._auto_listen
        self._set_listen_button(self._auto_listen)

        if self._auto_listen:
            self._maybe_listen()
        else:
            self._stop_listening()
            if not self._thinking and not self._speaking:
                self._orb.set_state("waiting")

    def _maybe_listen(self):
        """Uygunsa (kimse konuşmuyor, cevap beklenmiyor) mikrofonu dinlemeye alır."""
        if not (self._auto_listen and self._ai_ready):
            return
        if self._thinking or self._speaking:
            return
        if self._voice_worker is not None:
            return

        worker = VoiceInputWorker()
        worker.transcription_ready.connect(self._on_transcription_ready)
        worker.error_occurred.connect(self._on_voice_error)
        self._voice_worker = worker
        self._orb.set_state("listening")
        worker.start()

    def _keep_alive(self, worker):
        """Çalışan bir thread'in silinip programı çökertmesini önler."""
        self._retired = [w for w in self._retired if w.isRunning()]
        self._retired.append(worker)

    def _release_worker(self):
        """Mevcut dinleme işçisini serbest bırakır (yenisi başlayabilsin)."""
        worker = self._voice_worker
        self._voice_worker = None
        if worker is not None:
            self._keep_alive(worker)
        return worker

    def _stop_listening(self):
        """Dinlemeyi durdurur."""
        worker = self._release_worker()
        if worker is not None and worker.isRunning():
            worker.requestInterruption()

    @pyqtSlot(str)
    def _on_transcription_ready(self, text: str):
        """Whisper metni hazırladığında, yazılıp gönderilmiş gibi işler."""
        if self.sender() is not self._voice_worker:
            return   # durdurulmuş eski bir dinlemenin sonucu
        self._release_worker()

        if self._thinking or self._speaking:
            return
        if metin_gurultu_mu(text):
            QTimer.singleShot(100, self._maybe_listen)
            return

        self._input.setText(text)
        self._on_send()

    @pyqtSlot(str)
    def _on_voice_error(self, error: str):
        if self.sender() is not self._voice_worker:
            return
        self._release_worker()

        if self._thinking or self._speaking:
            return

        # Gerçek bir sorun varsa dinlemeyi kapat ve haber ver
        if error.startswith(("Mikrofona", "Ses tanıma")):
            self._add_system_message(f"⚠️ {error}")
            self._auto_listen = False
            self._set_listen_button(False)
            self._orb.set_state("waiting")
            return

        # "Ses algılanamadı / anlaşılamadı": sessizce tekrar dinle
        QTimer.singleShot(200, self._maybe_listen)

    # ── Yardımcı Fonksiyonlar ────────────────────────────────
    def _add_message(self, text: str, sender: str):
        bubble = MessageBubble(text, sender)
        self._msg_layout.addWidget(bubble)
        self._scroll_to_bottom()

    def _add_system_message(self, text: str):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:12px; font-family:'Segoe UI'; "
            f"padding:8px; background:transparent;"
        )
        self._msg_layout.addWidget(label)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def _set_ui_busy(self, busy: bool):
        """AI çalışırken giriş alanını ve gönder butonunu devre dışı bırakır."""
        self._input.setEnabled(not busy)
        self._send_btn.setEnabled(not busy)
        self._send_btn.setText("Düşünüyor..." if busy else "Gönder")

    def closeEvent(self, event):
        """Pencere kapanırken ses ve dinleme thread'lerini düzgünce durdurur."""
        self._auto_listen = False
        self._stop_listening()
        stop_audio()
        islemciler = list(self._retired)
        if self._tts_worker:
            islemciler.append(self._tts_worker)
        for w in islemciler:
            try:
                w.requestInterruption()
                w.wait(2500)
            except Exception:
                pass
        event.accept()


# ──────────────────────────────────────────────────────────────
# Başlangıç
# ──────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = WhisperWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()