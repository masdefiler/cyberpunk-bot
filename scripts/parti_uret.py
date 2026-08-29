"""Elle küratörlü gönderi partisi — kart metni ile caption BİREBİR eşleşir.

Otomatik hat (src/pipeline.py) caption'ı LLM'e yazdırır; kartın yüzündeki metin
ise küratörlü havuzdan gelir. İkisi bazen aynı şeyi anlatmaz. Bu script parti
içeriğini elle bağlar: hangi şablon, hangi metin, hangi fotoğraf, hangi caption.

    python scripts/parti_uret.py                 # yalnız preview/ yazar
    python scripts/parti_uret.py --queue         # onay kuyruğuna gönderir
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config                    # noqa: E402
from src.card import compose              # noqa: E402
from src.caption import build_caption     # noqa: E402
from src.host import host_image           # noqa: E402
from src.pipeline import queue_draft, _slug   # noqa: E402

log = config.get_logger("parti")

# ---------------------------------------------------------------------------
#  PARTİ — Eylül 2026 sezon açılışı
#  (şablon, pick, pillar, foto, dosya-eki, caption, hashtag önerileri)
# ---------------------------------------------------------------------------
PARTI = [
    dict(
        tpl="sezon", pick=0, pillar="A", photo=None, slug="yeni-sezon",
        caption="""Eylül geldi, salonlar yeniden doldu.

Sezonun ilk haftası aslında bütün yılı belirliyor: kim hangi grupta, aidat hangi gün, antrenman hangi saatte. Bu üç soru ilk hafta netleşmezse sezon boyunca peşinden koşuyorsun.

kulups'te kadroları kurmak, aidat planını tanımlamak ve takvimi velilere göndermek bir akşamlık iş. Kurulumu biz yapıyoruz — sen sahaya bakıyorsun.

14 gün ücretsiz, kart bilgisi istemiyoruz.
kulups.com""",
        tags=["yenisezon", "sezonbasliyor", "kulupyonetimi", "basketbolkulubu", "altyapi"],
    ),
    dict(
        tpl="liste", pick=0, pillar="A", photo=None, slug="sezon-kontrol-listesi",
        caption="""Sezon başlamadan bitmesi gereken beş iş 📋

1. Kadroları ve grupları oluştur
2. Veli iletişim bilgilerini topla
3. Aidat tutarını ve tahsilat gününü belirle
4. Antrenman takvimini yayınla
5. Lisans evraklarını dijitale taşı

Bu beşi eylülde halleden kulüp, sezonun geri kalanında yönetimle değil sahayla uğraşıyor. Beşini de tek panelden yapabilirsin.

Kaydet, sezon başında lazım olacak.
kulups.com""",
        tags=["sezonhazirligi", "kulupyonetimi", "altyapi", "sporyonetimi", "kontrollistesi"],
    ),
    dict(
        tpl="karsi", pick=1, pillar="C", photo=None, slug="aidat-once-sonra",
        caption="""Aidat takibi, kulüplerin en çok vakit kaybettiği yer.

Kim ödedi, kim ödemedi belirsiz. Nakit elden geçiyor, makbuz kayboluyor. Ay sonu geldiğinde hesap tutmuyor ve kimse kimseyi suçlayamıyor — çünkü kayıt yok.

kulups'te ödeyen ve ödemeyen tek ekranda. Veli kartıyla ödüyor, kayıt otomatik düşüyor, makbuz anında telefonuna gidiyor. Aidat silinmiyor; iptal edilirse iptal olarak görünüyor. Yani defter her zaman kendini savunabiliyor.

kulups.com""",
        tags=["aidat", "onlinetahsilat", "kulupyonetimi", "sporkulubu", "muhasebe"],
    ),
    dict(
        tpl="rakam", pick=1, pillar="E", photo=None, slug="taktik-tahtasi-ucretsiz",
        caption="""Taktik tahtası ücretsiz. Gerçekten ücretsiz.

Üyelik yok, deneme süresi yok, "şu kadar çizimden sonra ücretli" yok. Aç, oyununu çiz, oynat, yazdır.

Basketbol, futbol ve voleybol sahaları hazır. Kurduğun oyunu kaydedip takımına gönderebilir, antrenmanda ekrandan oynatabilirsin.

Antrenör arkadaşını etiketle, işine yarar.
board.kulups.com""",
        tags=["taktiktahtasi", "antrenor", "basketbolantrenoru", "oyunkurma", "ucretsiz"],
    ),
    dict(
        tpl="kutlama", pick=1, pillar="D", photo="coach-player", slug="antrenor-sahaya-odaklanir",
        caption="""Bir antrenörün işi sahada.

Ama günün yarısı evrak peşinde geçiyor: lisans belgesi kimde, sağlık raporu geldi mi, hangi veliye ne söylenmişti. Sonra antrenman saati geliyor ve kafa hâlâ ofiste.

kulups evrakı, yoklamayı ve veli iletişimini sırtından alıyor. Belgeler dijital arşivde, duyuru tek tuşla herkeste, katılım tek dokunuşla işleniyor.

Koç işine bakar, çocuklar oyuna.
kulups.com""",
        tags=["antrenor", "basketbolantrenoru", "evraktakibi", "veliiletisimi", "sahakenari"],
    ),
    dict(
        tpl="poster", pick=0, pillar="D", photo="hoop-indoor", slug="veliler-sormadan-bilsin",
        caption=""""Haberim yoktu."

Kulüplerin en çok duyduğu cümle bu. Maç saati değişti, antrenman iptal oldu, aidat günü geldi — ama mesaj bir yerlerde kayboldu.

Velinin kendi paneli olunca bu cümle bitiyor. Program, duyuru, ödeme durumu ve çocuğunun gelişimi orada duruyor. Sormaya gerek kalmıyor, sen de aynı şeyi on kere anlatmıyorsun.

14 gün ücretsiz deneyebilirsin.
kulups.com""",
        tags=["veliiletisimi", "kulupyonetimi", "sporkulubu", "altyapi", "duyuru"],
    ),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", action="store_true", help="onay kuyruğuna gönder")
    args = ap.parse_args()

    prev = ROOT / "preview" / "parti"
    prev.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())

    hazir = []
    for i, item in enumerate(PARTI, 1):
        img, tpl, photo = compose({"konsept_basligi": item["slug"]},
                                  pillar=item["pillar"], template=item["tpl"],
                                  pick=item["pick"], photo_name=item.get("photo"))
        cap = build_caption({"caption_metin": item["caption"],
                             "hashtag_onerileri": item["tags"]})
        fn = f"{stamp}-{i}_{item['pillar']}_{_slug(item['slug'])}.jpg"
        (prev / fn).write_bytes(img)
        (prev / (fn[:-4] + ".txt")).write_text(cap, encoding="utf-8")
        hazir.append((item, fn, img, cap, tpl, photo))
        log.info("%d/%d hazır: %s (%s, foto=%s)", i, len(PARTI), fn, tpl, photo or "—")

    if not args.queue:
        print(f"\n{len(PARTI)} gönderi önizlemede → {prev}")
        return

    # 1) görselleri output/'a yaz (URL'ler buradan doğar)
    urls = []
    for item, fn, img, cap, tpl, _ in hazir:
        urls.append(host_image(img, fn))

    # 2) TEK commit ile GitHub'a it — kuyruğa gitmeden ÖNCE URL'ler canlı olmalı
    subprocess.run(["git", "add", "output"], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-q", "-m",
                    f"chore: {len(hazir)} yeni gönderi görseli ({stamp})"], cwd=ROOT, check=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=ROOT, check=True)
    log.info("görseller GitHub'a itildi (%d dosya)", len(hazir))

    # 3) kuyruğa koy
    for (item, fn, img, cap, tpl, _), url in zip(hazir, urls):
        qid = queue_draft(url, cap, {"kart_baslik": item["slug"]}, tpl, item["pillar"])
        log.info("kuyrukta: %s ← %s", qid, tpl)

    print(f"\n{len(hazir)} gönderi ONAY KUYRUĞUNDA — panelden onaylayınca yayınlanır.")


if __name__ == "__main__":
    main()
