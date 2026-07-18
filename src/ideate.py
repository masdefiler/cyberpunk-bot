"""Fikir üretimi: bir içerik sütunu → konsept + görsel prompt + kurgu metni.

Sağlayıcı zinciri (settings.ideation.chain, varsayılan): gemini → pollinations → template
  gemini       : Google AI Studio ÜCRETSİZ katman (GEMINI_API_KEY) — $0
  pollinations : anahtarsız ücretsiz metin ucu — $0
  claude       : claude-sonnet-4-6 (ANTHROPIC_API_KEY) — opsiyonel, ücretli
  template     : anahtarsız yerel şablon bankası (offline fallback)
Biri patlarsa/parse edemezse sıradakine düşülür → sistem her koşulda üretir.

Dönüş sözleşmesi (dict): konsept_basligi, gorsel_prompt, negatif_prompt,
                         kisa_kurgu_metin, hashtag_onerileri
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
    "gorsel_prompt",
    "negatif_prompt",
    "kisa_kurgu_metin",
    "hashtag_onerileri",
)
HTTP_TIMEOUT = 60


def ideate(pillar_key: str, pillar: dict[str, Any], recent_titles: list[str]) -> dict[str, Any]:
    """Sütun için bir gönderi fikri üretir. Zinciri sırayla dener."""
    ideation = config.settings().get("ideation", {}) or {}
    forced = config.env("IDEATE_PROVIDER")
    chain = [forced] if forced else list(ideation.get("chain", ["gemini", "pollinations", "template"]))

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
    """API sağlayıcısını çağırır (bir kez retry ile), ham metin döndürür."""
    fn = {
        "gemini": _gemini,
        "pollinations": _pollinations_text,
        "claude": _claude,
    }.get(name)
    if not fn:
        raise ValueError(f"bilinmeyen ideation sağlayıcısı: {name}")
    try:
        return fn(system, user, ideation)
    except _ParseRetry:
        log.info("%s JSON parse başarısız, bir kez daha", name)
        return fn(system, user, ideation)


class _ParseRetry(Exception):
    """Sağlayıcı içinde tek seferlik retry sinyali (kullanılmıyorsa yok sayılır)."""


# ---------------------------------------------------------------------------
#  Ortak prompt
# ---------------------------------------------------------------------------
def _build_prompt(pillar: dict, recent_titles: list[str], ideation: dict) -> tuple[str, str]:
    dedup_n = int(ideation.get("dedup_hatirla", 50))
    kacinma = "\n".join(f"- {t}" for t in recent_titles[:dedup_n]) or "(henüz yok)"
    system = (
        "Sen bir siberpunk / alternatif tarih & gelecek temalı Instagram hesabının "
        "yaratıcı yönetmenisin. Görsel olarak tutarlı, atmosferik, sinematik konseptler "
        "üretiyorsun. SADECE geçerli JSON döndür — açıklama, markdown, kod bloğu YOK."
    )
    user = f"""Aşağıdaki içerik sütunu için TEK bir özgün gönderi fikri üret.

SÜTUN: {pillar.get('ad')}
AÇIKLAMA: {pillar.get('aciklama')}
YÖNLENDİRME: {pillar.get('yon')}
ÖRNEK TON: {pillar.get('ornek')}

Şu başlıkları TEKRARLAMA (yakın zamanda üretildi):
{kacinma}

Şu alanlara sahip bir JSON nesnesi döndür:
{{
  "konsept_basligi": "kısa, çarpıcı Türkçe başlık (en fazla 6 kelime)",
  "gorsel_prompt": "İNGİLİZCE, çok detaylı görsel üretim prompt'u. Sahneyi, ışığı, kadrajı, atmosferi betimle. Ortak stil eki OTOMATİK eklenecek, onu YAZMA. Tek kişi/nesne/mekana odaklan.",
  "negatif_prompt": "İngilizce, bu konsepte özel istenmeyen öğeler (boş bırakabilirsin)",
  "kisa_kurgu_metin": "1-3 cümlelik Türkçe mikro-kurgu; görseli bir dünyaya bağlayan atmosferik anlatı",
  "hashtag_onerileri": ["konu", "ozel", "hashtagler"]
}}

SADECE JSON döndür."""
    return system, user


# ---------------------------------------------------------------------------
#  Sağlayıcılar → ham metin
# ---------------------------------------------------------------------------
def _gemini(system: str, user: str, ideation: dict) -> str:
    """Google AI Studio ücretsiz katman. responseMimeType=application/json ile temiz JSON."""
    key = config.env("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY yok")
    model = ideation.get("gemini_model", "gemini-2.5-flash-lite")
    temp = float(ideation.get("temperature", 1.0))
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = requests.post(
        url,
        params={"key": key},
        json={
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": temp,
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
    parts = cands[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def _pollinations_text(system: str, user: str, ideation: dict) -> str:
    """Anahtarsız ücretsiz metin ucu (OpenAI uyumlu)."""
    seed = random.randint(1, 2_000_000_000)
    r = requests.post(
        "https://text.pollinations.ai/openai",
        json={
            "model": ideation.get("pollinations_model", "openai"),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "jsonMode": True,
            "seed": seed,
        },
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"pollinations-text {r.status_code}: {r.text[:200]}")
    try:
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError):
        return r.text   # bazı yanıtlar düz metin JSON döndürür


def _claude(system: str, user: str, ideation: dict) -> str:
    """claude-sonnet-4-6 (opsiyonel, ücretli)."""
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
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _validate(data: dict[str, Any]) -> dict[str, Any]:
    for key in REQUIRED_KEYS:
        if key not in data:
            raise ValueError(f"eksik alan: {key}")
    if not str(data["konsept_basligi"]).strip():
        raise ValueError("boş konsept_basligi")
    if not str(data["gorsel_prompt"]).strip():
        raise ValueError("boş gorsel_prompt")
    tags = data.get("hashtag_onerileri") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in re.split(r"[,\s]+", tags) if t.strip()]
    data["hashtag_onerileri"] = [str(t).lstrip("#").strip() for t in tags if str(t).strip()]
    data["negatif_prompt"] = str(data.get("negatif_prompt") or "").strip()
    return data


# ---------------------------------------------------------------------------
#  Anahtarsız şablon fallback (offline / tüm sağlayıcılar patlarsa)
# ---------------------------------------------------------------------------
_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "A": [
        {
            "konsept_basligi": "Neon Boğaziçi 1923",
            "gorsel_prompt": "1920s Istanbul waterfront reimagined, ornate Ottoman wooden mansions "
            "beside towering holographic minarets, a neon-lit steam tram gliding over the Bosphorus, "
            "gas lamps mixed with floating cyan hologram signage, rain-slicked cobblestones, a lone "
            "figure in a fez and long coat watching an airship dock",
            "kisa_kurgu_metin": "1923'te Boğaz'ın iki yakasını hologram tramvaylar birbirine "
            "dikiyordu. Kimse o gece limana inen sessiz zeplinin nereden geldiğini soramadı.",
        },
        {
            "konsept_basligi": "Buharlı Saray Devriyesi",
            "gorsel_prompt": "Victorian London street at dusk reimagined, brass clockwork androids "
            "patrolling under gas lamps, holographic advertisements flickering above hansom cabs, "
            "a detective in a top hat with a glowing cybernetic monocle, fog and neon reflections on "
            "wet stone, dirigibles overhead",
            "kisa_kurgu_metin": "Pirinç dişlilerden yapılmış devriyeler sisli sokaklarda dolanırken, "
            "monoklündeki ışık dedektife kimin yalan söylediğini fısıldıyordu.",
        },
    ],
    "B": [
        {
            "konsept_basligi": "Jakarta 2071, Yağmur Çarşısı",
            "gorsel_prompt": "Dense 2071 Jakarta night market alley, isometric framing, layered "
            "neon signage in multiple scripts, steam rising from food stalls, crowds under "
            "translucent umbrellas, holographic koi swimming through the air, reflective wet pavement, "
            "cables and vertical gardens above",
            "kisa_kurgu_metin": "2071 Jakarta'sında yağmur hiç dinmez; çarşının neon suları herkesin "
            "yüzüne başka bir gelecek çizerdi.",
        },
        {
            "konsept_basligi": "Yukarı Kat Sokakları 2088",
            "gorsel_prompt": "Street-level scene of a stacked megacity in 2088, rain and steam, "
            "pedestrians with glowing umbrellas, towering holographic billboards in cyan and magenta, "
            "food vendor cart with warm amber light, monorail arcing overhead, dense atmospheric haze",
            "kisa_kurgu_metin": "Şehrin kırk sekizinci katında güneş efsaneydi; herkes neonların "
            "altında, kendi yağmuruyla yaşardı.",
        },
    ],
    "C": [
        {
            "konsept_basligi": "Ormanın Yuttuğu Sunucu",
            "gorsel_prompt": "Abandoned colossal data center reclaimed by jungle, shattered solar "
            "panels, thick vines coiling through server racks, shafts of light through a broken roof, "
            "moss and standing water, a single deer standing in the ruined server hall, profound silence",
            "kisa_kurgu_metin": "Sunucular sustuğunda orman konuşmaya başladı. Salonun ortasında "
            "duran geyik, insanlığın son verisini otluyordu.",
        },
        {
            "konsept_basligi": "Terk Edilmiş Uzay Limanı",
            "gorsel_prompt": "Overgrown futuristic spaceport at dawn, rusted launch gantries wrapped "
            "in ivy, cracked runway reclaimed by tall grass, a half-buried shuttle, birds nesting in "
            "control towers, soft mist, melancholic post-apocalyptic stillness",
            "kisa_kurgu_metin": "Son mekik hiç kalkmadı. Şimdi kulelerde kuşlar yuva yapıyor, pistte "
            "otlar fısıldaşıyor.",
        },
    ],
    "D": [
        {
            "konsept_basligi": "Krom Gözlü Sokak Hackeri",
            "gorsel_prompt": "Close-up cinematic portrait of a cyberpunk street hacker, chrome ocular "
            "implant glowing cyan, circuit tattoos along the jaw, hood half up, rain droplets on skin, "
            "dramatic magenta side light, reflective eyes, shallow depth of field",
            "kisa_kurgu_metin": "Gözündeki krom, gördüğü her yalanı satır satır okurdu. Bu yüzden kimse "
            "ona doğrudan bakamazdı.",
        },
        {
            "konsept_basligi": "Protez Kollu Tamirci",
            "gorsel_prompt": "Medium cyberpunk portrait of a weary mechanic with an exposed articulated "
            "prosthetic arm, grease and neon glow, workshop sparks in the background, warm amber key "
            "light against cool teal shadows, intricate mechanical detail, story in the eyes",
            "kisa_kurgu_metin": "Kolunu kendisi yaptı, üç gece uykusuz. Şimdi o kol, tüm mahallenin "
            "kırık kalbini tamir ediyor.",
        },
    ],
    "E": [
        {
            "konsept_basligi": "2140 Nöral Arayüz Maskesi",
            "gorsel_prompt": "A single fictional neural interface mask presented in a museum vitrine, "
            "matte black ceramic with glowing cyan filament veins, thin cables coiled beside it, dark "
            "seamless background, one focused spotlight, extreme material detail, product-catalog framing",
            "kisa_kurgu_metin": "2140 yapımı bu maske takanın rüyalarını kaydederdi. Vitrindeki etikette "
            "tek satır yazıyor: 'İade edilemez.'",
        },
        {
            "konsept_basligi": "Sessizlik Vericisi, Model VII",
            "gorsel_prompt": "A fictional handheld device labeled as a 'silence transmitter' displayed "
            "as a catalog artifact, brushed brass and dark glass, a single amber indicator light, "
            "floating on a clean dark surface, one soft key light, museum-grade presentation, hyper detail",
            "kisa_kurgu_metin": "Model VII bir düğmeye basınca, çevresindeki yüz metre bir anlığına "
            "tarihten silinirdi. Kaç tane üretildiği hâlâ bilinmiyor.",
        },
    ],
}


def _template_fallback(pillar_key: str, pillar: dict, recent_titles: list[str]) -> dict[str, Any]:
    options = _TEMPLATES.get(pillar_key) or _TEMPLATES["B"]
    recent = set(recent_titles or [])
    chosen = next((o for o in options if o["konsept_basligi"] not in recent), options[0])
    log.info("şablon fikir kullanıldı: %s", chosen["konsept_basligi"])
    return _validate(
        {
            "konsept_basligi": chosen["konsept_basligi"],
            "gorsel_prompt": chosen["gorsel_prompt"],
            "negatif_prompt": "",
            "kisa_kurgu_metin": chosen["kisa_kurgu_metin"],
            "hashtag_onerileri": [],
        }
    )
