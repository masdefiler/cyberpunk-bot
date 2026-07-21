"""Açıklama (caption) kurulumu: mikro-kurgu + ayraç + karışık hashtag seti.

Her gönderide hashtag'ler havuzlardan RASTGELE ve farklı seçilir (aynı blok
tekrar tekrar görünmesin diye) — Instagram'ın spam sinyallerinden kaçınır.
"""
from __future__ import annotations

import random

from . import config

log = config.get_logger("caption")

SEPARATOR = "•　•　•"


def build_caption(concept: dict) -> str:
    """Konseptten tam caption metnini kurar."""
    settings = config.settings()
    posting = settings.get("posting", {}) or {}
    lo = int(posting.get("hashtag_min", 15))
    hi = int(posting.get("hashtag_max", 25))

    body_text = str(concept.get("caption_metin", "")).strip()
    title = str(concept.get("kart_baslik") or concept.get("konsept_basligi") or "").strip()

    tags = _select_hashtags(concept.get("hashtag_onerileri", []), lo, hi, settings)
    tag_line = " ".join(f"#{t}" for t in tags)

    body = body_text or title
    parts = [body, "", SEPARATOR, "", tag_line]
    return "\n".join(parts).strip()


def _select_hashtags(suggested: list[str], lo: int, hi: int, settings: dict) -> list[str]:
    """Konsept önerileri + havuzlardan karışık, tekrarsız 15-25 hashtag."""
    pools = settings.get("hashtags", {}) or {}
    count = random.randint(lo, hi)

    picked: list[str] = []
    seen: set[str] = set()

    def add(tag: str) -> None:
        t = str(tag).lstrip("#").strip().replace(" ", "")
        key = t.lower()
        if t and key not in seen:
            seen.add(key)
            picked.append(t)

    # 1) Konsepte özel öneriler önce (en fazla 5 tanesi)
    for t in list(suggested)[:5]:
        add(t)

    # 2) Her havuzdan orantılı, karışık seçim
    all_pool: list[str] = []
    for tags in pools.values():
        sample = list(tags)
        random.shuffle(sample)
        all_pool.extend(sample)
    random.shuffle(all_pool)

    for t in all_pool:
        if len(picked) >= count:
            break
        add(t)

    random.shuffle(picked)  # öneriler hep başta olmasın
    return picked[:count]
