"""Orkestratör: bir gönderiyi baştan sona üretir (ve isteğe bağlı yayınlar).

Akış:  state → ideate → compose(kart) → host → KUYRUK (onay) → SQLite kaydı
Varsayılan --dry-run: yayınlamaz, preview/ klasörüne görsel + caption yazar.
Hata olursa satır 'failed' işaretlenir, sütun rotasyonu ilerletilmez (yeniden denenir).

Kullanım:
    python -m src.pipeline                 # dry-run, 1 gönderi (preview/)
    python -m src.pipeline --count 3       # dry-run, 3 gönderi
    python -m src.pipeline --queue         # taslağı onay kuyruğuna gönder
    python -m src.pipeline --queue --count 2
    # NOT: doğrudan yayın KAPALI. Yayın yalnızca kulups.com panelinden onayla yapılır.
    PROVIDER=cloudflare python -m src.pipeline
"""
from __future__ import annotations

import argparse
import re
import time
import unicodedata
from pathlib import Path

from . import config
from .caption import build_caption
from .card import compose
from .host import host_image
from .ideate import ideate
from .publish import publish
from .state import State

log = config.get_logger("pipeline")
ROOT = Path(__file__).resolve().parent.parent
PREVIEW_DIR = ROOT / "preview"
OUTPUT_DIR = ROOT / "output"


def run_once(dry_run: bool = True, queue: bool = False, exclude: tuple | None = None) -> dict:
    """Tek bir gönderi üretir. Sonuç özetini (dict) döndürür."""
    settings = config.settings()
    pillars_cfg = config.pillars()
    rotation = pillars_cfg.get("rotation", [])
    pillars = pillars_cfg.get("pillars", {})

    state = State()

    # 24 saat kotası (yalnızca gerçek yayında)
    if not dry_run:
        max24 = int(settings.get("posting", {}).get("max_per_24h", 45))
        used = state.count_last_24h(("published",))
        if used >= max24:
            log.warning("24s yayın kotası dolu (%d/%d) — atlanıyor", used, max24)
            return {"status": "skipped_limit", "used": used, "max": max24}

    pillar_key = state.next_pillar(rotation)
    pillar = pillars.get(pillar_key, {})
    log.info("sütun seçildi: %s (%s)", pillar_key, pillar.get("ad", "?"))

    # 1) Fikir
    dedup_n = int(settings.get("ideation", {}).get("dedup_hatirla", 50))
    concept = ideate(pillar_key, pillar, state.recent_titles(dedup_n))
    title = concept["konsept_basligi"]
    log.info("konsept: %s", title)

    # Erken taslak kaydı (hata olsa da izlenebilir)
    post_id = state.record_post(pillar=pillar_key, title=title, status="draft")

    try:
        ex_t, ex_p = exclude if exclude else (set(), set())
        image_bytes, provider, photo = compose(
            concept, pillar=pillar_key, exclude_templates=ex_t, exclude_photos=ex_p)
        ex_t.add(provider); ex_p.add(photo)
        cap = build_caption(concept)
        filename = _filename(pillar_key, title)

        if queue:
            url = host_image(image_bytes, filename)
            qid = queue_draft(url, cap, concept, provider, pillar_key)
            state.update_post(post_id, image_path=f"output/{filename}", image_url=url,
                              prompt=concept.get("gorsel_prompt", ""), status="queued")
            result = {"image_url": url, "queue_id": qid}
        elif dry_run:
            result = _write_preview(image_bytes, cap, concept, filename)
            state.update_post(post_id, image_path=str(result["image"]),
                              prompt=concept["gorsel_prompt"], status="dry-run")
        else:
            url = host_image(image_bytes, filename)
            media_id = publish(url, cap)
            state.update_post(post_id, image_path=f"output/{filename}", image_url=url,
                              media_id=media_id, prompt=concept["gorsel_prompt"],
                              status="published")
            result = {"image_url": url, "media_id": media_id}

        # Başarı → sütun rotasyonunu ilerlet
        state.mark_pillar_used(pillar_key)
        summary = {"status": "queued" if queue else ("dry-run" if dry_run else "published"),
                   "pillar": pillar_key, "title": title, "provider": provider, "photo": photo, **result}
        log.info("TAMAM: %s", summary)
        return summary

    except Exception as exc:
        state.update_post(post_id, status="failed")
        log.error("gönderi başarısız (%s): %s", title, exc)
        raise


def run(count: int = 1, dry_run: bool = True, queue: bool = False) -> list[dict]:
    exclude = (set(), set())   # parti içinde şablon + fotoğraf tekrarını engelle
    """N gönderi üretir. Hata olursa kalanları denemeyi sürdürür."""
    results = []
    for i in range(count):
        log.info("=== gönderi %d/%d ===", i + 1, count)
        try:
            results.append(run_once(dry_run=dry_run, queue=queue, exclude=exclude))
        except Exception as exc:
            results.append({"status": "failed", "error": str(exc)})
    return results


# ---------------------------------------------------------------------------
#  Onay kuyruğu — taslağı kulups.com paneline gönderir (YAYINLAMAZ)
# ---------------------------------------------------------------------------
QUEUE_URL = ("https://europe-west1-kulup-yonetimi-1a3c5.cloudfunctions.net/igTaslakEkle")


def queue_draft(image_url: str, caption: str, concept: dict, template: str, pillar: str) -> str:
    """Taslağı onay kuyruğuna koyar. Yayın, panelden onaylanınca yapılır."""
    import requests
    token = config.env("IG_QUEUE_TOKEN")
    if not token:
        raise RuntimeError("IG_QUEUE_TOKEN tanımlı değil — taslak kuyruğa gönderilemedi")
    r = requests.post(QUEUE_URL, json={
        "token": token,
        "imageUrl": image_url,
        "caption": caption,
        "headline": concept.get("kart_baslik", ""),
        "benefit": concept.get("kart_fayda", ""),
        "template": template,
        "pillar": pillar,
    }, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"kuyruk hatası ({r.status_code}): {r.text[:200]}")
    qid = (r.json() or {}).get("id", "")
    log.info("ONAY KUYRUĞUNA EKLENDİ → id=%s (panelden onaylanınca yayınlanır)", qid)
    return qid


# ---------------------------------------------------------------------------
#  Yardımcılar
# ---------------------------------------------------------------------------
def _write_preview(image_bytes: bytes, caption: str, concept: dict, filename: str) -> dict:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    img_path = PREVIEW_DIR / filename
    txt_path = PREVIEW_DIR / (filename.rsplit(".", 1)[0] + ".txt")
    img_path.write_bytes(image_bytes)
    txt_path.write_text(
        f"# {concept['konsept_basligi']}\n\n{caption}\n\n"
        f"--- görsel prompt ---\n{concept['gorsel_prompt']}\n",
        encoding="utf-8",
    )
    try:
        shown = img_path.relative_to(ROOT)
    except ValueError:
        shown = img_path
    log.info("önizleme yazıldı: %s", shown)
    return {"image": img_path, "caption_file": txt_path}


def _filename(pillar_key: str, title: str) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    return f"{stamp}_{pillar_key}_{_slug(title)}.jpg"


def _slug(text: str, maxlen: int = 40) -> str:
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    norm = re.sub(r"[^a-zA-Z0-9]+", "-", norm).strip("-").lower()
    return (norm or "post")[:maxlen]


def main() -> None:
    parser = argparse.ArgumentParser(description="Siberpunk otonom Instagram içerik botu")
    parser.add_argument("--queue", action="store_true",
                        help="taslağı kulups.com onay kuyruğuna gönder (yayınlamaz)")
    parser.add_argument("--publish", action="store_true",
                        help="gerçekten Instagram'a yayınla (varsayılan: dry-run)")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=None,
                        help="yayınlama; preview/ klasörüne yaz (varsayılan davranış)")
    parser.add_argument("--count", type=int, default=None,
                        help="tek çalışmada üretilecek gönderi sayısı")
    args = parser.parse_args()

    settings = config.settings()
    dry_run = not args.publish  # --publish verilmedikçe dry-run
    if args.publish and not args.queue:
        parser.error('Doğrudan yayın kapalı. --queue kullan; yayın panelden onayla yapılır.')
    if args.dry_run:
        dry_run = True
    count = args.count or int(settings.get("posting", {}).get("daily_count", 1))

    log.info("mod: %s | count: %d", "DRY-RUN" if dry_run else "PUBLISH", count)
    results = run(count=count, dry_run=dry_run, queue=args.queue)

    ok = sum(1 for r in results if r.get("status") in ("dry-run", "published", "queued"))
    log.info("bitti: %d/%d başarılı", ok, len(results))
    if ok < len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
