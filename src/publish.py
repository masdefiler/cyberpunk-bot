"""Instagram Graph API ile yayınlama — iki adımlı akış.

1) POST /{ig_user_id}/media          (image_url + caption)  → creation_id
2) durum FINISHED olana kadar bekle  (GET /{creation_id}?fields=status_code)
3) POST /{ig_user_id}/media_publish  (creation_id)          → media_id

IGAA (Instagram Login) token'ları için taban graph.instagram.com'dur; Facebook
Login akışı için GRAPH_BASE=https://graph.facebook.com/v21.0 ile değiştirilebilir.
"""
from __future__ import annotations

import time

import requests

from . import config

log = config.get_logger("publish")

DEFAULT_GRAPH_BASE = "https://graph.instagram.com"
HTTP_TIMEOUT = 60
POLL_INTERVAL = 4       # saniye
POLL_MAX_TRIES = 20     # ~80 sn
# Video (Reels) işleme dakikalar sürebilir → daha seyrek ama çok daha uzun yoklama
VIDEO_POLL_INTERVAL = 10
VIDEO_POLL_MAX_TRIES = 60   # ~10 dk


class PublishError(RuntimeError):
    pass


def _base() -> str:
    return (config.env("GRAPH_BASE") or DEFAULT_GRAPH_BASE).rstrip("/")


def publish(image_url: str, caption: str) -> str:
    """Görsel URL + caption yayınlar, media_id döndürür."""
    ig_user_id = config.env("IG_USER_ID")
    token = config.env("IG_ACCESS_TOKEN")
    if not (ig_user_id and token):
        raise PublishError("IG_USER_ID / IG_ACCESS_TOKEN tanımlı değil")

    creation_id = _create_container(ig_user_id, image_url, caption, token)
    _wait_until_ready(creation_id, token)
    return _publish_container(ig_user_id, creation_id, token)


def publish_video(video_url: str, caption: str, cover_url: str | None = None) -> str:
    """Videoyu Reels olarak yayınlar (feed'de de görünür), media_id döndürür.

    video_url public erişilebilir olmalı (Instagram dosya yükleme kabul etmez).
    Video işleme dakikalar sürebildiği için durum yoklaması uzun tutulur.
    Desteklenen biçim pratikte: MP4 (H.264 + AAC), 9:16 önerilir, ≤90 sn, ≤100 MB.
    """
    ig_user_id = config.env("IG_USER_ID")
    token = config.env("IG_ACCESS_TOKEN")
    if not (ig_user_id and token):
        raise PublishError("IG_USER_ID / IG_ACCESS_TOKEN tanımlı değil")

    data = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
        "access_token": token,
    }
    if cover_url:
        data["cover_url"] = cover_url
    r = requests.post(f"{_base()}/{ig_user_id}/media", data=data, timeout=HTTP_TIMEOUT)
    payload = _json_or_error(r, "video konteyneri oluşturma")
    creation_id = payload.get("id")
    if not creation_id:
        raise PublishError(f"creation_id alınamadı: {payload}")
    log.info("video konteyneri oluşturuldu: %s", creation_id)
    _wait_until_ready(creation_id, token,
                      interval=VIDEO_POLL_INTERVAL, max_tries=VIDEO_POLL_MAX_TRIES)
    return _publish_container(ig_user_id, creation_id, token)


def _create_container(ig_user_id: str, image_url: str, caption: str, token: str) -> str:
    r = requests.post(
        f"{_base()}/{ig_user_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": token},
        timeout=HTTP_TIMEOUT,
    )
    data = _json_or_error(r, "media konteyneri oluşturma")
    creation_id = data.get("id")
    if not creation_id:
        raise PublishError(f"creation_id alınamadı: {data}")
    log.info("media konteyneri oluşturuldu: %s", creation_id)
    return creation_id


def _wait_until_ready(creation_id: str, token: str,
                      interval: int = POLL_INTERVAL, max_tries: int = POLL_MAX_TRIES) -> None:
    """Konteyner FINISHED olana kadar bekler; ERROR/EXPIRED'de hata verir."""
    for attempt in range(1, max_tries + 1):
        r = requests.get(
            f"{_base()}/{creation_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=HTTP_TIMEOUT,
        )
        data = _json_or_error(r, "konteyner durumu")
        status = data.get("status_code")
        if status == "FINISHED":
            log.info("konteyner hazır (%d. deneme)", attempt)
            return
        if status in ("ERROR", "EXPIRED"):
            raise PublishError(f"konteyner durumu {status}: {data.get('status')}")
        log.info("konteyner durumu %s, bekleniyor… (%d/%d)", status, attempt, max_tries)
        time.sleep(interval)
    raise PublishError("konteyner zaman aşımı (FINISHED olmadı)")


def _publish_container(ig_user_id: str, creation_id: str, token: str) -> str:
    r = requests.post(
        f"{_base()}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=HTTP_TIMEOUT,
    )
    data = _json_or_error(r, "yayınlama")
    media_id = data.get("id")
    if not media_id:
        raise PublishError(f"media_id alınamadı: {data}")
    log.info("YAYINLANDI → media_id=%s", media_id)
    return media_id


def _json_or_error(r: requests.Response, step: str) -> dict:
    try:
        data = r.json()
    except ValueError:
        raise PublishError(f"{step}: JSON olmayan yanıt ({r.status_code}): {r.text[:200]}")
    if r.status_code >= 400 or "error" in data:
        err = data.get("error", {})
        raise PublishError(f"{step} hatası ({r.status_code}): {err.get('message', data)}")
    return data
