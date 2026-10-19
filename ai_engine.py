# ai_engine.py
# Google Gemini ile maksimum hız motoru (Tek seferlik istek modu).

import os
import time
from dotenv import load_dotenv
from PyQt6.QtCore import QThread, pyqtSignal
from google import genai
from google.genai import types

load_dotenv()

ASSISTANT_NAME = "Whisper"

SYSTEM_INSTRUCTION = (
    f"Sen {ASSISTANT_NAME}'sın, kullanıcının kişisel yapay zeka asistanısın. "
    "Kullanıcıya 'efendim' diye hitap et. Türkçe konuş. "
    "Cevaplarını kısa, net ve kibar tut; en fazla 2-3 cümle. "
    "Asla uzun web adresi, yıldız veya emoji kullanma."
)


class GeminiWorker(QThread):
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, engine, message: str, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._message = message

    def run(self):
        try:
            self.response_ready.emit(self._engine.ask(self._message))
        except Exception as e:
            self.error_occurred.emit(f"Bağlantı hatası: {str(e)}")


class AIEngine:
    def __init__(self):
        self._client = None
        self._worker = None
        self._model_name = "gemini-3.5-flash-lite"

    def initialize(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY bulunamadı!")
        self._client = genai.Client(api_key=api_key)

    def ask(self, message: str) -> str:
        start = time.time()
        try:
            # Sohbet geçmişi tutmadan doğrudan tek istek atarak hızı zirveye çıkarıyoruz
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=message,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.5,
                )
            )
            text = response.text

            print(
                f"[Gemini] model={self._model_name} "
                f"sure={time.time() - start:.1f} sn",
                flush=True,
            )
            return text or "Yapıldı efendim."
        except Exception as e:
            raise e

    def send_message(self, message: str, on_response, on_error):
        if self._client is None:
            on_error("AI motoru başlatılmadı.")
            return

        if self._worker and self._worker.isRunning():
            self._worker.quit()

        self._worker = GeminiWorker(self, message)
        self._worker.response_ready.connect(on_response)
        self._worker.error_occurred.connect(on_error)
        self._worker.start()