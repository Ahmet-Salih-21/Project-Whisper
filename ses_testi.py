import asyncio, os, tempfile, traceback
import pygame

METIN = "Merhaba efendim, ben Whisper. Size nasıl yardımcı olabilirim?"
klasor = tempfile.gettempdir()


def cal(yol):
    if not pygame.mixer.get_init():
        pygame.mixer.init(frequency=24000)
    pygame.mixer.music.load(yol)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.wait(100)
    pygame.mixer.music.unload()


def edge_testi():
    import edge_tts
    yol = os.path.join(klasor, "test_edge.mp3")

    async def m():
        await edge_tts.Communicate(METIN, "tr-TR-AhmetNeural").save(yol)

    asyncio.run(m())
    print("[edge-tts] MP3 hazir:", os.path.getsize(yol), "bayt")
    cal(yol)


def gtts_testi():
    from gtts import gTTS
    yol = os.path.join(klasor, "test_gtts.mp3")
    gTTS(METIN, lang="tr").save(yol)
    print("[gTTS] MP3 hazir:", os.path.getsize(yol), "bayt")
    cal(yol)


for ad, fonk in [("edge-tts", edge_testi), ("gTTS", gtts_testi)]:
    print("\n--- Test:", ad, "---")
    try:
        fonk()
        print(ad, "bitti. Ses duydun mu?")
    except Exception:
        traceback.print_exc()
        print(ad, "HATA VERDI")