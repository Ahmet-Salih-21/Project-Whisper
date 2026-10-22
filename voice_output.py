# voice_output.py
# Whisper'ın cevaplarını sesli okuyan modül.
# 1) Gemini ses modeli (doğal ses). Kısa cümleler ses_onbellek klasöründe saklanır.
# 2) Gemini kullanılamazsa (kota/hata) gTTS ile okunur.

import hashlib
import os
import tempfile
import time
import wave

import pygame
from dotenv import load_dotenv
from google import genai
from google.genai import types
from gtts import gTTS
from PyQt6.QtCore import QThread, pyqtSignal

load_dotenv()

# .env dosyasında GEMINI_VOICE=Kore gibi değiştirilebilir.
# Erkek: Charon, Puck, Orus, Fenrir | Kadın: Kore, Aoede
GEMINI_VOICE = os.getenv("GEMINI_VOICE", "Charon")

# Çalışan modeli biliyorsan .env'ye GEMINI_TTS_MODEL=... yaz, deneme yapılmaz.
_ozel_model = os.getenv("GEMINI_TTS_MODEL", "").strip()
TTS_MODELS = ([_ozel_model] if _ozel_model else []) + [
    "gemini-3.8-flash-lite-tts",
    "gemini-3.8-flash-tts",
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-preview-tts",
]

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ses_onbellek")
CACHE_MAX_KARAKTER = 120   # bundan kısa cümleler önbelleğe alınır

_client = None
_calisan_model = None
_olmayan_modeller = set()
_bekleme = {}   # model -> tekrar denenebileceği zaman (kota dolunca)


def init_audio():
    """pygame mixer'ı başlatır. Ana thread'den çağrılmalıdır."""
    try:
        pygame.mixer.init(frequency=24000)
    except Exception as e:
        print(f"[TTS] Ses sistemi başlatılamadı: {e}")


def stop_audio():
    """Çalan sesi anında durdurur."""
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
    except Exception:
        pass


def _gemini_pcm(text: str):
    """Gemini ses modelinden ham ses (PCM) alır. Olmazsa None döner."""
    global _client, _calisan_model

    anahtar = os.getenv("GEMINI_API_KEY")
    if not anahtar:
        return None
    if _client is None:
        _client = genai.Client(api_key=anahtar)

    simdi = time.time()
    if _calisan_model and _bekleme.get(_calisan_model, 0) <= simdi:
        adaylar = [_calisan_model]
    else:
        adaylar = [
            m for m in TTS_MODELS
            if m not in _olmayan_modeller and _bekleme.get(m, 0) <= simdi
        ]

    for model in adaylar:
        try:
            t0 = time.time()
            cevap = _client.models.generate_content(
                model=model,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=GEMINI_VOICE
                            )
                        )
                    ),
                ),
            )
            pcm = cevap.candidates[0].content.parts[0].inline_data.data
            _calisan_model = model
            print(
                f"[TTS] Gemini sesi: model={model} ses={GEMINI_VOICE} "
                f"sure={time.time() - t0:.1f} sn",
                flush=True,
            )
            return pcm
        except Exception as e:
            hata = str(e)
            kucuk = hata.lower()
            print(f"[TTS] Gemini ses hatası ({model}): {hata[:150]}", flush=True)
            if "429" in hata or "resource_exhausted" in kucuk:
                _bekleme[model] = time.time() + 600
                print(f"[TTS] {model} limiti doldu, 10 dakika denenmeyecek.", flush=True)
                if model == _calisan_model:
                    _calisan_model = None
                continue
            if any(k in kucuk for k in (
                "404", "not_found", "not found", "403", "permission",
                "not supported", "unsupported",
            )):
                _olmayan_modeller.add(model)
                if model == _calisan_model:
                    _calisan_model = None
                continue
            return None
    return None


def _wav_yaz(yol: str, pcm: bytes):
    with wave.open(yol, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm)


class TTSWorker(QThread):
    """
    Metni sese çevirip oynatan arka plan işçisi.
    Sıra: önbellek -> Gemini sesi -> gTTS yedeği. Bitince 'finished' sinyali.
    """
    finished = pyqtSignal()

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

            wav_yolu = None
            onbellek_yolu = None

            if len(self._text) <= CACHE_MAX_KARAKTER:
                os.makedirs(CACHE_DIR, exist_ok=True)
                anahtar = hashlib.md5(
                    f"{GEMINI_VOICE}|{self._text}".encode("utf-8")
                ).hexdigest()
                onbellek_yolu = os.path.join(CACHE_DIR, anahtar + ".wav")
                if os.path.exists(onbellek_yolu):
                    wav_yolu = onbellek_yolu

            if wav_yolu is None:
                pcm = _gemini_pcm(self._text)
                if pcm:
                    if onbellek_yolu:
                        hedef = onbellek_yolu
                    else:
                        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                            hedef = f.name
                        gecici.append(hedef)
                    _wav_yaz(hedef, pcm)
                    wav_yolu = hedef

            if wav_yolu is None:
                print("[TTS] Gemini sesi kullanılamadı, gTTS ile okunuyor.", flush=True)
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    mp3 = f.name
                gecici.append(mp3)
                gTTS(self._text, lang="tr").save(mp3)
                wav_yolu = mp3

            if self.isInterruptionRequested():
                return

            pygame.mixer.music.load(wav_yolu)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                self.msleep(50)
                if self.isInterruptionRequested():
                    pygame.mixer.music.stop()
                    break
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