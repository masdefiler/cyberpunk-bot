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
             "isik", "parlak", "kutlama", "an")
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


def _brand(base: Image.Image, x: int, y: int, *, dark_bg: bool = True, chip: int = 74):
    """Beyaz çipte kalkan + 'kulups' kelimesi — küçük, kesin, köşede."""
    d = ImageDraw.Draw(base)
    d.rounded_rectangle([x, y, x + chip, y + chip], radius=int(chip * 0.28),
                        fill=(255, 255, 255),
                        outline=None if dark_bg else (203, 213, 225),
                        width=0 if dark_bg else 2)
    if LOGO_PATH.exists():
        lg = Image.open(LOGO_PATH).convert("RGBA")
        k = int(chip * 0.68)
        r = k / max(lg.size)
        lg = lg.resize((max(1, int(lg.width * r)), max(1, int(lg.height * r))), Image.LANCZOS)
        base.alpha_composite(lg.convert("RGBA"), (x + (chip - lg.width) // 2, y + (chip - lg.height) // 2))
    wf = F_TEXT(34, bold=True)
    d = ImageDraw.Draw(base)
    d.text((x + chip + 16, y + (chip - _lh(wf)) // 2), "kulups",
           font=wf, fill=PAPER if dark_bg else INK)


def _footer(d, y, *, center=False, x=M, dark=True):
    """Alt satır: kulups.com — nokta — 14 gün ücretsiz (iki temada da)."""
    f1, f2 = F_TEXT(30, True), F_TEXT(28)
    t1, t2 = "kulups.com", "14 gün ücretsiz"
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
def _t_poster(photo, headline, benefit, emph):
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
    _footer(d, foot_y)
    _brand(base, M, M - 18)
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
    _brand(base, M, M - 18, dark_bg=False)
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
    _brand(base, M, M - 26, dark_bg=False)
    return base.convert("RGB")


def _t_an(photo, headline, benefit, emph):
    """Polaroid 'an' kartı: açık zemin, çerçeveli eğik foto + merkez başlık."""
    base = Image.new("RGBA", (S, S), LIGHT_BG + (255,))
    cu = S * 0.009
    ov = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    _court_motif_col(ImageDraw.Draw(ov), S * 0.3, S * 0.5, cu, NAVY, alpha=20, stroke=2)
    base.alpha_composite(ov)

    pw, phh = 470, 520
    pol = Image.new("RGBA", (pw, phh), (255, 255, 255, 255))
    pol.paste(_cover(_warm(photo), pw - 44, phh - 110, focus=0.28), (22, 22))
    pol = pol.rotate(-3.4, expand=True, resample=Image.BICUBIC)
    sh = Image.new("RGBA", pol.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([10, 16, pol.size[0] - 4, pol.size[1] - 2], 12, fill=(15, 23, 42, 60))
    sh = sh.filter(ImageFilter.GaussianBlur(14))
    px_ = (S - pol.size[0]) // 2
    base.alpha_composite(sh, (px_, 118))
    base.alpha_composite(pol, (px_, 104))

    d = ImageDraw.Draw(base)
    maxw = S - 2 * M
    sz, lines = _mixed_wrap(d, headline, emph, 88, maxw, 2)
    bf, bl = _fit_plain(d, benefit, 29, maxw - 80, 2)
    y = 104 + pol.size[1] + 34
    y = _draw_mixed(d, lines, sz, 0, y, align="center", width=S, ink=INK)
    y += 12
    for ln in bl:
        d.text(((S - d.textlength(ln, font=bf)) / 2, y), ln, font=bf, fill=MUTED_D)
        y += _lh(bf) + 7
    _footer(d, S - M - 22, center=True, dark=False)
    _brand(base, M, M - 34, dark_bg=False)
    return base.convert("RGB")


_RENDER = {"poster": _t_poster, "court": _t_court, "duo": _t_duo,
           "stat": _t_stat, "sistem": _t_sistem,
           "isik": _t_isik, "parlak": _t_parlak,
           "kutlama": _t_kutlama, "an": _t_an}


# ===========================================================================
#  Genel API
# ===========================================================================
def compose(concept: dict, *, pillar: str = "", template: str | None = None,
            exclude_templates: set | None = None,
            exclude_photos: set | None = None) -> tuple[bytes, str, str]:
    """concept+pillar → (jpeg, şablon, foto). Kart metni KÜRATÖRLÜ havuzdan."""
    seed = concept.get("konsept_basligi") or concept.get("kart_baslik") or "kulups"
    rnd = random.Random(hashlib.sha1(seed.encode("utf-8")).hexdigest())

    tpls = [t for t in TEMPLATES if t not in (exclude_templates or set())] or list(TEMPLATES)
    tpl = template if template in TEMPLATES else tpls[rnd.randrange(len(tpls))]

    if tpl == "sistem":
        pool = GENEL
    elif tpl in ("kutlama", "an"):
        pool = MUTLU
    else:
        pool = POOL.get(pillar) or [p for v in POOL.values() for p in v]
    headline, benefit, emph = pool[rnd.randrange(len(pool))]

    if tpl in LIGHT_TPLS:
        photo_name, photo = _pick_mood_photo(rnd, exclude_photos or set())
    else:
        photo_name, photo = _pick_photo(pillar, rnd, exclude_photos or set())
    img = _RENDER[tpl](photo, headline, benefit, emph)

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
