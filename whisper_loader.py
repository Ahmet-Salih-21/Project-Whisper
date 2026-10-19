# whisper_loader.py
# Whisper modelini program başlarken (pencere açılmadan önce) yükler.
# Arka plan thread'inde yüklemek çökmeye sebep olduğu için ayrı dosyada tutuldu.

import os

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from faster_whisper import WhisperModel

_model = None


def preload():
    """Modeli bir kere yükler. main.py'nin en başında çağrılır."""
    global _model
    if _model is None:
        print("Whisper modeli yukleniyor, birkac saniye surebilir...")
        _model = WhisperModel("small", device="cpu", compute_type="int8")
        print("Whisper hazir.")
    return _model


def get_model():
    return _model