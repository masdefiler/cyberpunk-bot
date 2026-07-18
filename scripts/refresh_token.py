"""Uzun ömürlü Instagram token'ını yeniler (60 günde bir çalıştırılmalı).

Instagram Login (IGAA) token'ları için graph.instagram.com/refresh_access_token
kullanılır — sadece mevcut token gerekir, app id/secret gerekmez. Yeni token 60 gün
daha geçerlidir. GitHub Actions içinde çalışıyorsa yeni token GITHUB_OUTPUT'a yazılır
ve workflow onu 'gh secret set IG_ACCESS_TOKEN' ile geri saklar.

Facebook Login akışı kullanılıyorsa GRAPH_MODE=facebook + IG_APP_ID/IG_APP_SECRET ile
fb_exchange_token uçları kullanılır.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import config  # noqa: E402

log = config.get_logger("refresh")


def refresh_instagram() -> tuple[str, int]:
    """graph.instagram.com üzerinden token'ı yeniler → (yeni_token, saniye_geçerlilik)."""
    token = config.env("IG_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("IG_ACCESS_TOKEN yok")
    r = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
        timeout=60,
    )
    data = r.json()
    if r.status_code >= 400 or "access_token" not in data:
        raise RuntimeError(f"yenileme başarısız ({r.status_code}): {data}")
    return data["access_token"], int(data.get("expires_in", 0))


def refresh_facebook() -> tuple[str, int]:
    """Facebook Login: kısa/uzun token'ı fb_exchange_token ile uzatır."""
    token = config.env("IG_ACCESS_TOKEN")
    app_id = config.env("IG_APP_ID")
    app_secret = config.env("IG_APP_SECRET")
    if not all([token, app_id, app_secret]):
        raise RuntimeError("Facebook modu için IG_ACCESS_TOKEN/IG_APP_ID/IG_APP_SECRET gerekli")
    r = requests.get(
        "https://graph.facebook.com/v21.0/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": token,
        },
        timeout=60,
    )
    data = r.json()
    if r.status_code >= 400 or "access_token" not in data:
        raise RuntimeError(f"yenileme başarısız ({r.status_code}): {data}")
    return data["access_token"], int(data.get("expires_in", 0))


def main() -> None:
    mode = (config.env("GRAPH_MODE") or "instagram").lower()
    new_token, expires_in = refresh_facebook() if mode == "facebook" else refresh_instagram()
    days = expires_in // 86400 if expires_in else "?"
    log.info("token yenilendi — %s gün geçerli", days)

    # GitHub Actions'a devret (workflow secret'ı güncelleyecek)
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        print(f"::add-mask::{new_token}")   # log'da maskele
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"new_token={new_token}\n")
        log.info("yeni token GITHUB_OUTPUT'a yazıldı")
    else:
        # Yerelde: token'ı göster (kullanıcı .env'i günceller)
        print(new_token)


if __name__ == "__main__":
    main()
