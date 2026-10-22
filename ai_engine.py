# ai_engine.py
# Google Gemini ile iletişim ve araç kullanımı (tools.py).
# API çağrısı ayrı bir thread'de çalışır, arayüz donmaz.
# Hız için modelin "düşünme" ayarı düşürülür ve her cevabın süresi terminale yazılır.

import os
import time
from dotenv import load_dotenv
from PyQt6.QtCore import QThread, pyqtSignal
from google import genai
from google.genai import types

import tools

load_dotenv()

ASSISTANT_NAME = "Whisper"

SYSTEM_INSTRUCTION = (
    f"Sen {ASSISTANT_NAME}'sın, kullanıcının kişisel yapay zeka asistanısın. "
    "Kullanıcıya 'efendim' diye hitap et. Türkçe konuş. "
    "Cevaplarını kısa, net ve kibar tut; en fazla 2-3 cümle. "
    "Cevapların sesli okunacak, bu yüzden madde işareti, yıldız, emoji ve uzun web adresi kullanma. "
    "Güncel bilgi gerektiren her şey için (haber, hava durumu, spor, fiyat, güncel olaylar) "
    "internette_ara aracını kullan. "
    "Kullanıcı bir siteyi açmak isterse web_sitesi_ac, YouTube'da video veya müzik isterse youtube_ara, "
    "sayfayı kendisi görmek istediği aramalar için google_ara, uygulama için uygulama_ac, "
    "ses veya müzik kontrolü için medya_kontrol, saat ve tarih için saat_tarih_soyle araçlarını kullan. "
    "Bir işlemi yaptıktan sonra tek kısa cümleyle ne yaptığını söyle. "
    "Yapamadığın bir şey istenirse bunu açıkça söyle, yapmış gibi davranma."
)

# Düşünme ayarları sırayla denenir; biri hata verirse sıradakine geçilir.
THINKING_OPTIONS = [
    ("thinking_level=minimal", lambda: types.ThinkingConfig(thinking_level="minimal")),
    ("thinking_level=low", lambda: types.ThinkingConfig(thinking_level="low")),
    ("thinking_budget=0", lambda: types.ThinkingConfig(thinking_budget=0)),
    ("varsayilan (yavas)", lambda: None),
]


class GeminiWorker(QThread):
    """Gemini çağrısını arka planda çalıştırır."""
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
    """Gemini ile sohbet oturumunu yönetir. main.py aynı şekilde kullanır."""

    def __init__(self):
        self._client = None
        self._chat = None
        self._worker = None
        self._model_name = None
        self._opt = 0

    def initialize(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY bulunamadı! "
                "Lütfen .env dosyasına API anahtarınızı ekleyin."
            )
        self._model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self._client = genai.Client(api_key=api_key)
        tools.tools_baslat(self._client, self._model_name)

    def _new_chat(self):
        _, make = THINKING_OPTIONS[self._opt]
        thinking = make()
        if thinking is None:
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION, tools=tools.TOOLS
            )
        else:
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=tools.TOOLS,
                thinking_config=thinking,
            )
        self._chat = self._client.chats.create(model=self._model_name, config=config)

    def ask(self, message: str) -> str:
        """Mesajı gönderir, cevabı döndürür (thread içinde çağrılır)."""
        start = time.time()
        while True:
            try:
                if self._chat is None:
                    self._new_chat()
                text = self._chat.send_message(message).text
                label = THINKING_OPTIONS[self._opt][0]
                print(
                    f"[Gemini] model={self._model_name} ayar={label} "
                    f"sure={time.time() - start:.1f} sn",
                    flush=True,
                )
                return text or "Yapıldı efendim."
            except Exception as e:
                err = str(e).lower()
                son_secenek = self._opt >= len(THINKING_OPTIONS) - 1
                if not son_secenek and ("thinking" in err or "validation" in err):
                    self._opt += 1
                    self._chat = None
                    continue
                raise

    def send_message(self, message: str, on_response, on_error):
        if self._client is None:
            on_error("AI motoru henüz başlatılmadı.")
            return

        if self._worker and self._worker.isRunning():
            self._worker.quit()

        self._worker = GeminiWorker(self, message)
        self._worker.response_ready.connect(on_response)
        self._worker.error_occurred.connect(on_error)
        self._worker.start()