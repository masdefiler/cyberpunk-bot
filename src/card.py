"""Gönderi görseli — "Saha Disiplini" tasarım felsefesi (design/PHILOSOPHY.md).

İlkeler (canvas-design skill'inden):
  · Az kelime, büyük ses: dev sıkışık tipografi (Big Shoulders) + fısıltı etiketler (Work Sans)
  · Tek vurgu kelimesi altın Instrument Serif italik — cümlenin kalbi
  · Fotoğraf ham girmez: lacivert DUOTONE — stok görünümü ölür, marka dokusu doğar
  · Saha çizgisi motifleri (yay/çember/köşe) düşük opaklıkta zemine işlenir
  · Geniş kenar payları; hiçbir öge taşmaz/çakışmaz; boşluk kazanılmış alandır

Karta basılan HER metin bu dosyadaki KÜRATÖRLÜ havuzdan gelir (imla garantili);
LLM yalnız Instagram caption'ı yazar, kartın yüzüne dokunamaz.

4 şablon: poster / court / duo / stat — pipeline aynı partide şablonu ve
fotoğrafı TEKRARLAMAZ (exclude parametreleri).
"""
from __future__ import annotations

import hashlib
import io
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from . import config

log = config.get_logger("card")
ROOT = Path(__file__).resolve().parent.parent
PHOTO_DIR = ROOT / "assets" / "photos"
FONT_DIR = ROOT / "assets" / "fonts"
LOGO_PATH = ROOT / "assets" / "logo.png"
URUN_DIR = ROOT / "assets" / "urun"     # ürün logoları (athletic, board, coach…)

S = 1080
M = 92          # küresel kenar payı — kimse bunun içine giremez

NAVY = (15, 23, 42)
NAVY_SOFT = (30, 41, 59)
PAPER = (241, 245, 249)     # kırık beyaz
GOLD = (212, 169, 79)
BLUE = (26, 86, 219)
MUTED = (148, 163, 184)
LIGHT_BG = (245, 247, 251)      # aydınlık zemin (kırık beyaz)
INK = (15, 23, 42)              # açık zeminde metin = lacivert
MUTED_D = (100, 116, 139)       # açık zeminde ikincil metin

TEMPLATES = ("poster", "court", "duo", "stat", "sistem",
             "isik", "parlak", "kutlama", "an",
             "sezon", "karsi", "rakam", "liste")
# telefon otomatik rotasyonda YOK: ürüne özel (athletic) kart, yalnız küratörlü
# partiden çağrılır — pipeline yanlışlıkla kulups.com markasıyla basmasın.
LIGHT_TPLS = {"isik", "parlak", "kutlama", "an"}

# ---------------------------------------------------------------------------
#  KÜRATÖRLÜ METİN HAVUZU — (başlık, fayda, vurgu-kelime)
#  Vurgu kelime başlıkta AYNEN geçmeli (küçük/büyük duyarsız eşleşir).
# ---------------------------------------------------------------------------
POOL: dict[str, list[tuple[str, str, str]]] = {
    "A": [
        ("Yoklama defteri emekli oldu",
         "Katılım tek dokunuşla işlenir, devamsızlık raporu kendiliğinden çıkar.", "emekli"),
        ("Program artık kaybolmuyor",
         "Antrenman ve maç takvimi herkesin panelinde; değişiklik anında bildirilir.", "kaybolmuyor"),
        ("Bütün kadro tek ekranda",
         "Sporcu kartları, forma numaraları ve veli bilgileri hep elinizin altında.", "tek"),
    ],
    "B": [
        ("Gelişimi hissetme, ölç",
         "Boy, kilo ve performans ölçümleri; aylar içindeki ilerleme grafikte.", "ölç"),
        ("Her sporcuya kendi programı",
         "Bireysel gelişim programını ata; sporcu kendi panelinden takip etsin.", "kendi"),
        ("Sakatlık takibi kayıt altında",
         "Sakatlık geçmişi ve dönüş tarihi tek yerde; tahmine yer yok.", "kayıt"),
    ],
    "C": [
        ("Aidat kim ödedi, kim ödemedi?",
         "Tüm ödemeler tek ekranda; veliye kartla ödeme bağlantısı gider.", "ödedi"),
        ("Tahsilatı kovalamayı bırak",
         "iyzico ile kartla tahsilat — para doğrudan kulübün hesabına geçer.", "bırak"),
        ("Ay sonu hesabı dert değil",
         "Kim ödedi, kim gecikti: durum her an güncel, rapor hazır.", "dert"),
    ],
    "D": [
        ("Veliler sormadan bilsin",
         "Program, duyuru ve gelişim veli panelinde; 'haberim yoktu' devri bitti.", "sormadan"),
        ("Evrak klasörleri rafta kalsın",
         "Lisans ve belgeler dijital arşivde; aradığınız evrak iki saniyede önünüzde.", "rafta"),
        ("Duyuru herkese aynı anda",
         "Tek duyuru; bütün veliler ve sporcular anında haberdar.", "aynı"),
    ],
    "E": [
        ("Oyununu çiz, sahaya taşı",
         "Sürükle-bırak taktik tahtası: çiz, oynat, yazdır.", "çiz"),
        ("Taktik tahtası hep ücretsiz",
         "Antrenörlere üyeliksiz ve sınırsız; hemen çizmeye başla.", "ücretsiz"),
        ("Hücumu kâğıtta bırakma",
         "Kurduğun oyunu kaydet, takımına gönder, antrenmanda oynat.", "kâğıtta"),
    ],
}

# Tüm havuz KAPALI SALON çekimleridir (kullanıcı tercihi, 2026-07-22).
PILLAR_PHOTOS = {
    "A": ["coach-draw", "timeout", "huddle"],
    "B": ["indoor-shot", "coach-player", "game"],
    "C": ["huddle", "timeout", "coach-board"],
    "D": ["coach-player", "coach-board", "coach-draw"],
    "E": ["coach-draw", "coach-board", "game"],
}

# "sistem" şablonu için genel tanıtım metinleri (pillar'dan bağımsız)
GENEL: list[tuple[str, str, str]] = [
    ("Kulübünün tüm yönetimi tek panelde",
     "Yoklama, aidat, takvim, veli iletişimi ve taktik tahtası — hepsi bir arada.", "tek"),
    ("Kağıt, Excel, WhatsApp devri bitti",
     "Kulüp yönetiminin tamamı tek uygulamada; kurulum bizden.", "bitti"),
]
SISTEM_OZELLIKLER = ["Yoklama", "Aidat & Tahsilat", "Maç Takvimi",
                     "Taktik Tahtası", "Veli Portalı", "Evrak & Kayıt"]

# Aydınlık/duygu kartları için MUTLU havuz (kutlama + an şablonları buradan konuşur)
MUTLU: list[tuple[str, str, str]] = [
    ("Velisi mutlu, sporcusu mutlu",
     "Herkes gelişmeleri kendi panelinde görür; kimse sormak zorunda kalmaz.", "mutlu"),
    ("Antrenör sahaya odaklanır",
     "Evrak işleri sistemde; koç işine, çocuklar oyuna bakar.", "sahaya"),
    ("Kulüpte herkesin yüzü gülüyor",
     "Düzen kurulunca stres biter: yoklama, aidat, iletişim rayında.", "gülüyor"),
    ("Antrenman günü en sevilen gün",
     "Program belli, saat belli, herkes hazır — geriye oyun kalır.", "sevilen"),
]
# Aydınlık kartlarda kullanılacak fotoğraflar (doğal renk, sıcak grade)
MOOD_PHOTOS = ["happy-run", "happy-gym", "coach-player", "indoor-shot"]


# ---------------------------------------------------------------------------
#  Fontlar (repo içi — Actions'ta da aynı)
# ---------------------------------------------------------------------------
def _font(name: str, size: int):
    p = FONT_DIR / name
    try:
        return ImageFont.truetype(str(p), size)
    except Exception:
        return ImageFont.load_default()


def F_DISPLAY(sz):  # dev başlık — sıkışık gövde
    return _font("BigShoulders-Bold.ttf", sz)


def F_ACCENT(sz):   # altın vurgu — italik serif
    return _font("InstrumentSerif-Italic.ttf", sz)


def F_TEXT(sz, bold=False):
    return _font("WorkSans-Bold.ttf" if bold else "WorkSans-Regular.ttf", sz)


def _lh(f):
    a, d = f.getmetrics()
    return a + d


# ---------------------------------------------------------------------------
#  Karışık-font başlık: vurgu kelime altın serif italik, kalan dev display
# ---------------------------------------------------------------------------
def _mixed_wrap(d, text: str, emph: str, size: int, max_w: int, max_lines: int):
    """Kelimeleri (font, genişlik) ile ölçerek satırlara böler; sığana dek küçülür."""
    for sz in range(size, int(size * 0.5), -6):
        df, af = F_DISPLAY(sz), F_ACCENT(int(sz * 0.94))
        words = []
        for w in text.split():
            emp = emph and emph.lower() in w.lower()
            f = af if emp else df
            words.append((w, emp, d.textlength(w + " ", font=f)))
        lines, cur, cw = [], [], 0.0
        for w, emp, ww in words:
            if cw + ww > max_w and cur:
                lines.append(cur)
                cur, cw = [], 0.0
            cur.append((w, emp))
            cw += ww
        if cur:
            lines.append(cur)
        if len(lines) <= max_lines:
            return sz, lines
    return int(size * 0.5), lines  # son deneme ne verdiyse


def _draw_mixed(d, lines, sz, x, y, *, align="left", width=0, gap=1.04, ink=None):
    df, af = F_DISPLAY(sz), F_ACCENT(int(sz * 0.94))
    lh = int(_lh(df) * gap)
    for ln in lines:
        total = sum(d.textlength(w + " ", font=(af if e else df)) for w, e in ln)
        cx = x + (width - total) / 2 if align == "center" else x
        for w, e in ln:
            f = af if e else df
            # serif italiği display satırıyla taban hizasına oturt
            oy = _lh(df) - _lh(f) if e else 0
            d.text((cx, y + oy), w, font=f, fill=GOLD if e else (ink or PAPER))
            cx += d.textlength(w + " ", font=f)
        y += lh
    return y


def _fit_plain(d, text, size, max_w, max_lines, *, bold=False):
    for sz in range(size, 14, -2):
        f = F_TEXT(sz, bold)
        words, lines, cur = text.split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if d.textlength(t, font=f) <= max_w or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) <= max_lines:
            return f, lines
    return f, lines[:max_lines]


# ---------------------------------------------------------------------------
#  Fotoğraf: lacivert duotone
# ---------------------------------------------------------------------------
def _duotone(img: Image.Image) -> Image.Image:
    g = ImageOps.autocontrast(img.convert("L"), cutoff=1)
    return ImageOps.colorize(g, black=(8, 13, 28), white=(214, 224, 240),
                             mid=(44, 62, 96)).convert("RGB")


def _warm(img: Image.Image) -> Image.Image:
    """Aydınlık kartlar için doğal renk: kontrast + hafif sıcaklık/doygunluk."""
    from PIL import ImageEnhance
    im = ImageOps.autocontrast(img.convert("RGB"), cutoff=1)
    im = ImageEnhance.Color(im).enhance(1.12)
    im = ImageEnhance.Brightness(im).enhance(1.04)
    return ImageEnhance.Contrast(im).enhance(1.05)


def _cover(img, w, h, focus=0.32):
    r = max(w / img.width, h / img.height)
    im = img.resize((max(w, int(img.width * r) + 1), max(h, int(img.height * r) + 1)), Image.LANCZOS)
    x = (im.width - w) // 2
    y = int((im.height - h) * focus)
    return im.crop((x, y, x + w, y + h))


def _fade_bottom(img, start=0.42, top_a=0.04, bot_a=0.94):
    w, h = img.size
    mask = Image.new("L", (1, h))
    px = mask.load()
    for y in range(h):
        t = 0.0 if y < h * start else (y - h * start) / max(1.0, h * (1 - start))
        px[0, y] = int(255 * min(1.0, top_a + (bot_a - top_a) * (t ** 1.25)))
    return Image.composite(Image.new("RGB", (w, h), NAVY), img, mask.resize((w, h)))


# ---------------------------------------------------------------------------
#  Saha motifleri + marka kilidi
# ---------------------------------------------------------------------------
def _court_motif(d: ImageDraw.ImageDraw, ox: float, oy: float, u: float,
                 alpha=46, stroke=3):
    """GERÇEK yarım saha geometrisi, 0..100 birim uzayında (pota üstte).

    Oranlar üründeki taktik tahtasıyla aynı: boyalı alan 34-66 / 3-34,
    serbest atış çemberi (50,34) r9, çember (50,10) r2.3 + panya,
    kısa devre yayı r5.5, üç sayı = köşe çizgileri x=8/92 (y 3→22) + r42 yay,
    orta saha çizgisi y=97 + merkez çemberin üst yarısı.
    """
    col = GOLD + (alpha,)
    P = lambda x, y: (ox + x * u, oy + y * u)
    box = lambda cx, cy, r: [ox + (cx - r) * u, oy + (cy - r) * u,
                             ox + (cx + r) * u, oy + (cy + r) * u]
    # baseline
    d.line([*P(3, 3), *P(97, 3)], fill=col, width=stroke)
    # boyalı alan + serbest atış çemberi
    d.rectangle([*P(34, 3), *P(66, 34)], outline=col, width=stroke)
    d.ellipse(box(50, 34, 9), outline=col, width=stroke)
    # panya + çember + kısa devre yayı
    d.line([*P(42.5, 6.2), *P(57.5, 6.2)], fill=col, width=stroke)
    d.ellipse(box(50, 10, 2.3), outline=col, width=stroke)
    d.arc(box(50, 10, 5.5), 0, 180, fill=col, width=stroke)
    # üç sayı: köşe çizgileri + yay (uçları köşe çizgilerine oturur: ~16°/164°)
    d.line([*P(8, 3), *P(8, 22)], fill=col, width=stroke)
    d.line([*P(92, 3), *P(92, 22)], fill=col, width=stroke)
    d.arc(box(50, 10, 42), 16, 164, fill=col, width=stroke)
    # orta saha: çizgi + merkez çemberin üst yarısı
    d.line([*P(3, 97), *P(97, 97)], fill=col, width=stroke)
    d.arc(box(50, 97, 10), 180, 360, fill=col, width=stroke)


def _court_motif_col(d, ox, oy, u, rgb, alpha=30, stroke=3):
    """_court_motif ile aynı geometri, istenen renkte (açık tema için lacivert)."""
    global GOLD
    _g = GOLD
    try:
        GOLD = rgb          # motif fonksiyonu GOLD kullanır; geçici değiştir
        _court_motif(d, ox, oy, u, alpha=alpha, stroke=stroke)
    finally:
        GOLD = _g


def _court_bg(base: Image.Image, *, u: float, ox: float, oy: float,
              alpha=46, stroke=3):
    ov = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    _court_motif(ImageDraw.Draw(ov), ox, oy, u, alpha=alpha, stroke=stroke)
    base.alpha_composite(ov)


def _brand(base: Image.Image, x: int, y: int, *, dark_bg: bool = True, chip: int = 74,
           urun: str | None = None):
    """Beyaz çipte logo + 'kulups' — ürün verilirse ürün logosu + altın ürün adı."""
    d = ImageDraw.Draw(base)
    d.rounded_rectangle([x, y, x + chip, y + chip], radius=int(chip * 0.28),
                        fill=(255, 255, 255),
                        outline=None if dark_bg else (203, 213, 225),
                        width=0 if dark_bg else 2)
    path = (URUN_DIR / f"{urun}.png") if urun else LOGO_PATH
    if not path.exists():
        path = LOGO_PATH
    if path.exists():
        lg = Image.open(path).convert("RGBA")
        k = int(chip * (0.74 if urun else 0.68))
        r = k / max(lg.size)
        lg = lg.resize((max(1, int(lg.width * r)), max(1, int(lg.height * r))), Image.LANCZOS)
        base.alpha_composite(lg, (x + (chip - lg.width) // 2, y + (chip - lg.height) // 2))
    wf = F_TEXT(34, bold=True)
    d = ImageDraw.Draw(base)
    tx = x + chip + 16
    ty = y + (chip - _lh(wf)) // 2
    d.text((tx, ty), "kulups", font=wf, fill=PAPER if dark_bg else INK)
    if urun:
        uf = F_TEXT(34, bold=True)
        d.text((tx + d.textlength("kulups ", font=wf), ty), urun, font=uf, fill=GOLD)


def _footer(d, y, *, center=False, x=M, dark=True, domain="kulups.com"):
    """Alt satır: alan adı — nokta — 14 gün ücretsiz (iki temada da)."""
    f1, f2 = F_TEXT(30, True), F_TEXT(28)
    t1, t2 = domain, "14 gün ücretsiz"
    w = d.textlength(t1, font=f1) + 30 + d.textlength(t2, font=f2)
    if center:
        x = (S - w) / 2
    d.text((x, y), t1, font=f1, fill=GOLD if dark else BLUE)
    cx = x + d.textlength(t1, font=f1) + 12
    d.ellipse([cx, y + 14, cx + 6, y + 20], fill=MUTED if dark else MUTED_D)
    d.text((cx + 18, y + 1), t2, font=f2, fill=MUTED if dark else MUTED_D)


# ===========================================================================
#  ŞABLON: poster — tam duotone foto, dev başlık altta
# ===========================================================================
def _t_poster(photo, headline, benefit, emph, extra=None):
    dom = (extra or {}).get("domain", "kulups.com")
    urn = (extra or {}).get("urun")
    im = _fade_bottom(_duotone(_cover(photo, S, S)))
    base = im.convert("RGBA")
    _court_bg(base, u=S * 0.0068, ox=S * 0.42, oy=S * 0.045, alpha=34, stroke=2)
    d = ImageDraw.Draw(base)

    maxw = S - 2 * M
    sz, lines = _mixed_wrap(d, headline, emph, 118, maxw, 3)
    bf, bl = _fit_plain(d, benefit, 32, maxw - 40, 2)
    foot_y = S - M - 34
    ben_h = (_lh(bf) + 8) * len(bl)
    head_h = int(_lh(F_DISPLAY(sz)) * 1.04) * len(lines)
    y0 = foot_y - 26 - ben_h - 22 - head_h

    d.line([M, y0 - 26, M + 110, y0 - 26], fill=GOLD, width=5)
    y = _draw_mixed(d, lines, sz, M, y0)
    y += 20
    for ln in bl:
        d.text((M, y), ln, font=bf, fill=(203, 213, 225))
        y += _lh(bf) + 8
    _footer(d, foot_y, domain=dom)
    _brand(base, M, M - 18, urun=urn)
    return base.convert("RGB")


# ===========================================================================
#  ŞABLON: court — düz zemin, merkez tipografi, saha motifi
# ===========================================================================
def _t_court(photo, headline, benefit, emph):
    base = Image.new("RGBA", (S, S), NAVY + (255,))
    cu = S * 0.0115
    _court_bg(base, u=cu, ox=(S - 100 * cu) / 2, oy=S * 0.1, alpha=44, stroke=3)
    d = ImageDraw.Draw(base)

    maxw = S - 2 * M
    sz, lines = _mixed_wrap(d, headline, emph, 128, maxw, 3)
    bf, bl = _fit_plain(d, benefit, 33, maxw - 120, 2)
    head_h = int(_lh(F_DISPLAY(sz)) * 1.05) * len(lines)
    ben_h = (_lh(bf) + 9) * len(bl)
    pill_h = 78
    total = head_h + 30 + ben_h + 44 + pill_h
    y = (S - total) // 2 + 26

    kf = F_TEXT(26, True)
    kick = "Kulüp yönetim sistemi"
    d.text(((S - d.textlength(kick, font=kf)) / 2, y - 66), kick, font=kf, fill=MUTED)
    y = _draw_mixed(d, lines, sz, 0, y, align="center", width=S)
    y += 26
    for ln in bl:
        d.text(((S - d.textlength(ln, font=bf)) / 2, y), ln, font=bf, fill=(203, 213, 225))
        y += _lh(bf) + 9

    pf = F_TEXT(30, True)
    pt = "14 gün ücretsiz dene"
    pw = d.textlength(pt, font=pf) + 76
    px = (S - pw) / 2
    py = y + 40
    d.rounded_rectangle([px, py, px + pw, py + pill_h], radius=pill_h // 2, fill=BLUE)
    d.text((px + 38, py + (pill_h - _lh(pf)) // 2), pt, font=pf, fill=(255, 255, 255))
    df = F_TEXT(27, True)
    d.text(((S - d.textlength("kulups.com", font=df)) / 2, S - M - 30), "kulups.com", font=df, fill=GOLD)
    _brand(base, (S - 74 - 16 - int(d.textlength("kulups", font=F_TEXT(34, True)))) // 2, M - 22)
    return base.convert("RGB")


# ===========================================================================
#  ŞABLON: duo — sol duotone foto, sağ lacivert kolon
# ===========================================================================
def _t_duo(photo, headline, benefit, emph):
    base = Image.new("RGBA", (S, S), NAVY + (255,))
    cut = int(S * 0.52)
    base.paste(_duotone(_cover(photo, cut, S, focus=0.24)), (0, 0))
    d = ImageDraw.Draw(base)
    d.rectangle([cut, 0, cut + 4, S], fill=GOLD)

    du = (S - cut) * 0.0086
    _court_bg(base, u=du, ox=cut + 26, oy=S * 0.58, alpha=40, stroke=2)
    d = ImageDraw.Draw(base)

    x = cut + 56
    maxw = S - x - M
    sz, lines = _mixed_wrap(d, headline, emph, 96, maxw, 4)
    bf, bl = _fit_plain(d, benefit, 30, maxw, 3)
    head_h = int(_lh(F_DISPLAY(sz)) * 1.05) * len(lines)
    ben_h = (_lh(bf) + 8) * len(bl)
    total = head_h + 26 + ben_h
    y = (S - total) // 2 - 6

    d.line([x, y - 24, x + 96, y - 24], fill=GOLD, width=5)
    y = _draw_mixed(d, lines, sz, x, y)
    y += 20
    for ln in bl:
        d.text((x, y), ln, font=bf, fill=(203, 213, 225))
        y += _lh(bf) + 8
    _footer(d, S - M - 32, x=x)
    _brand(base, x, M - 18)
    return base.convert("RGB")


# ===========================================================================
#  ŞABLON: stat — somut poetry: vurgu kelime DEV, gerisi fısıltı
# ===========================================================================
def _t_stat(photo, headline, benefit, emph):
    base = Image.new("RGBA", (S, S), NAVY + (255,))
    su = S * 0.0104
    _court_bg(base, u=su, ox=(S - 100 * su) / 2, oy=S * 0.14, alpha=36, stroke=2)
    d = ImageDraw.Draw(base)
    d.rectangle([M - 26, M - 26, S - M + 26, S - M + 26], outline=NAVY_SOFT, width=2)

    # kelime sırası KORUNUR: vurgu-öncesi üstte, DEV vurgu ortada, kalanı altta
    words = headline.split()
    idx = next((i for i, w in enumerate(words) if emph and emph.lower() in w.lower()),
               len(words) - 1)
    big = words[idx]
    before = " ".join(words[:idx])
    after = " ".join(words[idx + 1:])

    bsz = 300
    while d.textlength(big, font=F_ACCENT(bsz)) > S - 2 * M and bsz > 90:
        bsz -= 10
    bf_big = F_ACCENT(bsz)
    bw = d.textlength(big, font=bf_big)
    bh = _lh(bf_big)
    by = (S - bh) // 2 - 40

    sf = F_DISPLAY(64)
    if before:
        d.text(((S - d.textlength(before, font=sf)) / 2, by - _lh(sf) - 6), before, font=sf, fill=PAPER)
    d.text(((S - bw) / 2, by), big, font=bf_big, fill=GOLD)
    yy = by + bh + 4
    if after:
        d.text(((S - d.textlength(after, font=sf)) / 2, yy), after, font=sf, fill=PAPER)
        yy += _lh(sf) + 10

    bff, bbl = _fit_plain(d, benefit, 31, S - 2 * M - 100, 2)
    yy += 24
    for ln in bbl:
        d.text(((S - d.textlength(ln, font=bff)) / 2, yy), ln, font=bff, fill=(203, 213, 225))
        yy += _lh(bff) + 8

    nf = F_TEXT(24, True)
    d.text((M, M - 6), "No. " + hashlib.sha1(headline.encode()).hexdigest()[:2].upper(),
           font=nf, fill=MUTED)
    _footer(d, S - M - 30, center=True)
    _brand(base, S - M - 74 - 16 - int(d.textlength("kulups", font=F_TEXT(34, True))), M - 22)
    return base.convert("RGB")


# ===========================================================================
#  ŞABLON: sistem — genel tanıtım: başlık + özellik rozetleri + CTA
# ===========================================================================
def _t_sistem(photo, headline, benefit, emph):
    base = Image.new("RGBA", (S, S), NAVY + (255,))
    cu = S * 0.0115
    _court_bg(base, u=cu, ox=(S - 100 * cu) / 2, oy=S * 0.3, alpha=38, stroke=3)
    d = ImageDraw.Draw(base)

    maxw = S - 2 * M
    kf = F_TEXT(26, True)
    kick = "Kulüp yönetim sistemi"
    d.text(((S - d.textlength(kick, font=kf)) / 2, M + 96), kick, font=kf, fill=MUTED)

    sz, lines = _mixed_wrap(d, headline, emph, 108, maxw, 2)
    y = _draw_mixed(d, lines, sz, 0, M + 148, align="center", width=S)

    bf, bl = _fit_plain(d, benefit, 30, maxw - 120, 2)
    y += 14
    for ln in bl:
        d.text(((S - d.textlength(ln, font=bf)) / 2, y), ln, font=bf, fill=(203, 213, 225))
        y += _lh(bf) + 8

    # özellik rozetleri: 2 sütun × 3 satır, altın nokta işareti (font glifine güvenme)
    rf = F_TEXT(28, True)
    cols, gap_x, gap_y, rh = 2, 26, 14, 64
    rw = (S - 2 * M - gap_x) / cols
    gy = y + 34
    for i, oz in enumerate(SISTEM_OZELLIKLER):
        cx = M + (i % cols) * (rw + gap_x)
        cy = gy + (i // cols) * (rh + gap_y)
        d.rounded_rectangle([cx, cy, cx + rw, cy + rh], radius=16,
                            fill=(24, 34, 56), outline=(51, 65, 85), width=2)
        d.ellipse([cx + 26, cy + rh / 2 - 7, cx + 40, cy + rh / 2 + 7], fill=GOLD)
        d.text((cx + 58, cy + (rh - _lh(rf)) // 2), oz, font=rf, fill=PAPER)

    py = gy + 3 * (rh + gap_y) + 18
    pf = F_TEXT(30, True)
    pt = "14 gün ücretsiz dene"
    pw = d.textlength(pt, font=pf) + 76
    ph = 74
    px = (S - pw) / 2
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=ph // 2, fill=BLUE)
    d.text((px + 38, py + (ph - _lh(pf)) // 2), pt, font=pf, fill=(255, 255, 255))
    df = F_TEXT(27, True)
    d.text(((S - d.textlength("kulups.com", font=df)) / 2, py + ph + 20), "kulups.com", font=df, fill=GOLD)
    _brand(base, (S - 74 - 16 - int(d.textlength("kulups", font=F_TEXT(34, True)))) // 2, M - 30)
    return base.convert("RGB")


# ===========================================================================
#  AYDINLIK AİLE — isik / parlak / kutlama / an
# ===========================================================================
def _t_isik(photo, headline, benefit, emph):
    """Açık zemin, merkez tipografi — court'un gündüz ikizi."""
    base = Image.new("RGBA", (S, S), LIGHT_BG + (255,))
    cu = S * 0.0115
    ov = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    _court_motif_col(od, (S - 100 * cu) / 2, S * 0.12, cu, NAVY, alpha=26, stroke=3)
    base.alpha_composite(ov)
    d = ImageDraw.Draw(base)

    maxw = S - 2 * M
    kf = F_TEXT(26, True)
    kick = "Kulüp yönetim sistemi"
    d.text(((S - d.textlength(kick, font=kf)) / 2, 236), kick, font=kf, fill=MUTED_D)

    sz, lines = _mixed_wrap(d, headline, emph, 124, maxw, 3)
    bf, bl = _fit_plain(d, benefit, 32, maxw - 120, 2)
    head_h = int(_lh(F_DISPLAY(sz)) * 1.05) * len(lines)
    y = 300
    y = _draw_mixed(d, lines, sz, 0, y, align="center", width=S, ink=INK)
    y += 24
    for ln in bl:
        d.text(((S - d.textlength(ln, font=bf)) / 2, y), ln, font=bf, fill=MUTED_D)
        y += _lh(bf) + 9

    pf = F_TEXT(30, True)
    pt = "14 gün ücretsiz dene"
    pw = d.textlength(pt, font=pf) + 76
    ph = 76
    px = (S - pw) / 2
    py = y + 42
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=ph // 2, fill=BLUE)
    d.text((px + 38, py + (ph - _lh(pf)) // 2), pt, font=pf, fill=(255, 255, 255))
    _footer(d, S - M - 30, center=True, dark=False)
    _brand(base, (S - 74 - 16 - int(d.textlength("kulups", font=F_TEXT(34, True)))) // 2, M - 22, dark_bg=False)
    return base.convert("RGB")


def _t_parlak(photo, headline, benefit, emph):
    """Tam kanvas doğal renk foto + beyaza eriyen alt + lacivert başlık."""
    im = _cover(_warm(photo), S, S)
    w, h = im.size
    mask = Image.new("L", (1, h))
    px_ = mask.load()
    for yy in range(h):
        t = 0.0 if yy < h * 0.30 else (yy - h * 0.30) / (h * 0.44)
        px_[0, yy] = int(255 * min(1.0, t ** 1.1))
    im = Image.composite(Image.new("RGB", (S, S), LIGHT_BG), im, mask.resize((S, S)))
    base = im.convert("RGBA")
    d = ImageDraw.Draw(base)

    maxw = S - 2 * M
    sz, lines = _mixed_wrap(d, headline, emph, 112, maxw, 3)
    bf, bl = _fit_plain(d, benefit, 31, maxw - 60, 2)
    foot_y = S - M + 6
    ben_h = (_lh(bf) + 8) * len(bl)
    head_h = int(_lh(F_DISPLAY(sz)) * 1.04) * len(lines)
    y0 = foot_y - 30 - ben_h - 20 - head_h

    d.line([M, y0 - 24, M + 110, y0 - 24], fill=GOLD, width=5)
    y = _draw_mixed(d, lines, sz, M, y0, ink=INK)
    y += 18
    for ln in bl:
        d.text((M, y), ln, font=bf, fill=MUTED_D)
        y += _lh(bf) + 8
    _footer(d, foot_y, dark=False)
    _brand_pill(base, M, M - 22)
    return base.convert("RGB")


def _t_kutlama(photo, headline, benefit, emph):
    """Üstte mutlu foto (doğal renk), altta beyaz panel — altın ayrım çizgisi."""
    base = Image.new("RGBA", (S, S), LIGHT_BG + (255,))
    cut = int(S * 0.56)
    base.paste(_cover(_warm(photo), S, cut, focus=0.3), (0, 0))
    d = ImageDraw.Draw(base)
    d.rectangle([0, cut, S, cut + 5], fill=GOLD)

    x = M
    maxw = S - 2 * M
    sz, lines = _mixed_wrap(d, headline, emph, 92, maxw, 2)
    bf, bl = _fit_plain(d, benefit, 30, maxw, 1)   # tek satır — footer'la çakışma imkânsız
    y = cut + 60
    y = _draw_mixed(d, lines, sz, x, y, ink=INK)
    y += 16
    for ln in bl:
        d.text((x, y), ln, font=bf, fill=MUTED_D)
        y += _lh(bf) + 8
    _footer(d, S - M - 24, x=x, dark=False)
    _brand_pill(base, M, M - 30)
    return base.convert("RGB")


def _t_an(photo, headline, benefit, emph):
    """Polaroid 'an' kartı: açık zemin, çerçeveli eğik foto + merkez başlık."""
    base = Image.new("RGBA", (S, S), LIGHT_BG + (255,))
    cu = S * 0.009
    ov = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    _court_motif_col(ImageDraw.Draw(ov), S * 0.3, S * 0.5, cu, NAVY, alpha=20, stroke=2)
    base.alpha_composite(ov)

    d = ImageDraw.Draw(base)
    maxw = S - 2 * M
    sz, lines = _mixed_wrap(d, headline, emph, 88, maxw, 2)
    bf, bl = _fit_plain(d, benefit, 29, maxw - 80, 2)

    # önce metin bloğunu alta yerleştir, polaroid KALAN yüksekliğe ölçeklensin
    foot_y = S - M - 22
    head_h = int(_lh(F_DISPLAY(sz)) * 1.04) * len(lines)
    ben_h = (_lh(bf) + 7) * len(bl)
    text_y = foot_y - 40 - ben_h - 12 - head_h
    top = 132
    box_h = max(300, text_y - 34 - top)
    phh = int(min(520, box_h))
    pw = int(phh * 470 / 520)

    pol = Image.new("RGBA", (pw, phh), (255, 255, 255, 255))
    pol.paste(_cover(_warm(photo), pw - 44, phh - 110, focus=0.28), (22, 22))
    pol = pol.rotate(-3.4, expand=True, resample=Image.BICUBIC)
    sh = Image.new("RGBA", pol.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([10, 16, pol.size[0] - 4, pol.size[1] - 2], 12, fill=(15, 23, 42, 60))
    sh = sh.filter(ImageFilter.GaussianBlur(14))
    px_ = (S - pol.size[0]) // 2
    py_ = int(top + (box_h - pol.size[1]) / 2)
    base.alpha_composite(sh, (px_, py_ + 14))
    base.alpha_composite(pol, (px_, py_))

    d = ImageDraw.Draw(base)
    y = _draw_mixed(d, lines, sz, 0, text_y, align="center", width=S, ink=INK)
    y += 12
    for ln in bl:
        d.text(((S - d.textlength(ln, font=bf)) / 2, y), ln, font=bf, fill=MUTED_D)
        y += _lh(bf) + 7
    _footer(d, foot_y, center=True, dark=False)
    _brand(base, M, M - 34, dark_bg=False)
    return base.convert("RGB")


# ===========================================================================
#  v6 — TİPOGRAFİK AİLE: sezon / karsi / rakam / liste
#  Fotoğraf kullanmaz; feed'de fotoğraflı kartların arasına "nefes" koyar.
# ===========================================================================
NOPHOTO_TPLS = {"sezon", "karsi", "rakam", "liste", "telefon"}
# extra sözlüğünü kabul eden şablonlar (imzası 5 argümanlı)
EXTRA_TPLS = NOPHOTO_TPLS | {"poster"}


def _ust(s: str) -> str:
    """Türkçe büyütme — Python'un upper()'ı 'i'yi 'I' yapar, doğrusu 'İ'."""
    return s.replace("i", "İ").replace("ı", "I").upper()


def _check(d, cx, cy, r, col, w=5):
    """✓ glifi hiçbir fontta YOK → tik'i çizgiyle çiziyoruz."""
    d.line([(cx - r * 0.42, cy + r * 0.02), (cx - r * 0.10, cy + r * 0.36),
            (cx + r * 0.46, cy - r * 0.40)], fill=col, width=w, joint="curve")


def _cross(d, cx, cy, r, col, w=5):
    d.line([(cx - r * 0.34, cy - r * 0.34), (cx + r * 0.34, cy + r * 0.34)], fill=col, width=w)
    d.line([(cx - r * 0.34, cy + r * 0.34), (cx + r * 0.34, cy - r * 0.34)], fill=col, width=w)


def _brand_pill(base: Image.Image, x: int, y: int, *, chip: int = 68, urun: str | None = None):
    """Fotoğraf üstünde okunaklı marka kilidi: tüm lockup beyaz hapta."""
    d = ImageDraw.Draw(base)
    wf = F_TEXT(31, bold=True)
    kelime = f"kulups {urun}" if urun else "kulups"
    tw = d.textlength(kelime, font=wf)
    pad = 14
    w = pad + chip + 13 + tw + 26
    h = chip + 2 * pad
    d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=(255, 255, 255))
    path = (URUN_DIR / f"{urun}.png") if urun else LOGO_PATH
    if not path.exists():
        path = LOGO_PATH
    if path.exists():
        lg = Image.open(path).convert("RGBA")
        k = int(chip * 0.94)
        r = k / max(lg.size)
        lg = lg.resize((max(1, int(lg.width * r)), max(1, int(lg.height * r))), Image.LANCZOS)
        base.alpha_composite(lg, (int(x + pad + (chip - lg.width) / 2), int(y + pad + (chip - lg.height) / 2)))
    d = ImageDraw.Draw(base)
    tx = x + pad + chip + 13
    ty = y + (h - _lh(wf)) / 2
    d.text((tx, ty), "kulups", font=wf, fill=INK)
    if urun:
        d.text((tx + d.textlength("kulups ", font=wf), ty), urun, font=wf, fill=(150, 110, 30))


def _kicker(d, text, y, *, center=True, x=M, col=None, size=26, track=4):
    """Harf aralığı açılmış küçük etiket (ALL CAPS)."""
    f = F_TEXT(size, True)
    t = _ust(text)
    w = sum(d.textlength(c, font=f) for c in t) + track * (len(t) - 1)
    cx = (S - w) / 2 if center else x
    for c in t:
        d.text((cx, y), c, font=f, fill=col or MUTED)
        cx += d.textlength(c, font=f) + track
    return w


# --- v6 metin havuzları -----------------------------------------------------
SEZON: list[tuple[str, str, str, list[str]]] = [
    ("Yeni sezon burada başlar",
     "Kayıt, kadro ve aidat planı daha ilk hafta otursun.", "başlar",
     ["Sporcu kaydı", "Kadro kurulumu", "Aidat planı"]),
    ("Sezona dağınık başlama",
     "Defter, Excel ve gruplar yerine tek panel — kurulumu biz yapıyoruz.", "dağınık",
     ["Yoklama", "Takvim", "Tahsilat"]),
    ("Eylülde işin kolay olsun",
     "Yeni sporcular, yeni gruplar, yeni takvim: hepsi bir akşamda hazır.", "kolay",
     ["Veli portalı", "Evrak arşivi", "Duyuru"]),
]

KARSI: list[tuple[str, list[str], list[str]]] = [
    ("Kulüp yönetimi",
     ["Yoklama defteri ve kayıp sayfalar",
      "Excel'de tutulan aidat listesi",
      "Dört ayrı WhatsApp grubu"],
     ["Yoklama tek dokunuşla işlenir",
      "Aidat durumu her an güncel",
      "Duyuru herkese aynı anda gider"]),
    ("Aidat takibi",
     ["Kim ödedi, kim ödemedi belirsiz",
      "Elden nakit, kaybolan makbuz",
      "Ay sonu hesap kâbusu"],
     ["Ödeyen–ödemeyen tek ekranda",
      "Kartla ödeme, kayıt otomatik",
      "Makbuz anında velinin telefonunda"]),
]

RAKAM: list[tuple[str, str, str, str, str]] = [
    ("14", "GÜN", "Ücretsiz deneyin", "Kart bilgisi istemeden bütün özellikler açık.", "Ücretsiz"),
    ("0", "₺", "Taktik tahtası bedava", "Üyelik yok, sınır yok: çiz, oynat, yazdır.", "bedava"),
    ("1", "PANEL", "Kulübün tamamı burada", "Yoklama, aidat, takvim, veli iletişimi ve evrak.", "tamamı"),
]

LISTE: list[tuple[str, str, str, list[str]]] = [
    ("Sezon hazırlığı", "Sezon başlamadan beş iş", "beş",
     ["Kadroları ve grupları oluştur",
      "Veli iletişim bilgilerini topla",
      "Aidat tutarını ve gününü belirle",
      "Antrenman takvimini yayınla",
      "Lisans evraklarını dijitale taşı"]),
    ("İlk hafta", "Kulüp açılış kontrol listesi", "kontrol",
     ["Sporcu kayıtları girildi",
      "Antrenörler gruplara atandı",
      "Takvim velilere gönderildi",
      "Aidat planı tanımlandı",
      "Evraklar arşive yüklendi"]),
]


# ===========================================================================
#  ŞABLON: sezon — lacivert, dev başlık, altın alt bant (feed'de yeni bir ses)
# ===========================================================================
def _t_sezon(photo, headline, benefit, emph, extra=None):
    chips = (extra or {}).get("chips", [])
    dom = (extra or {}).get("domain", "kulups.com")
    urn = (extra or {}).get("urun")
    kick = (extra or {}).get("kick", "2026 · 2027 sezonu")
    base = Image.new("RGBA", (S, S), NAVY + (255,))
    cu = S * 0.0106
    _court_bg(base, u=cu, ox=(S - 100 * cu) / 2, oy=S * 0.085, alpha=26, stroke=3)
    d = ImageDraw.Draw(base)

    bar_h = 112
    maxw = S - 2 * M
    sz, lines = _mixed_wrap(d, headline, emph, 126, maxw, 3)
    bf, bl = _fit_plain(d, benefit, 32, maxw - 60, 2)

    # blok altın banttan yukarı doğru kurulur → hiçbir hâlde boşlukta yüzmez
    head_h = int(_lh(F_DISPLAY(sz)) * 1.04) * len(lines)
    ben_h = (_lh(bf) + 9) * len(bl)
    chip_h = 66 if chips else 0
    y = S - bar_h - 74 - chip_h - (34 if chips else 0) - ben_h - 22 - head_h
    _kicker(d, kick, y - 62, center=False, x=M, col=GOLD, size=27, track=6)
    d.line([M, y - 80, M + 96, y - 80], fill=GOLD, width=5)
    y = _draw_mixed(d, lines, sz, M, y)
    y += 22
    for ln in bl:
        d.text((M, y), ln, font=bf, fill=(203, 213, 225))
        y += _lh(bf) + 9

    # rozet sırası
    y += 34
    cf = F_TEXT(27, True)
    cx = M
    for c in chips:
        w = d.textlength(c, font=cf) + 52
        h = 66
        if cx + w > S - M:
            break
        d.rounded_rectangle([cx, y, cx + w, y + h], radius=h // 2,
                            outline=(71, 85, 105), width=2)
        d.ellipse([cx + 22, y + h / 2 - 5, cx + 32, y + h / 2 + 5], fill=GOLD)
        d.text((cx + 42, y + (h - _lh(cf)) / 2), c, font=cf, fill=PAPER)
        cx += w + 14

    # altın alt bant
    d.rectangle([0, S - bar_h, S, S], fill=GOLD)
    f1, f2 = F_TEXT(31, True), F_TEXT(29)
    t1, t2 = dom, "14 gün ücretsiz"
    w = d.textlength(t1, font=f1) + 30 + d.textlength(t2, font=f2)
    bx = (S - w) / 2
    by = S - bar_h + (bar_h - _lh(f1)) / 2
    d.text((bx, by), t1, font=f1, fill=NAVY)
    ccx = bx + d.textlength(t1, font=f1) + 12
    d.ellipse([ccx, by + 15, ccx + 6, by + 21], fill=(120, 95, 40))
    d.text((ccx + 18, by + 1), t2, font=f2, fill=(92, 72, 28))
    _brand(base, M, M - 18, urun=urn)
    return base.convert("RGB")


# ===========================================================================
#  ŞABLON: karsi — üstte "ÖNCE" (kâğıt), altta "SONRA" (lacivert)
# ===========================================================================
def _t_karsi(photo, headline, benefit, emph, extra=None):
    once = (extra or {}).get("once", [])
    sonra = (extra or {}).get("sonra", [])
    dom = (extra or {}).get("domain", "kulups.com")
    urn = (extra or {}).get("urun")
    cut = int(S * 0.50)
    base = Image.new("RGBA", (S, S), LIGHT_BG + (255,))
    d = ImageDraw.Draw(base)
    d.rectangle([0, cut, S, S], fill=NAVY)
    d.rectangle([0, cut - 5, S, cut], fill=GOLD)

    # başlık (kicker) — sağ üstte, markanın karşısında
    kf = F_TEXT(26, True)
    d.text((S - M - d.textlength(_ust(headline), font=kf), M + 4),
           _ust(headline), font=kf, fill=MUTED_D)

    def etiket(text, y, *, fill, ink, ol=None):
        f = F_TEXT(27, True)
        t = _ust(text)
        w = d.textlength(t, font=f) + 54
        h = 58
        d.rounded_rectangle([M, y, M + w, y + h], radius=h // 2, fill=fill,
                            outline=ol, width=2 if ol else 0)
        d.text((M + 27, y + (h - _lh(f)) / 2), t, font=f, fill=ink)
        return y + h

    def satirlar(items, y, *, ink, mark, mcol, ring):
        f = F_TEXT(33)
        for it in items:
            r = 20
            cx, cy = M + r, y + 22
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ring, width=3,
                      fill=(GOLD if mark == "check" else None))
            (_check if mark == "check" else _cross)(d, cx, cy, r, mcol, 5)
            _f, _l = _fit_plain(d, it, 33, S - (M + 2 * r + 26) - M, 1)
            d.text((M + 2 * r + 26, y + 22 - _lh(_f) / 2 + 1), _l[0], font=_f, fill=ink)
            y += 78
        return y

    y = etiket("önce", 196, fill=None, ink=MUTED_D, ol=(203, 213, 225))
    satirlar(once, y + 30, ink=(71, 85, 105), mark="cross", mcol=(148, 163, 184),
             ring=(214, 220, 230))

    y = etiket("sonra", cut + 52, fill=GOLD, ink=NAVY)
    satirlar(sonra, y + 30, ink=PAPER, mark="check", mcol=NAVY, ring=GOLD)

    _footer(d, S - M - 18, domain=dom)
    _brand(base, M, M - 18, dark_bg=False, urun=urn)
    return base.convert("RGB")


# ===========================================================================
#  ŞABLON: rakam — tek dev sayı; scroll'u durduran en sade kart
# ===========================================================================
def _t_rakam(photo, headline, benefit, emph, extra=None):
    num = (extra or {}).get("num", "14")
    unit = (extra or {}).get("unit", "GÜN")
    dom = (extra or {}).get("domain", "kulups.com")
    urn = (extra or {}).get("urun")
    base = Image.new("RGBA", (S, S), NAVY + (255,))
    cu = S * 0.0105
    _court_bg(base, u=cu, ox=(S - 100 * cu) / 2, oy=S * 0.63, alpha=17, stroke=2)
    d = ImageDraw.Draw(base)

    # 1) metin bloğu ÖNCE ölçülür ve footer'ın üstüne çapalanır
    maxw = S - 2 * M
    sz, lines = _mixed_wrap(d, headline, emph, 96, maxw, 2)
    bf, bl = _fit_plain(d, benefit, 32, maxw - 90, 2)
    foot_y = S - M - 24
    head_h = int(_lh(F_DISPLAY(sz)) * 1.04) * len(lines)
    ben_h = (_lh(bf) + 8) * len(bl)
    text_y = foot_y - 34 - ben_h - 18 - head_h

    # 2) sayı KALAN alana sığdırılır (başlık iki satırsa sayı küçülür, çakışmaz)
    top = 208
    zone = max(240, text_y - 46 - top)
    cy = top + zone / 2
    nf = F_DISPLAY(int(min(430, zone * 0.92)))
    nb = d.textbbox((0, 0), num, font=nf)
    nw, nh = nb[2] - nb[0], nb[3] - nb[1]
    nx = (S - nw) / 2

    ring = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    R = int(min(max(nh * 0.66, 210), zone / 2 - 6))
    ImageDraw.Draw(ring).ellipse([S / 2 - R, cy - R, S / 2 + R, cy + R],
                                 outline=GOLD + (70,), width=4)
    base.alpha_composite(ring)
    d = ImageDraw.Draw(base)
    d.text((nx - nb[0], cy - nh / 2 - nb[1]), num, font=nf, fill=GOLD)

    if unit:
        # tek karakterlik birim (₺) iri Work Sans ile — BigShoulders ₺'si tuhaf duruyor
        uf = F_TEXT(160, True) if len(unit) <= 2 else F_TEXT(46, True)
        ub = d.textbbox((0, 0), unit, font=uf)
        d.text((nx + nw + 24 - ub[0], cy + nh / 2 - (ub[3] - ub[1]) - ub[1]),
               unit, font=uf, fill=PAPER)

    y = _draw_mixed(d, lines, sz, 0, text_y, align="center", width=S)
    y += 18
    for ln in bl:
        d.text(((S - d.textlength(ln, font=bf)) / 2, y), ln, font=bf, fill=(203, 213, 225))
        y += _lh(bf) + 8
    _footer(d, foot_y, center=True, domain=dom)
    _brand(base, M, M - 26, urun=urn)
    return base.convert("RGB")


# ===========================================================================
#  ŞABLON: liste — kaydedilesi kontrol listesi (reklam değil, işe yarar içerik)
# ===========================================================================
def _t_liste(photo, headline, benefit, emph, extra=None):
    items = (extra or {}).get("items", [])
    kick = (extra or {}).get("kick", "Sezon hazırlığı")
    dom = (extra or {}).get("domain", "kulups.com")
    urn = (extra or {}).get("urun")
    base = Image.new("RGBA", (S, S), LIGHT_BG + (255,))
    cu = S * 0.0104
    ov = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    _court_motif_col(ImageDraw.Draw(ov), (S - 100 * cu) / 2, S * 0.30, cu, NAVY, alpha=11, stroke=2)
    base.alpha_composite(ov)
    d = ImageDraw.Draw(base)

    _kicker(d, kick, 214, center=False, x=M, col=BLUE, size=26, track=5)
    maxw = S - 2 * M
    sz, lines = _mixed_wrap(d, headline, emph, 92, maxw, 2)
    y = _draw_mixed(d, lines, sz, M, 258, ink=INK)

    # satırlar kalan yüksekliğe göre ölçülür → footer'a ASLA girmez
    foot_y = S - M - 6
    y += 30
    n = max(1, len(items[:5]))
    gap = 13
    avail = (foot_y - 34) - y
    rh = int(max(62, min(86, (avail - gap * (n - 1)) / n)))
    for i, it in enumerate(items[:5]):
        d.rounded_rectangle([M, y, S - M, y + rh], radius=16, fill=(255, 255, 255),
                            outline=(224, 230, 238), width=2)
        r = int(min(19, rh * 0.24))
        cx, cy = M + 34 + r, y + rh / 2
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GOLD)
        _check(d, cx, cy, r, (255, 255, 255), 5)
        _f, _l = _fit_plain(d, it, 31, S - 2 * M - (34 + 2 * r + 26) - 30, 1)
        d.text((cx + r + 26, cy - _lh(_f) / 2 + 1), _l[0], font=_f, fill=INK)
        y += rh + gap

    _footer(d, foot_y, x=M, dark=False, domain=dom)
    _brand(base, M, M - 26, dark_bg=False, urun=urn)
    return base.convert("RGB")


# ===========================================================================
#  ŞABLON: telefon — ürünün ölçüm ekranı telefonun içinde (Kulups Athletic)
# ===========================================================================
def _iskelet(d, x, y, w, h, col=(148, 163, 184), eklem=(226, 232, 240), kal=4):
    """Yandan koşu pozunda basit poz iskeleti — üründeki nokta-eşleme görüntüsü.

    Koordinatlar 0..1 kutusunda; ayaklar altta, yüz sağa (kapıya) bakar.
    """
    P = lambda a, b: (x + a * w, y + b * h)
    bas, boyun, omuz, kalca = (0.44, 0.10), (0.44, 0.20), (0.42, 0.24), (0.46, 0.52)
    kollar = [[omuz, (0.27, 0.36), (0.30, 0.50)], [omuz, (0.58, 0.33), (0.66, 0.22)]]
    bacaklar = [[kalca, (0.63, 0.74), (0.70, 0.99)], [kalca, (0.33, 0.72), (0.21, 0.62)]]
    d.ellipse([*P(bas[0] - 0.075, bas[1] - 0.070), *P(bas[0] + 0.075, bas[1] + 0.070)],
              outline=col, width=kal)
    d.line([*P(*boyun), *P(*kalca)], fill=col, width=kal)
    for zincir in kollar + bacaklar:
        for a, b in zip(zincir, zincir[1:]):
            d.line([*P(*a), *P(*b)], fill=col, width=kal)
    for nk in [boyun, omuz, kalca] + [z[1] for z in kollar + bacaklar] + [z[2] for z in kollar + bacaklar]:
        cx, cy = P(*nk)
        d.ellipse([cx - kal, cy - kal, cx + kal, cy + kal], fill=eklem)


def _t_telefon(photo, headline, benefit, emph, extra=None):
    e = extra or {}
    dom = e.get("domain", "kulups.com")
    urn = e.get("urun")
    scr = e.get("ekran", {})
    base = Image.new("RGBA", (S, S), NAVY + (255,))
    cu = S * 0.0095
    _court_bg(base, u=cu, ox=-S * 0.16, oy=S * 0.30, alpha=22, stroke=2)
    d = ImageDraw.Draw(base)

    # ---- telefon gövdesi (sağda) ----
    pw, ph = 348, 728
    px, py = S - M - pw, 176
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=46, fill=(2, 6, 18),
                        outline=(71, 85, 105), width=3)
    ix, iy, iw, ih = px + 11, py + 11, pw - 22, ph - 22
    d.rounded_rectangle([ix, iy, ix + iw, iy + ih], radius=36, fill=(10, 16, 32))
    d.rounded_rectangle([ix + iw / 2 - 59, iy + 10, ix + iw / 2 + 59, iy + 36],
                        radius=13, fill=(30, 41, 59))

    # test etiketi
    tf = F_TEXT(21, True)
    tt = _ust(scr.get("test", "20 m sürat"))
    d.text((ix + (iw - d.textlength(tt, font=tf)) / 2, iy + 58), tt, font=tf, fill=GOLD)

    # kamera görüntüsü: zemin çizgisi + altın kapı (kesikli dikey)
    cam_t, cam_b = iy + 100, iy + int(ih * 0.60)
    d.rounded_rectangle([ix + 16, cam_t, ix + iw - 16, cam_b], radius=18, fill=(15, 23, 42))
    zem = cam_b - 54
    d.line([ix + 34, zem, ix + iw - 34, zem], fill=(51, 65, 85), width=3)
    gx = ix + iw * 0.60
    yy = cam_t + 26
    while yy < zem + 20:                       # kesikli kapı çizgisi
        d.line([gx, yy, gx, min(yy + 13, zem + 20)], fill=GOLD, width=4)
        yy += 22
    d.polygon([(gx - 9, cam_t + 14), (gx + 9, cam_t + 14), (gx, cam_t + 30)], fill=GOLD)
    # poz iskeleti — sporcu kapıya koşuyor (ürünün ekranda gösterdiği şey)
    fh = (zem - cam_t) * 0.88
    _iskelet(d, ix + iw * 0.10, zem - fh, fh * 0.78, fh)

    # sonuç paneli
    rt = cam_b + 22
    rb = iy + int(ih * 0.855)
    d.rounded_rectangle([ix + 16, rt, ix + iw - 16, rb], radius=18, fill=(17, 26, 46))
    vf, uf = F_DISPLAY(96), F_TEXT(30, True)
    val, unit = scr.get("val", "3,42"), scr.get("unit", "sn")
    vb = d.textbbox((0, 0), val, font=vf)
    vw = vb[2] - vb[0]
    uw = d.textlength(unit, font=uf)
    sx = ix + (iw - (vw + 12 + uw)) / 2
    vy = rt + ((rb - rt) - (vb[3] - vb[1])) / 2 - 8
    d.text((sx - vb[0], vy - vb[1]), val, font=vf, fill=PAPER)
    d.text((sx + vw + 12, vy + (vb[3] - vb[1]) - _lh(uf) + 8), unit, font=uf, fill=MUTED)

    # onay şeridi
    af = F_TEXT(22, True)
    at = scr.get("alt", "Kapı geçildi")
    awd = d.textlength(at, font=af) + 74
    ax = ix + (iw - awd) / 2
    ay = rb + 18
    d.rounded_rectangle([ax, ay, ax + awd, ay + 50], radius=25, fill=(23, 37, 62))
    _check(d, ax + 30, ay + 25, 14, GOLD, 4)
    d.text((ax + 52, ay + (50 - _lh(af)) / 2), at, font=af, fill=(203, 213, 225))

    # ---- sol metin kolonu ----
    maxw = px - M - 52
    _kicker(d, e.get("kick", "telefon kamerasıyla"), 0, center=False, x=M, col=GOLD, size=24, track=5)
    sz, lines = _mixed_wrap(d, headline, emph, 92, maxw, 4)
    bf, bl = _fit_plain(d, benefit, 29, maxw, 4)
    head_h = int(_lh(F_DISPLAY(sz)) * 1.04) * len(lines)
    ben_h = (_lh(bf) + 8) * len(bl)
    y = (S - (head_h + 22 + ben_h)) / 2 + 10
    # kicker'ı başlığın hemen üstüne taşı (yukarıda 0'a çizileni sil)
    d.rectangle([0, 0, M + 420, 40], fill=NAVY)
    _kicker(d, e.get("kick", "telefon kamerasıyla"), y - 54, center=False, x=M, col=GOLD, size=24, track=5)
    d.line([M, y - 74, M + 84, y - 74], fill=GOLD, width=4)
    y = _draw_mixed(d, lines, sz, M, y)
    y += 22
    for ln in bl:
        d.text((M, y), ln, font=bf, fill=(203, 213, 225))
        y += _lh(bf) + 8

    _footer(d, S - M - 22, x=M, domain=dom)
    _brand(base, M, M - 26, urun=urn)
    return base.convert("RGB")


_RENDER = {"poster": _t_poster, "court": _t_court, "duo": _t_duo,
           "stat": _t_stat, "sistem": _t_sistem,
           "isik": _t_isik, "parlak": _t_parlak,
           "kutlama": _t_kutlama, "an": _t_an,
           "sezon": _t_sezon, "karsi": _t_karsi,
           "rakam": _t_rakam, "liste": _t_liste,
           "telefon": _t_telefon}


# ===========================================================================
#  Genel API
# ===========================================================================
def compose(concept: dict, *, pillar: str = "", template: str | None = None,
            exclude_templates: set | None = None,
            exclude_photos: set | None = None,
            pick: int | None = None, photo_name: str | None = None,
            icerik: dict | None = None) -> tuple[bytes, str, str]:
    """concept+pillar → (jpeg, şablon, foto). Kart metni KÜRATÖRLÜ havuzdan."""
    seed = concept.get("konsept_basligi") or concept.get("kart_baslik") or "kulups"
    rnd = random.Random(hashlib.sha1(seed.encode("utf-8")).hexdigest())

    tpls = [t for t in TEMPLATES if t not in (exclude_templates or set())] or list(TEMPLATES)
    # _RENDER'daki her şablon elle istenebilir (telefon gibi rotasyon dışı olanlar dahil)
    tpl = template if template in _RENDER else tpls[rnd.randrange(len(tpls))]

    extra = None
    if icerik:                      # küratörlü parti: metin havuzdan DEĞİL, çağırandan
        headline = icerik.get("headline", "")
        benefit = icerik.get("benefit", "")
        emph = icerik.get("emph", "")
        extra = icerik.get("extra") or {}
    elif tpl == "sezon":
        headline, benefit, emph, chips = SEZON[pick % len(SEZON) if pick is not None else rnd.randrange(len(SEZON))]
        extra = {"chips": chips}
    elif tpl == "karsi":
        headline, once, sonra = KARSI[pick % len(KARSI) if pick is not None else rnd.randrange(len(KARSI))]
        benefit, emph = "", ""
        extra = {"once": once, "sonra": sonra}
    elif tpl == "rakam":
        num, unit, headline, benefit, emph = RAKAM[pick % len(RAKAM) if pick is not None else rnd.randrange(len(RAKAM))]
        extra = {"num": num, "unit": unit}
    elif tpl == "liste":
        kick, headline, emph, items = LISTE[pick % len(LISTE) if pick is not None else rnd.randrange(len(LISTE))]
        benefit = ""
        extra = {"kick": kick, "items": items}
    else:
        if tpl == "sistem":
            pool = GENEL
        elif tpl in ("kutlama", "an"):
            pool = MUTLU
        else:
            pool = POOL.get(pillar) or [p for v in POOL.values() for p in v]
        headline, benefit, emph = pool[pick % len(pool) if pick is not None else rnd.randrange(len(pool))]

    if tpl in NOPHOTO_TPLS:
        photo_name, photo = "", None          # tipografik kart — fotoğraf harcamaz
    elif photo_name:
        photo = Image.open(PHOTO_DIR / f"{photo_name}.jpg").convert("RGB")
    elif tpl in LIGHT_TPLS:
        photo_name, photo = _pick_mood_photo(rnd, exclude_photos or set())
    else:
        photo_name, photo = _pick_photo(pillar, rnd, exclude_photos or set())
    img = (_RENDER[tpl](photo, headline, benefit, emph, extra)
           if (extra is not None and tpl in EXTRA_TPLS)
           else _RENDER[tpl](photo, headline, benefit, emph))

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92, optimize=True)
    log.info("kart hazır: şablon=%s foto=%s başlık=%r", tpl, photo_name, headline)
    return buf.getvalue(), tpl, photo_name


def _pick_mood_photo(rnd, exclude):
    files = {p.stem: p for p in sorted(PHOTO_DIR.glob("*.jpg"))}
    cands = [n for n in MOOD_PHOTOS if n in files and n not in exclude]         or [n for n in MOOD_PHOTOS if n in files] or list(files)
    name = cands[rnd.randrange(len(cands))]
    return name, Image.open(files[name]).convert("RGB")


def _pick_photo(pillar, rnd, exclude):
    files = {p.stem: p for p in sorted(PHOTO_DIR.glob("*.jpg"))}
    if not files:
        raise FileNotFoundError(f"stok fotoğraf yok: {PHOTO_DIR}")
    prefer = [n for n in PILLAR_PHOTOS.get(pillar, []) if n in files and n not in exclude]
    cands = prefer or [n for n in files if n not in exclude] or list(files)
    name = cands[rnd.randrange(len(cands))]
    return name, Image.open(files[name]).convert("RGB")
