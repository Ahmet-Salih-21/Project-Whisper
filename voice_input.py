# voice_input.py
# Mikrofon kaydı ve konuşma tanıma modülü.
# - Konuşmanın başlangıcı ve bitişi ortam gürültüsüne ve konuşma seviyesine göre bulunur.
# - Konuşma bittikten 0.8 sn sonra kayıt kesilir.
# - Ses, Whisper'a verilmeden önce otomatik yükseltilir (kısık mikrofon için).
# - Süreler terminale yazılır: [Ses] ...

import time
from collections import deque

import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QThread, pyqtSignal

import whisper_loader


class VoiceInputWorker(QThread):
    """
    Sinyaller:
      transcription_ready(str) — metin hazırlandığında
      error_occurred(str)      — hata oluştuğunda
      model_loading()          — eski uyumluluk için duruyor, kullanılmıyor
    """
    transcription_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    model_loading = pyqtSignal()

    SAMPLE_RATE = 16000
    CHUNK_SEC = 0.1
    MIN_THRESHOLD = 0.004     # konuşma başlangıç eşiğinin en düşük değeri
    NOISE_MULT = 2.5          # başlangıç eşiği = gürültü x 2.5
    END_NOISE_MULT = 1.8      # bitiş eşiği en az gürültü x 1.8
    END_LEVEL_RATIO = 0.3     # bitiş eşiği en az konuşma seviyesinin %30'u
    END_MIN = 0.003           # bitiş eşiğinin mutlak alt sınırı
    SILENCE_SEC = 0.8         # konuşma bitince bu kadar bekle
    MAX_WAIT_SEC = 8.0        # konuşma başlamazsa vazgeç
    MAX_SPEECH_SEC = 10.0     # en uzun konuşma
    MIN_SEC = 0.3
    PRE_ROLL = 3              # konuşmadan önceki kaç parça korunsun

    def run(self):
        try:
            model = whisper_loader.get_model()
            if model is None:
                self.error_occurred.emit("Ses tanıma modeli yüklenemedi.")
                return

            t0 = time.time()
            audio = self._record()
            t1 = time.time()

            if audio is None or len(audio) < int(self.SAMPLE_RATE * self.MIN_SEC):
                self.error_occurred.emit("Ses algılanamadı, lütfen tekrar deneyin.")
                return

            text = self._transcribe(model, audio).strip()
            t2 = time.time()
            print(
                f"[Ses] ses={len(audio) / self.SAMPLE_RATE:.1f}sn "
                f"kayit={t1 - t0:.1f}sn cozme={t2 - t1:.1f}sn metin={text!r}",
                flush=True,
            )

            if text:
                self.transcription_ready.emit(text)
            else:
                self.error_occurred.emit("Konuşma anlaşılamadı, lütfen tekrar deneyin.")

        except RuntimeError as e:
            self.error_occurred.emit(str(e))
        except Exception as e:
            self.error_occurred.emit(f"Ses tanıma hatası: {e}")

    def _record(self):
        """Konuşma başlayıp bitene kadar kaydeder, baştaki sessizliği kırpar."""
        chunk_size = int(self.SAMPLE_RATE * self.CHUNK_SEC)
        silence_limit = int(self.SILENCE_SEC / self.CHUNK_SEC)
        max_wait = int(self.MAX_WAIT_SEC / self.CHUNK_SEC)
        max_speech = int(self.MAX_SPEECH_SEC / self.CHUNK_SEC)

        pre = deque(maxlen=self.PRE_ROLL)
        recent = deque(maxlen=30)
        frames = []
        speech_rms = []
        start_thr = self.MIN_THRESHOLD
        end_thr = self.END_MIN
        noise = 0.0
        level = 0.0
        speech_started = False
        silence_count = 0
        waited = 0
        speech_chunks = 0
        peak = 0.0

        try:
            with sd.InputStream(
                samplerate=self.SAMPLE_RATE, channels=1, dtype="float32"
            ) as stream:
                while True:
                    if self.isInterruptionRequested():
                        break

                    chunk, _ = stream.read(chunk_size)
                    rms = float(np.sqrt(np.mean(chunk ** 2)))
                    peak = max(peak, rms)

                    # 1) Konuşma başlamadan önce: gürültüyü ölç, başlangıcı bekle
                    if not speech_started:
                        recent.append(rms)
                        if len(recent) >= 3:
                            start_thr = max(
                                self.MIN_THRESHOLD, min(recent) * self.NOISE_MULT
                            )
                        pre.append(chunk.copy())
                        waited += 1
                        if rms > start_thr:
                            speech_started = True
                            frames.extend(pre)
                            noise = float(np.percentile(list(recent), 25))
                            speech_rms.append(rms)
                            silence_count = 0
                        elif waited >= max_wait:
                            break
                        continue

                    # 2) Konuşulurken: bitişi, gürültüye ve konuşma seviyesine göre bul
                    frames.append(chunk.copy())
                    speech_chunks += 1
                    if rms > start_thr:
                        speech_rms.append(rms)
                    level = float(np.percentile(speech_rms, 75)) if speech_rms else start_thr
                    end_thr = max(
                        noise * self.END_NOISE_MULT,
                        level * self.END_LEVEL_RATIO,
                        self.END_MIN,
                    )

                    if rms > end_thr:
                        silence_count = 0
                    else:
                        silence_count += 1
                        if silence_count >= silence_limit:
                            break
                    if speech_chunks >= max_speech:
                        break

        except sd.PortAudioError as e:
            raise RuntimeError(f"Mikrofona erişilemiyor: {e}")

        print(
            f"[Ses] baslangic_esik={start_thr:.4f} bitis_esik={end_thr:.4f} "
            f"gurultu={noise:.4f} seviye={level:.4f} "
            f"en_yuksek={peak:.4f} algilandi={speech_started}",
            flush=True,
        )
        return np.concatenate(frames, axis=0) if frames else None

    def _transcribe(self, model, audio: np.ndarray) -> str:
        """Sesi yükseltip doğrudan Whisper'a verir, Türkçe metne çevirir."""
        samples = audio.flatten().astype(np.float32)

        # Kısık mikrofon için: en yüksek nokta 0.8 olacak şekilde ölçekle (en fazla 40 kat)
        tepe = float(np.max(np.abs(samples)))
        if tepe > 0.001:
            samples = samples * min(0.8 / tepe, 40.0)
            samples = np.clip(samples, -1.0, 1.0)

        segments, _ = model.transcribe(
            samples,
            language="tr",
            beam_size=1,
            temperature=0.0,
            condition_on_previous_text=False,
            without_timestamps=True,
            initial_prompt="Türkçe konuşma. Asistanın adı Whisper.",
        )
        return " ".join(seg.text for seg in segments)