# -*- coding: utf-8 -*-
"""
ÖZEL GÖNDERİ — elde hazırlanmış bir görseli onay kuyruğuna koyar.

Kart motorundan geçmeyen gönderiler içindir: bayram/anma görselleri, duyurular,
tek seferlik tasarımlar. Şablon rotasyonuna ve sütun (pillar) sayacına DOKUNMAZ.

    python3 scripts/ozel_gonderi.py --gorsel yol/a.jpg --caption yol/a.txt \
        --slug 30-agustos --template 30agustos --pillar ozel [--dry]

Akış, parti_uret.py ile aynı ve sırası ÖNEMLİ:
  1) görseli output/'a yaz     2) commit + push     3) URL'in CANLI olduğunu doğrula
  4) kuyruğa koy
Instagram dosya yükleme kabul etmez, yalnız URL çeker; URL canlı değilken kuyruğa
koymak panelde yayına basıldığı an başarısız bir gönderi demektir.
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src import config                      # noqa: E402
from src.host import host_image             # noqa: E402
from src.pipeline import queue_draft        # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
log = config.get_logger("ozel")


def _slugify(s: str) -> str:
    tr = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    s = s.translate(tr).lower()
    return "".join(c if c.isalnum() else "-" for c in s).strip("-")[:40]


def _canli_mi(url: str, deneme: int = 8) -> bool:
    """raw.githubusercontent önbelleği birkaç saniye gecikebiliyor — bekleyip bak."""
    import requests
    for i in range(deneme):
        try:
            r = requests.get(url, timeout=20, stream=True)
            if r.status_code == 200 and int(r.headers.get("content-length", "1")) > 1000:
                return True
        except Exception:
            pass
        time.sleep(3)
        log.info("URL henüz canlı değil, bekleniyor (%d/%d)", i + 1, deneme)
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gorsel", required=True)
    ap.add_argument("--caption", required=True, help="metin dosyası ya da metnin kendisi")
    ap.add_argument("--slug", default="ozel")
    ap.add_argument("--template", default="ozel")
    ap.add_argument("--pillar", default="ozel", help="rotasyona karışmasın diye varsayılan 'ozel'")
    ap.add_argument("--dry", action="store_true", help="yalnız yaz ve göster, kuyruğa KOYMA")
    a = ap.parse_args()

    gorsel = pathlib.Path(a.gorsel).expanduser()
    if not gorsel.exists():
        sys.exit(f"görsel yok: {gorsel}")
    img = gorsel.read_bytes()

    cp = pathlib.Path(a.caption).expanduser()
    caption = cp.read_text(encoding="utf-8").strip() if cp.exists() else a.caption

    fn = f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}_{_slugify(a.slug)}{gorsel.suffix}"

    # 1) output/'a yaz
    url = host_image(img, fn)
    log.info("dosya: output/%s (%.0f KB)", fn, len(img) / 1024)

    if a.dry:
        print(f"\n[DRY] kuyruğa KONMADI.\n  dosya : output/{fn}\n  url   : {url}\n"
              f"  başlık: {caption.splitlines()[0][:80]}")
        return

    # 2) tek commit + push
    subprocess.run(["git", "add", f"output/{fn}"], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-q", "-m", f"chore: özel gönderi görseli ({a.slug})"],
                   cwd=ROOT, check=True)
    # CI botu da aynı dala itiyor: önce uzaktakini al, sonra it. Yoksa ilk
    # çakışmada betik ölür ve görsel yarı yolda kalır.
    subprocess.run(["git", "pull", "--rebase", "--autostash", "-q", "origin", "main"],
                   cwd=ROOT, check=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=ROOT, check=True)
    log.info("GitHub'a itildi")

    # 3) URL canlı mı
    if not _canli_mi(url):
        sys.exit(f"URL canlı değil, kuyruğa KOYMADIM: {url}")
    log.info("URL canlı ✓")

    # 4) kuyruğa koy
    qid = queue_draft(url, caption, {"kart_baslik": a.slug}, a.template, a.pillar)
    print(f"\nONAY KUYRUĞUNDA → id={qid}\n  {url}\n"
          f"  kulups.com panelinden onaylayınca yayınlanır.")


if __name__ == "__main__":
    main()
