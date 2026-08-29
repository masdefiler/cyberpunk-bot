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


# ---------------------------------------------------------------------------
#  PARTİ — Kulups Athletic (telefon kamerasıyla atletik test)
#  ⚠️ İDDİA DENETİMİ: dikey sıçrama ve uzun atlama kamerası PARK EDİLDİ
#  (katalogda gelistirme:true) — bu partide kameralı sıçrama VAAT EDİLMEZ.
#  Kamerayla gerçekten ölçülen 10 test: 20 m · 10 m · 5-10-5 · T-testi ·
#  şınav · mekik · squat · plank · tek ayak denge · öne uzanma.
# ---------------------------------------------------------------------------
ATL = {"domain": "athletic.kulups.com", "urun": "athletic"}

PARTI_ATLETIK = [
    dict(
        tpl="telefon", pillar="B", photo=None, slug="kronometreyi-cebine-koy",
        icerik=dict(
            headline="Kronometreyi cebine koy", emph="cebine",
            benefit="Kapıyı ekranda çiz, sporcu geçsin; süreyi kamera okusun.",
            extra=dict(ATL, kick="telefon kamerasıyla",
                       ekran={"test": "20 m sürat", "val": "3,42",
                              "unit": "sn", "alt": "Kapı geçildi"})),
        caption="""Kronometreyle sürat ölçmenin sorunu insan tepkisi.

Düdük ile parmak arasında birkaç yüzde birlik saniye var. 20 metre koşusunda bu fark, sporcunun bir sezonda kazandığı gelişimden büyük olabiliyor. Aynı koşuyu iki antrenör ölçse iki farklı süre çıkar.

Kulups Athletic'te telefonu bitiş çizgisine koyuyorsun, kapıyı ekranda parmağınla yerine sürüklüyorsun. Sporcu geçtiği anda süre duruyor — geçiş kareler arasından hesaplanıyor, tepki payı diye bir şey kalmıyor.

20 m, 10 m, 5-10-5 ve T-testi böyle ölçülüyor. Kronometre de duruyor; isteyen onu kullanır.

athletic.kulups.com""",
        tags=["atletiktest", "surattesti", "antrenor", "sporcugelisimi", "kondisyon"],
    ),
    dict(
        tpl="karsi", pillar="B", photo=None, slug="surat-olcumu-once-sonra",
        icerik=dict(
            headline="Sürat ölçümü", emph="", benefit="",
            extra=dict(ATL,
                       once=["Düdük ile parmak arasında gecikme",
                             "Kim ne zaman bastı tartışması",
                             "Aynı koşu, iki farklı süre"],
                       sonra=["Bitiş kapısını kamera okuyor",
                              "Geçiş anı kareler arasından",
                              "Aynı koşu, tek sonuç"])),
        caption="""Ölçüm güvenilir değilse gelişim de güvenilir değildir.

Sporcunun 20 metresi 3,55'ten 3,42'ye indi diyelim. Bu gerçek bir gelişim mi, yoksa kronometreye bu sefer daha erken mi basıldı? Ayıramıyorsan o veri işe yaramaz — grafiği çizersin ama neyi ölçtüğünü bilemezsin.

Kamera her seferinde aynı şeyi ölçer: gövde kapıyı ne zaman geçti. Ölçen kişi değişse de sonuç değişmez. Gelişim grafiği ancak o zaman bir şey anlatır.

athletic.kulups.com""",
        tags=["atletiktest", "olcum", "sporcugelisimi", "antrenorluk", "veri"],
    ),
    dict(
        tpl="liste", pillar="B", photo=None, slug="kamerayla-olculen-testler",
        icerik=dict(
            headline="Kamerayla ölçülen testler", emph="Kamerayla",
            benefit="",
            extra=dict(ATL, kick="Atletik test",
                       items=["20 m sürat · 10 m ilk adım",
                              "5-10-5 çeviklik · T-testi",
                              "Şınav · mekik · squat tekrarı",
                              "Plank süresi",
                              "Tek ayak denge · öne uzanma"])),
        caption="""Telefonun kamerasıyla ölçülen testler 📱

· 20 m sürat ve 10 m ilk adım
· 5-10-5 çeviklik ve T-testi
· Şınav, mekik, squat — sayan da telefon, geçerli tekrarı ayıran da
· Plank süresi
· Tek ayak denge ve öne uzanma

Hiçbiri zorunlu değil: her testte elle giriş açık. Mezuran ve kronometren varsa sayıyı yazıp geçersin, sonuç yine aynı yere düşer — sporcunun gelişim grafiğine.

athletic.kulups.com""",
        tags=["atletiktest", "kondisyon", "antrenmanplani", "sporcugelisimi", "olcum"],
    ),
    dict(
        tpl="rakam", pillar="B", photo=None, slug="video-cihazda-kalir",
        icerik=dict(
            headline="Video cihazda kalır", emph="kalır",
            benefit="Ölçüm cihazın içinde yapılır; kaydedilen tek şey sonuçtaki sayıdır.",
            extra=dict(ATL, num="0", unit="YÜKLEME")),
        caption="""Çocukların videosu hiçbir yere gitmiyor.

Bir uygulamaya çocuk videosu çektirmek ciddi bir sorumluluk. Biz o sorumluluğu almamayı seçtik: görüntü işleme tamamen telefonun içinde çalışıyor. Sunucuya giden tek şey ortaya çıkan sayı — 3,42 saniye, 24 tekrar, 41 saniye plank.

Saklanmayan veri sızmaz. En güvenli video, hiç yüklenmeyen videodur.

athletic.kulups.com""",
        tags=["kvkk", "veriguvenligi", "atletiktest", "sporcugelisimi", "cocukbasketbol"],
    ),
]

PARTILER = {"eylul": PARTI, "athletic": PARTI_ATLETIK}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", action="store_true", help="onay kuyruğuna gönder")
    ap.add_argument("--parti", default="eylul", choices=sorted(PARTILER),
                    help="hangi parti üretilsin")
    args = ap.parse_args()
    parti = PARTILER[args.parti]

    prev = ROOT / "preview" / "parti"
    prev.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())

    hazir = []
    for i, item in enumerate(parti, 1):
        img, tpl, photo = compose({"konsept_basligi": item["slug"]},
                                  pillar=item["pillar"], template=item["tpl"],
                                  pick=item.get("pick"), photo_name=item.get("photo"),
                                  icerik=item.get("icerik"))
        cap = build_caption({"caption_metin": item["caption"],
                             "hashtag_onerileri": item["tags"]})
        fn = f"{stamp}-{i}_{item['pillar']}_{_slug(item['slug'])}.jpg"
        (prev / fn).write_bytes(img)
        (prev / (fn[:-4] + ".txt")).write_text(cap, encoding="utf-8")
        hazir.append((item, fn, img, cap, tpl, photo))
        log.info("%d/%d hazır: %s (%s, foto=%s)", i, len(parti), fn, tpl, photo or "—")

    if not args.queue:
        print(f"\n{len(parti)} gönderi önizlemede → {prev}")
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
