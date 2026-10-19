# ses_testi2.py
# Gemini ses modellerini sırayla dener, hangisi çalışıyorsa çalar.

import os
import tempfile
import time
import traceback
import wave

import pygame
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

METIN = "Merhaba efendim. Sistem hazır, sorun yok. Size nasıl yardımcı olabilirim?"
SES = "Charon"   # erkek sesler: Charon, Puck, Orus, Fenrir  |  kadın: Kore, Aoede

MODELLER = [
    "gemini-3.8-flash-lite-tts",
    "gemini-3.8-flash-tts",
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-preview-tts",
]


def cal(pcm: bytes):
    yol = os.path.join(tempfile.gettempdir(), "gemini_tts_test.wav")
    with wave.open(yol, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm)
    pygame.mixer.init(frequency=24000)
    pygame.mixer.music.load(yol)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.wait(100)
    pygame.mixer.music.unload()
    pygame.mixer.quit()


for model in MODELLER:
    print(f"\n--- {model} ({SES}) ---")
    try:
        t = time.time()
        cevap = client.models.generate_content(
            model=model,
            contents=METIN,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=SES)
                    )
                ),
            ),
        )
        pcm = cevap.candidates[0].content.parts[0].inline_data.data
        print(f"CALISTI, uretim suresi: {time.time() - t:.1f} sn. Caliyorum...")
        cal(pcm)
    except Exception as e:
        print("HATA:", str(e)[:300])