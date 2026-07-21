"""Fikir üretimi: bir içerik sütunu → kulups özellik tanıtımı gönderisi.

Sağlayıcı zinciri (settings.ideation.chain): gemini → pollinations → template
  gemini       : Google AI Studio ÜCRETSİZ katman (GEMINI_API_KEY) — $0
  pollinations : anahtarsız ücretsiz metin ucu — $0
  claude       : opsiyonel, ücretli
  template     : anahtarsız yerel şablon bankası (offline fallback)

Dönüş sözleşmesi (dict):
    konsept_basligi   : kısa iç başlık (dedup anahtarı)
    kart_baslik       : GÖRSELİN üstüne basılacak büyük başlık (kısa, vurucu)
    kart_fayda        : başlığın altındaki tek cümlelik fayda
    gorsel_prompt     : İNGİLİZCE arka plan görseli prompt'u (YAZI İÇERMEZ)
    negatif_prompt    : İngilizce negatif prompt
    caption_metin     : Instagram açıklaması (2-4 cümle + yumuşak CTA)
    hashtag_onerileri : liste[str]
"""
from __future__ import annotations

import json
import random
import re
from typing import Any

import requests

from . import config

log = config.get_logger("ideate")

REQUIRED_KEYS = (
    "konsept_basligi",
    "kart_baslik",
    "kart_fayda",
    "gorsel_prompt",
    "negatif_prompt",
    "caption_metin",
    "hashtag_onerileri",
)
HTTP_TIMEOUT = 60


def ideate(pillar_key: str, pillar: dict[str, Any], recent_titles: list[str]) -> dict[str, Any]:
    """Sütun için bir gönderi fikri üretir. Zinciri sırayla dener."""
    ideation = config.settings().get("ideation", {}) or {}
    forced = config.env("IDEATE_PROVIDER")
    chain = [forced] if forced else list(
        ideation.get("chain", ["gemini", "pollinations", "template"]))

    system, user = _build_prompt(pillar, recent_titles, ideation)

    last_err: Exception | None = None
    for name in chain:
        try:
            if name == "template":
                return _template_fallback(pillar_key, pillar, recent_titles)
            raw = _call_provider(name, system, user, ideation)
            log.info("fikir üretildi → %s", name)
            return _validate(_parse_json(raw))
        except Exception as exc:
            log.warning("ideation '%s' başarısız: %s", name, exc)
            last_err = exc
            continue
    log.warning("tüm ideation sağlayıcıları başarısız (%s) → şablon", last_err)
    return _template_fallback(pillar_key, pillar, recent_titles)


def _call_provider(name: str, system: str, user: str, ideation: dict) -> str:
    fn = {"gemini": _gemini, "pollinations": _pollinations_text, "claude": _claude}.get(name)
    if not fn:
        raise ValueError(f"bilinmeyen ideation sağlayıcısı: {name}")
    return fn(system, user, ideation)


# ---------------------------------------------------------------------------
#  Ortak prompt
# ---------------------------------------------------------------------------
def _build_prompt(pillar: dict, recent_titles: list[str], ideation: dict) -> tuple[str, str]:
    dedup_n = int(ideation.get("dedup_hatirla", 50))
    kacinma = "\n".join(f"- {t}" for t in recent_titles[:dedup_n]) or "(henüz yok)"
    ozellikler = "\n".join(f"- {o}" for o in (pillar.get("ozellikler") or []))

    system = (
        "Sen kulups.com'un (Kulüp Yönetimi — basketbol kulüpleri için dijital yönetim "
        "sistemi) Instagram içerik editörüsün. Hedef kitlen: basketbol kulübü "
        "yöneticileri, antrenörler ve kulüp sahipleri.\n"
        "KURALLAR:\n"
        "1) SADECE aşağıda listelenen GERÇEK özellikleri anlat. Olmayan özellik UYDURMA.\n"
        "2) Abartılı vaat yok (‘%300 gelir’, ‘garanti’ gibi ifadeler yasak).\n"
        "3) Sade, samimi, profesyonel Türkçe. Antrenörün gerçek derdinden konuş.\n"
        "4) SADECE geçerli JSON döndür — açıklama, markdown, kod bloğu YOK."
    )

    user = f"""Aşağıdaki içerik sütunu için TEK bir özellik tanıtımı gönderisi üret.

SÜTUN: {pillar.get('ad')}
AÇIKLAMA: {pillar.get('aciklama')}

BU SÜTUNDAKİ GERÇEK ÖZELLİKLER (birini seç ve onu anlat):
{ozellikler}

YÖNLENDİRME: {pillar.get('yon')}
ÖRNEK TON: {pillar.get('ornek')}

Şu başlıkları TEKRARLAMA (yakın zamanda kullanıldı):
{kacinma}

Şu alanlara sahip bir JSON nesnesi döndür:
{{
  "konsept_basligi": "kısa iç başlık, hangi özelliği anlattığını belirtir (en fazla 6 kelime)",
  "kart_baslik": "GÖRSELİN üstüne basılacak büyük başlık. Kısa ve vurucu, EN FAZLA 7 KELİME. Faydayı ya da derdi söyler. Nokta koyma.",
  "kart_fayda": "başlığın altına gelecek TEK cümle, en fazla 14 kelime. Özelliğin somut faydası.",
  "gorsel_prompt": "İNGİLİZCE arka plan görseli prompt'u. Basketbol/kulüp ortamı, insanlar uzaktan ya da arkadan, YAKIN YÜZ YOK. Alt yarıda metin için BOŞ ALAN bırak. Görselde YAZI/LOGO OLMASIN. Ortak stil eki otomatik eklenecek, onu yazma.",
  "negatif_prompt": "İngilizce, bu görsele özel istenmeyenler (boş bırakabilirsin)",
  "caption_metin": "Instagram açıklaması: 2-4 cümle. Önce antrenörün/yöneticinin derdi, sonra kulups'un çözümü. Sonunda yumuşak bir davet (ör. 'Kulübün için 14 gün ücretsiz dene: kulups.com'). Emoji az ve yerinde.",
  "hashtag_onerileri": ["basketbol", "kulupyonetimi", "antrenor"]
}}

SADECE JSON döndür."""
    return system, user


# ---------------------------------------------------------------------------
#  Sağlayıcılar → ham metin
# ---------------------------------------------------------------------------
def _gemini(system: str, user: str, ideation: dict) -> str:
    key = config.env("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY yok")
    model = ideation.get("gemini_model", "gemini-2.5-flash-lite")
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": key},
        json={
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": float(ideation.get("temperature", 1.0)),
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingBudget": 0},
            },
        },
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"gemini {r.status_code}: {r.text[:200]}")
    cands = r.json().get("candidates") or []
    if not cands:
        raise RuntimeError(f"gemini boş yanıt: {str(r.json())[:200]}")
    return "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []))


def _pollinations_text(system: str, user: str, ideation: dict) -> str:
    r = requests.post(
        "https://text.pollinations.ai/openai",
        json={
            "model": ideation.get("pollinations_model", "openai"),
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "jsonMode": True,
            "seed": random.randint(1, 2_000_000_000),
        },
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"pollinations-text {r.status_code}: {r.text[:200]}")
    try:
        return r.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError):
        return r.text


def _claude(system: str, user: str, ideation: dict) -> str:
    key = config.env("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY yok")
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=ideation.get("anthropic_model", "claude-sonnet-4-6"),
        max_tokens=int(ideation.get("anthropic_max_tokens", 1024)),
        temperature=float(ideation.get("temperature", 1.0)),
        thinking={"type": "disabled"},
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


# ---------------------------------------------------------------------------
#  JSON ayrıştırma + doğrulama
# ---------------------------------------------------------------------------
def _parse_json(raw: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(),
                  flags=re.IGNORECASE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _validate(data: dict[str, Any]) -> dict[str, Any]:
    for key in REQUIRED_KEYS:
        if key not in data:
            raise ValueError(f"eksik alan: {key}")
    for key in ("konsept_basligi", "kart_baslik", "gorsel_prompt", "caption_metin"):
        if not str(data.get(key, "")).strip():
            raise ValueError(f"boş alan: {key}")

    tags = data.get("hashtag_onerileri") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in re.split(r"[,\s]+", tags) if t.strip()]
    data["hashtag_onerileri"] = [str(t).lstrip("#").strip() for t in tags if str(t).strip()]

    # Kart metinleri görsele basılacak: fazla uzunsa kırp (kart zaten sığdırır)
    data["kart_baslik"] = " ".join(str(data["kart_baslik"]).split()).rstrip(".")
    data["kart_fayda"] = " ".join(str(data.get("kart_fayda") or "").split())
    data["negatif_prompt"] = str(data.get("negatif_prompt") or "").strip()
    return data


# ---------------------------------------------------------------------------
#  Anahtarsız şablon fallback (offline / tüm sağlayıcılar patlarsa)
# ---------------------------------------------------------------------------
_BG = {
    "salon": "Wide interior shot of a modern basketball training hall, youth team "
             "practicing in the distance, warm window light across the hardwood, "
             "empty clean floor space in the lower half of the frame",
    "kenar": "A basketball coach seen from behind at the sideline watching practice, "
             "blurred team in the background, bright airy gym, clean empty floor in "
             "the lower part of the frame",
    "ofis": "Tidy modern sports club office desk with a laptop and a basketball on a "
            "shelf, soft daylight, calm and organised atmosphere, plenty of empty "
            "surface in the lower half",
    "tribun": "Parents watching a youth basketball practice from the stands, seen from "
              "a distance, warm friendly atmosphere, soft light, uncluttered lower half",
    "taktik": "A clipboard and basketball resting on a gym bench beside an empty court, "
              "early morning light, strategic calm mood, clean empty space below",
}


def _t(konsept, baslik, fayda, bg, caption, tags):
    return {"konsept_basligi": konsept, "kart_baslik": baslik, "kart_fayda": fayda,
            "gorsel_prompt": _BG[bg], "negatif_prompt": "", "caption_metin": caption,
            "hashtag_onerileri": tags}


_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "A": [
        _t("Yoklama tek dokunuş", "Yoklama artık deftere yazılmıyor",
           "Antrenman katılımını tek dokunuşla işaretle, devamsızlık raporu kendiliğinden çıksın.",
           "salon",
           "Deftere yazılan yoklama listesi kaybolur, kimin kaç antrenmana geldiği ay sonunda "
           "tartışma olur. kulups'ta yoklamayı tek dokunuşla alırsın, devamsızlık raporu hazır bekler.\n\n"
           "Kulübün için 14 gün ücretsiz dene: kulups.com",
           ["yoklama", "kulupyonetimi", "antrenor"]),
        _t("Haftalık program", "Program WhatsApp'ta kaybolmasın",
           "Haftalık antrenman ve maç takvimini oluştur; veli ve sporculara bildirim otomatik gitsin.",
           "kenar",
           "Program değişince 200 kişilik gruba mesaj atmak, sonra 'haberim yoktu' cevaplarıyla "
           "uğraşmak… kulups'ta takvimi bir kez kurarsın, bildirim herkese kendiliğinden ulaşır.\n\n"
           "Kulübün için 14 gün ücretsiz dene: kulups.com",
           ["antrenmanprogrami", "kulupyonetimi", "basketbol"]),
    ],
    "B": [
        _t("Ölçüm ve gelişim", "Gelişimi hissetme, ölç",
           "Boy, kilo ve performans ölçümlerini kaydet; sporcunun aylar içindeki gelişimini gör.",
           "salon",
           "'Çocuk gelişti mi?' sorusuna his ile değil veriyle cevap ver. kulups'ta ölçümleri "
           "kaydedersin, gelişim zaman içinde net görünür — veliye göstermesi de kolay olur.\n\n"
           "Kulübün için 14 gün ücretsiz dene: kulups.com",
           ["sporcugelisimi", "basketbol", "altyapi"]),
        _t("Sakatlık takibi", "Sakatlık geçmişi elinin altında",
           "Sakatlık kayıtları, beklenen dönüş tarihi ve sağlık geçmişi tek yerde dursun.",
           "kenar",
           "Hangi sporcu ne zaman sakatlandı, ne zaman dönecek? Aklında tutmak zorunda değilsin. "
           "kulups'ta sakatlık kaydı ve beklenen dönüş tarihi sporcu kartında durur.\n\n"
           "Kulübün için 14 gün ücretsiz dene: kulups.com",
           ["sakatlik", "sporsagligi", "kulupyonetimi"]),
    ],
    "C": [
        _t("Aidat kovalamak", "Aidat kovalamayı bırak",
           "Velilere talep gönder, iyzico ile kartla tahsil et; kim ödedi kim ödemedi net görünsün.",
           "ofis",
           "Ay başı geldi mi aidat mesajları başlar, elden nakit, defterde eksik kayıt… "
           "kulups'ta veli karttan öder, ödeme takibi kendiliğinden tutulur.\n\n"
           "Kulübün için 14 gün ücretsiz dene: kulups.com",
           ["aidat", "kulupyonetimi", "onlinetahsilat"]),
        _t("Kulüp mağazası", "Forma satışı da sistemde",
           "Forma, ekipman ve ürünlerini listele; kulüp içi satışlarını tek yerden yönet.",
           "ofis",
           "Forma siparişi toplamak ayrı bir iş: kim istedi, hangi beden, kim ödedi… "
           "kulups'un kulüp mağazasıyla ürünlerini listeler, satışları tek yerden görürsün.\n\n"
           "Kulübün için 14 gün ücretsiz dene: kulups.com",
           ["kulupmagazasi", "forma", "basketbol"]),
    ],
    "D": [
        _t("Veli portalı", "Veli her şeyi kendi panelinden görsün",
           "Program, aidat ve bildirimler velinin ve sporcunun kendi ekranında.",
           "tribun",
           "Veliden gelen 'antrenman kaçta?', 'aidatı yatırdım mı?' sorularına gün içinde "
           "defalarca cevap veriyorsan: kulups'ta veli kendi panelinden hepsini görür.\n\n"
           "Kulübün için 14 gün ücretsiz dene: kulups.com",
           ["veliiletisimi", "kulupyonetimi", "altyapi"]),
        _t("Evrak takibi", "Lisans ve sağlık raporu aranmasın",
           "Lisans, sağlık raporu ve sözleşmeleri sporcu bazında sakla, aradığında bul.",
           "ofis",
           "Turnuva öncesi evrak telaşı tanıdık gelir: kimin lisansı eksik, sağlık raporu nerede… "
           "kulups'ta belgeler sporcu kartında durur, aramana gerek kalmaz.\n\n"
           "Kulübün için 14 gün ücretsiz dene: kulups.com",
           ["evraktakibi", "lisans", "kulupyonetimi"]),
    ],
    "E": [
        _t("Ücretsiz taktik tahtası", "Taktik tahtası tamamen ücretsiz",
           "Sürükle-bırak ile oyunu kur, çizimi kaydet ve yazdır. Üyelik gerekmez.",
           "taktik",
           "Oyun kurarken kâğıda çizip fotoğrafını çekmeye son. kulups'un taktik tahtası "
           "sürükle-bırak çalışır, çizimini kaydedip yazdırabilirsin — üstelik üyelik "
           "gerekmiyor, tamamen ücretsiz.\n\n"
           "Hemen dene: kulups.com",
           ["taktiktahtasi", "antrenor", "basketbol"]),
        _t("Oyun kurma aracı", "Antrenörler için ücretsiz araç",
           "Üyelik olmadan oyun kur, çizimlerini kaydet, antrenmana yazdırıp götür.",
           "taktik",
           "Antrenman öncesi oyunu anlatmanın en hızlı yolu: çiz, kaydet, yazdır. "
           "kulups'un taktik tahtası bunu ücretsiz yapıyor, üyelik bile istemiyor.\n\n"
           "Hemen dene: kulups.com",
           ["taktik", "basketbolantrenoru", "ucretsiz"]),
    ],
}


def _template_fallback(pillar_key: str, pillar: dict, recent_titles: list[str]) -> dict[str, Any]:
    options = _TEMPLATES.get(pillar_key) or _TEMPLATES["A"]
    recent = set(recent_titles or [])
    chosen = next((o for o in options if o["konsept_basligi"] not in recent), options[0])
    log.info("şablon fikir kullanıldı: %s", chosen["konsept_basligi"])
    return _validate(dict(chosen))
