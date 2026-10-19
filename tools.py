# tools.py
# Whisper'ın bilgisayarda yapabildiği işlemler ("araçlar").
# Güvenlik için sadece bu listedeki hazır işlemler yapılabilir;
# yapay zekanın istediği rastgele komutu çalıştırmak mümkün değildir.

import ctypes
import datetime
import subprocess
import urllib.parse
import webbrowser

from google.genai import types

_client = None
_model = None


def tools_baslat(client, model_adi):
    """ai_engine.py başlarken çağırır; internette_ara için gerekli."""
    global _client, _model
    _client = client
    _model = model_adi


def web_sitesi_ac(adres: str) -> str:
    """Bir web sitesini varsayılan tarayıcıda açar.
    adres örnekleri: 'youtube.com', 'bbc.com/turkce', 'hurriyet.com.tr'."""
    adres = adres.strip()
    if not adres or " " in adres:
        return "Geçersiz adres."
    if "://" in adres and not adres.startswith(("http://", "https://")):
        return "Sadece web adresleri açılabilir."
    if not adres.startswith(("http://", "https://")):
        adres = "https://" + adres
    webbrowser.open(adres)
    return f"{adres} açıldı."


def google_ara(sorgu: str) -> str:
    """Google'da arama yapar ve sonuç sayfasını tarayıcıda açar.
    Kullanıcı sayfayı kendisi görmek istediğinde kullanılır."""
    url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(sorgu)
    webbrowser.open(url)
    return f"Google'da '{sorgu}' araması açıldı."


def youtube_ara(sorgu: str) -> str:
    """YouTube'da arama yapar ve sonuç sayfasını tarayıcıda açar.
    Video, şarkı, klip, müzik açmak istendiğinde kullanılır."""
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(sorgu)
    webbrowser.open(url)
    return f"YouTube'da '{sorgu}' araması açıldı."


UYGULAMALAR = {
    "not defteri": "notepad",
    "hesap makinesi": "calc",
    "paint": "mspaint",
    "dosya gezgini": "explorer",
    "görev yöneticisi": "taskmgr",
    "ayarlar": "ms-settings:",
    "chrome": "chrome",
    "whatsapp": "whatsapp:",
}


def uygulama_ac(uygulama_adi: str) -> str:
    """Bilgisayardaki bir uygulamayı açar.
    Desteklenenler: not defteri, hesap makinesi, paint, dosya gezgini,
    görev yöneticisi, ayarlar, chrome, whatsapp."""
    ad = uygulama_adi.strip().lower()
    hedef = UYGULAMALAR.get(ad)
    if hedef is None:
        return "Bu uygulamayı açamıyorum. Desteklenenler: " + ", ".join(UYGULAMALAR)
    subprocess.Popen(f'start "" "{hedef}"', shell=True)
    return f"{uygulama_adi} açıldı."


MEDYA_TUSLARI = {
    "sesi_ac": 0xAF,
    "sesi_kis": 0xAE,
    "sessiz": 0xAD,
    "oynat_duraklat": 0xB3,
    "sonraki": 0xB0,
    "onceki": 0xB1,
}


def medya_kontrol(komut: str, kez: int = 1) -> str:
    """Ses ve medya tuşlarına basar.
    komut değerleri: sesi_ac, sesi_kis, sessiz, oynat_duraklat, sonraki, onceki.
    kez: kaç kez basılacağı. Ses için her basış yaklaşık %2 değiştirir,
    'biraz' için 5, 'çok' için 15 kullan."""
    vk = MEDYA_TUSLARI.get(komut)
    if vk is None:
        return "Geçersiz komut. Geçerliler: " + ", ".join(MEDYA_TUSLARI)
    for _ in range(max(1, min(int(kez), 50))):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
    return f"{komut} uygulandı."


GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def saat_tarih_soyle() -> str:
    """Şu anki saat, tarih ve günü döndürür."""
    s = datetime.datetime.now()
    return f"{s.strftime('%d.%m.%Y')} {GUNLER[s.weekday()]}, saat {s.strftime('%H:%M')}"


def internette_ara(sorgu: str) -> str:
    """İnternette güncel bilgi arar ve özetini döndürür.
    Hava durumu, spor sonuçları, fiyatlar, güncel olaylar ve
    bilmediğin her şey için kullan."""
    if _client is None:
        return "İnternet araması hazır değil."
    try:
        cevap = _client.models.generate_content(
            model=_model,
            contents=(
                f"{sorgu}\n\nGüncel bilgiyi internetten bul. "
                "Türkçe, en fazla 4 kısa cümleyle özetle. Madde işareti kullanma."
            ),
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
        )
        return cevap.text or "Sonuç bulunamadı."
    except Exception as e:
        hata = str(e)
        print(f"[Arama] HATA: {hata[:200]}", flush=True)
        if "429" in hata or "RESOURCE_EXHAUSTED" in hata:
            webbrowser.open(
                "https://www.google.com/search?q=" + urllib.parse.quote_plus(sorgu)
            )
            return "Arama kotası doldu. Sonuçları tarayıcıda açtım."
        return "İnternet araması şu an çalışmıyor."

def haber_basliklari(konu: str = "") -> str:
    """Türkiye'nin güncel haber başlıklarını getirir (Google Haberler).
    konu boşsa genel son dakika başlıklarını, doluysa o konudaki başlıkları
    getirir (örnek: 'ekonomi', 'Galatasaray', 'yapay zeka')."""
    import urllib.request
    import xml.etree.ElementTree as ET

    try:
        if konu.strip():
            url = ("https://news.google.com/rss/search?q="
                   + urllib.parse.quote_plus(konu) + "&hl=tr&gl=TR&ceid=TR:tr")
        else:
            url = "https://news.google.com/rss?hl=tr&gl=TR&ceid=TR:tr"
        istek = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(istek, timeout=8) as r:
            kok = ET.fromstring(r.read())
        basliklar = [
            (oge.findtext("title") or "").strip() for oge in kok.iter("item")
        ][:6]
        basliklar = [b for b in basliklar if b]
        if not basliklar:
            return "Haber bulunamadı."
        return "Güncel başlıklar: " + " | ".join(basliklar)
    except Exception as e:
        print(f"[Haber] HATA: {e}", flush=True)
        return f"Haberlere ulaşılamadı: {e}"


TOOLS = [
    web_sitesi_ac,
    google_ara,
    youtube_ara,
    uygulama_ac,
    medya_kontrol,
    saat_tarih_soyle,
    haber_basliklari,
    internette_ara,
]