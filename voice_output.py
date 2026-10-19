# voice_output.py
# Whisper'ın cevaplarını sesli okuyan modül (Hızlı ve Kararlı Mod).

import os
import tempfile
import pygame
from gtts import gTTS
from PyQt6.QtCore import QThread, pyqtSignal

# Pygame mixer'ı uygulama başladığında bir kez başlatıyoruz
try:
    pygame.mixer.init(frequency=24000, size=-16, channels=1, buffer=1024)
except Exception as e:
    print(f"[TTS] Ses sistemi başlatılamadı: {e}")


def init_audio():
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=24000, size=-16, channels=1, buffer=1024)
    except Exception:
        pass


def stop_audio():
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
    except Exception:
        pass


class TTSWorker(QThread):
    finished = pyqtSignal()  # main.py ile uyumlu parametresiz sinyal

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        for ch in ("*", "#", "_", "`"):
            text = text.replace(ch, "")
        self._text = text.strip()

    def run(self):
        gecici = []
        try:
            if not self._text:
                return

            if self.isInterruptionRequested():
                return

            # Hız ve kararlılık için doğrudan gTTS (Google Translate TTS) kullanılıyor
            mp3 = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
            gecici.append(mp3)
            gTTS(self._text, lang="tr").save(mp3)
            audio_yolu = mp3

            if self.isInterruptionRequested():
                return

            init_audio()
            pygame.mixer.music.load(audio_yolu)
            pygame.mixer.music.play()
            
            while pygame.mixer.music.get_busy():
                self.msleep(20)
                if self.isInterruptionRequested():
                    pygame.mixer.music.stop()
                    break

            pygame.mixer.music.stop()
            pygame.mixer.music.unload()

        except Exception as e:
            print(f"[TTS] Hata: {e}", flush=True)
        finally:
            for yol in gecici:
                try:
                    os.unlink(yol)
                except Exception:
                    pass
            self.finished.emit()