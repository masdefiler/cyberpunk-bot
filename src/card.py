"""Gönderi görseli: GERÇEK stok fotoğraf + 4 profesyonel şablon (Pillow).

Neden böyle: AI üretimi arka planlar sahte duruyordu ve tek şablon her gönderiyi
aynı gösteriyordu. Artık `assets/photos/` altındaki gerçek basketbol fotoğrafları
kullanılıyor ve 4 farklı düzenden biri seçiliyor:

    hero    — tam fotoğraf + alt degrade + editoryal metin bloğu
    marker  — başlık renkli "fosforlu" bloklar içinde, koyu zemin + fotoğraf
    split   — üstte marka renginde panel + yay kesimli fotoğraf altta
    mockup  — telefon maketi (gerçek kulups ekranı çizilir) + mesaj bandı

Tümü 1080×1080. Türkçe metin JSX/CSS değil doğrudan Pillow ile basılır; büyük
harfe ÇEVİRME yapılmaz (İ/ı bozulmasın).
"""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import config

log = config.get_logger("card")
ROOT = Path(__file__).resolve().parent.parent
PHOTO_DIR = ROOT / "assets" / "photos"
LOGO_PATH = ROOT / "assets" / "logo.png"

S = 1080  # kare gönderi

# ---- marka ----
NAVY = (15, 23, 42)
NAVY2 = (22, 35, 63)
BLUE = (26, 86, 219)
BLUE2 = (59, 130, 246)
GOLD = (212, 169, 79)
WHITE = (241, 245, 249)
MUTED = (148, 163, 184)
GREEN = (16, 185, 129)
AMBER = (180, 83, 9)
INK = (30, 41, 59)

TEMPLATES = ("hero", "marker", "split", "mockup")

# Konu → tercih edilen fotoğraflar (yoksa tüm havuzdan seçilir)
PHOTO_HINTS = {
    "aidat": ["huddle", "kids-coach", "game"],
    "yoklama": ["kids-coach", "kids-play", "huddle"],
    "veli": ["kids-coach", "kids-duel", "huddle"],
    "gelişim": ["kids-duel", "dunk", "game"],
    "taktik": ["huddle", "game", "kids-coach"],
    "maç": ["game", "dunk", "hoop"],
    "antrenman": ["kids-play", "kids-duel", "kids-coach"],
}


# ===========================================================================
#  Genel API
# ===========================================================================
def render_card(headline: str, benefit: str, *, template: str | None = None,
                seed: str = "", photo: str | None = None) -> Image.Image:
    """Başlık + fayda metninden 1080×1080 gönderi görseli üretir."""
    rnd = random.Random(hashlib.sha1((seed or headline).encode("utf-8")).hexdigest())
    template = template or TEMPLATES[rnd.randrange(len(TEMPLATES))]
    img = _pick_photo(headline + " " + benefit, photo, rnd)

    if template == "marker":
        return _t_marker(img, headline, benefit)
    if template == "split":
        return _t_split(img, headline, benefit)
    if template == "mockup":
        return _t_mockup(img, headline, benefit)
    return _t_hero(img, headline, benefit)


def compose(concept: dict, *, template: str | None = None) -> tuple[bytes, str]:
    """concept → (JPEG baytları, kullanılan şablon adı). Pipeline bunu çağırır."""
    import io
    headline = concept.get("kart_baslik") or concept.get("konsept_basligi") or ""
    benefit = concept.get("kart_fayda") or ""
    seed = concept.get("konsept_basligi") or headline
    rnd = random.Random(hashlib.sha1(seed.encode("utf-8")).hexdigest())
    tpl = template or TEMPLATES[rnd.randrange(len(TEMPLATES))]
    img = render_card(headline, benefit, template=tpl, seed=seed)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92, optimize=True)
    log.info("kart hazır: şablon=%s başlık=%r", tpl, headline[:48])
    return buf.getvalue(), tpl


# ===========================================================================
#  ŞABLON 1 — hero: tam fotoğraf + editoryal metin
# ===========================================================================
def _t_hero(photo: Image.Image, headline: str, benefit: str) -> Image.Image:
    img = _cover(photo, S, S)
    img = _gradient(img, start=0.34, top_a=0.18, bot_a=0.95)
    d = ImageDraw.Draw(img)
    m = 84
    maxw = S - 2 * m

    hf, hl = _fit(d, headline, 78, maxw, 3, True)
    bf, bl = _fit(d, benefit, 34, maxw, 2, False)
    hlh, blh = _lh(hf) + 10, _lh(bf) + 8

    cta_h = 66
    y = S - m - cta_h - 34 - (blh * len(bl)) - 26 - (hlh * len(hl))

    # altın aksan
    d.rounded_rectangle([m, y - 34, m + 104, y - 34 + 9], radius=4, fill=GOLD)
    for ln in hl:
        d.text((m, y), ln, font=hf, fill=WHITE)
        y += hlh
    y += 26
    for ln in bl:
        d.text((m, y), ln, font=bf, fill=(203, 213, 225))
        y += blh

    _cta_row(d, m, S - m - cta_h, "kulups.com", "14 gün ücretsiz")
    return _logo_lockup(img, m, m, wordmark=True)


# ===========================================================================
#  ŞABLON 2 — marker: fosforlu başlık blokları
# ===========================================================================
def _t_marker(photo: Image.Image, headline: str, benefit: str) -> Image.Image:
    img = _cover(photo, S, S)
    # sağ-alt fotoğraf kalsın, sol-üst koyulaşsın
    ov = Image.new("RGB", (S, S), NAVY)
    mask = Image.linear_gradient("L").rotate(-32, resample=Image.BICUBIC, expand=False)
    mask = mask.resize((S, S)).point(lambda v: int(255 - v * 0.62))
    img = Image.composite(ov, img, mask)
    img = _gradient(img, start=0.55, top_a=0.0, bot_a=0.72)

    d = ImageDraw.Draw(img)
    m = 84
    maxw = S - 2 * m - 40

    hf, hl = _fit(d, headline, 74, maxw, 3, True)
    y = 260
    for ln in hl:
        tw = d.textlength(ln, font=hf)
        h = _lh(hf)
        d.rounded_rectangle([m - 18, y - 12, m + tw + 26, y + h + 10], radius=14, fill=BLUE)
        d.text((m, y), ln, font=hf, fill=(255, 255, 255))
        y += h + 22

    bf, bl = _fit(d, benefit, 34, maxw, 3, False)
    y += 16
    for ln in bl:
        d.text((m, y), ln, font=bf, fill=(226, 232, 240))
        y += _lh(bf) + 8

    _pill(d, m, S - 84 - 74, "14 gün ücretsiz dene", fill=GOLD, fg=NAVY, size=32)
    return _logo_lockup(img, m, m, wordmark=True)


# ===========================================================================
#  ŞABLON 3 — split: marka paneli + yay kesimli fotoğraf
# ===========================================================================
def _t_split(photo: Image.Image, headline: str, benefit: str) -> Image.Image:
    cut = int(S * 0.60)
    img = Image.new("RGB", (S, S), NAVY)

    # üst: köşegen marka degradesi
    top = Image.new("RGB", (S, cut + 90), NAVY)
    td = ImageDraw.Draw(top)
    for i in range(cut + 90):
        t = i / (cut + 90)
        td.line([(0, i), (S, i)],
                fill=(int(15 + (26 - 15) * t), int(23 + (86 - 23) * t), int(42 + (219 - 42) * t)))
    img.paste(top, (0, 0))

    # alt: fotoğraf, üst kenarı yay ile kesilmiş
    ph = _cover(photo, S, S - cut + 80)
    m_ = Image.new("L", ph.size, 0)
    md = ImageDraw.Draw(m_)
    md.rectangle([0, 90, S, ph.size[1]], fill=255)
    md.ellipse([-S * 0.15, -40, S * 1.15, 220], fill=255)
    img.paste(ph, (0, cut - 80), m_)

    d = ImageDraw.Draw(img)
    m = 92
    maxw = S - 2 * m

    hf, hl = _fit(d, headline, 72, maxw, 3, True)
    bf, bl = _fit(d, benefit, 32, maxw, 2, False)
    block = _lh(hf) * len(hl) + 24 + (_lh(bf) + 6) * len(bl)
    y = 236
    for ln in hl:
        d.text(((S - d.textlength(ln, font=hf)) / 2, y), ln, font=hf, fill=WHITE)
        y += _lh(hf) + 6
    y += 18
    for ln in bl:
        d.text(((S - d.textlength(ln, font=bf)) / 2, y), ln, font=bf, fill=(191, 205, 226))
        y += _lh(bf) + 6

    _pill(d, None, y + 26, "14 gün ücretsiz dene", fill=(255, 255, 255), fg=BLUE, size=32)
    img = _logo_lockup(img, None, 92, wordmark=True, center=True)
    return img


# ===========================================================================
#  ŞABLON 4 — mockup: telefon maketi + gerçek kulups ekranı
# ===========================================================================
def _t_mockup(photo: Image.Image, headline: str, benefit: str) -> Image.Image:
    img = _cover(photo, S, S)
    img = Image.blend(img, Image.new("RGB", (S, S), NAVY), 0.76)
    img = _gradient(img, start=0.0, top_a=0.25, bot_a=0.55)

    # telefon
    pw, ph = 386, 720
    px, py = 74, (S - ph) // 2 + 26
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([px - 10, py - 10, px + pw + 10, py + ph + 10], radius=54,
                        fill=(11, 17, 32), outline=(51, 65, 85), width=3)
    screen = _phone_screen(pw - 22, ph - 22, headline + " " + benefit)
    m_ = Image.new("L", screen.size, 0)
    ImageDraw.Draw(m_).rounded_rectangle([0, 0, screen.size[0], screen.size[1]], radius=42, fill=255)
    img.paste(screen, (px + 11, py + 11), m_)

    # sağ metin sütunu
    tx = px + pw + 66
    maxw = S - tx - 74
    hf, hl = _fit(d, headline, 58, maxw, 4, True)
    bf, bl = _fit(d, benefit, 29, maxw, 4, False)
    block = (_lh(hf) + 8) * len(hl) + 22 + (_lh(bf) + 7) * len(bl) + 96
    y = (S - block) // 2 + 20

    d.rounded_rectangle([tx, y - 46, tx + 96, y - 46 + 8], radius=4, fill=GOLD)
    for ln in hl:
        d.text((tx, y), ln, font=hf, fill=WHITE)
        y += _lh(hf) + 8
    y += 22
    for ln in bl:
        d.text((tx, y), ln, font=bf, fill=(203, 213, 225))
        y += _lh(bf) + 7
    _pill(d, tx, y + 26, "kulups.com", fill=BLUE, fg=(255, 255, 255), size=30)

    return _logo_lockup(img, 74, 64, wordmark=True)


def _phone_screen(w: int, h: int, topic: str) -> Image.Image:
    """Telefon ekranı: gerçek kulups panel görünümü (aidat ya da yoklama)."""
    yoklama = any(k in topic.lower() for k in ("yoklama", "katılım", "devamsız"))
    sc = Image.new("RGB", (w, h), (244, 246, 250))
    d = ImageDraw.Draw(sc)
    f = lambda k, b=False: _font(max(9, int(w * k)), b)

    # durum çubuğu
    d.text((22, 18), "kulups", font=f(0.058, True), fill=BLUE)
    d.rounded_rectangle([w - 62, 20, w - 26, 36], radius=4, outline=(51, 65, 85), width=2)
    d.rounded_rectangle([w - 59, 23, w - 40, 33], radius=2, fill=GREEN)

    # başlık bandı
    top = 62
    hh = int(w * 0.15)
    d.rounded_rectangle([16, top, w - 16, top + hh], radius=16, fill=BLUE)
    d.text((34, top + hh * 0.28), "Yoklama" if yoklama else "Aidat Takibi",
           font=f(0.055, True), fill=(255, 255, 255))
    d.text((w - 34 - d.textlength("U14", font=f(0.042, True)), top + hh * 0.34), "U14",
           font=f(0.042, True), fill=(219, 234, 254))

    rows = [("Ali Kaya", True), ("Zeynep Demir", True), ("Mert Yıldız", True),
            ("Elif Şahin", False), ("Kaan Aydın", True)]
    y = top + hh + 14
    rh = int(h * 0.098)
    for ad, ok in rows:
        d.rounded_rectangle([16, y, w - 16, y + rh], radius=12, fill=(255, 255, 255))
        ini = "".join(p[0] for p in ad.split())
        d.ellipse([32, y + rh * 0.24, 32 + rh * 0.5, y + rh * 0.74], fill=(230, 237, 251))
        d.text((32 + rh * 0.14, y + rh * 0.34), ini, font=f(0.032, True), fill=BLUE)
        d.text((32 + rh * 0.66, y + rh * 0.32), ad, font=f(0.042, True), fill=INK)
        if yoklama:
            txt, bg, fg = ("Katıldı", (220, 252, 231), (4, 120, 87)) if ok else ("Gelmedi", (254, 226, 226), (153, 27, 27))
        else:
            txt, bg, fg = ("Ödendi", (220, 252, 231), (4, 120, 87)) if ok else ("Bekliyor", (255, 247, 237), AMBER)
        tw = d.textlength(txt, font=f(0.032, True))
        d.rounded_rectangle([w - 34 - tw - 26, y + rh * 0.28, w - 30, y + rh * 0.72], radius=999, fill=bg)
        d.text((w - 34 - tw - 13, y + rh * 0.36), txt, font=f(0.032, True), fill=fg)
        y += rh + 10

    # özet
    d.rounded_rectangle([16, y + 6, w - 16, y + 6 + int(h * 0.1)], radius=14, fill=(248, 250, 252))
    lbl = "Bugün katılım" if yoklama else "Bu ay tahsil edilen"
    val = "4 / 5" if yoklama else "3.000 ₺"
    d.text((34, y + 6 + h * 0.032), lbl, font=f(0.036), fill=(71, 85, 105))
    vw = d.textlength(val, font=f(0.052, True))
    d.text((w - 34 - vw, y + 6 + h * 0.026), val, font=f(0.052, True), fill=GREEN)
    return sc


# ===========================================================================
#  Ortak parçalar
# ===========================================================================
def _pick_photo(topic: str, forced: str | None, rnd: random.Random) -> Image.Image:
    files = sorted(PHOTO_DIR.glob("*.jpg"))
    if not files:
        raise FileNotFoundError(f"stok fotoğraf yok: {PHOTO_DIR}")
    if forced:
        p = PHOTO_DIR / f"{forced}.jpg"
        if p.exists():
            return Image.open(p).convert("RGB")
    low = topic.lower()
    for key, names in PHOTO_HINTS.items():
        if key in low:
            cands = [PHOTO_DIR / f"{n}.jpg" for n in names]
            cands = [c for c in cands if c.exists()]
            if cands:
                return Image.open(rnd.choice(cands)).convert("RGB")
    return Image.open(rnd.choice(files)).convert("RGB")


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    r = max(w / img.width, h / img.height)
    im = img.resize((max(w, int(img.width * r) + 1), max(h, int(img.height * r) + 1)), Image.LANCZOS)
    x = (im.width - w) // 2
    y = int((im.height - h) * 0.34)   # yüzler üst-orta kalsın
    return im.crop((x, y, x + w, y + h))


def _gradient(img: Image.Image, *, start: float, top_a: float, bot_a: float) -> Image.Image:
    w, h = img.size
    mask = Image.new("L", (1, h))
    px = mask.load()
    for y in range(h):
        t = 0.0 if y < h * start else (y - h * start) / max(1.0, h * (1 - start))
        px[0, y] = int(255 * min(1.0, top_a + (bot_a - top_a) * (t ** 1.3)))
    return Image.composite(Image.new("RGB", (w, h), NAVY), img, mask.resize((w, h)))


def _logo_lockup(img: Image.Image, x: int | None, y: int, *, wordmark: bool = False,
                 center: bool = False) -> Image.Image:
    """Beyaz app-icon çipi içinde kalkan + isteğe bağlı 'kulups' yazısı."""
    chip = 96
    base = img.convert("RGBA")
    d = ImageDraw.Draw(base)
    wf = _font(40, True)
    total = chip + (14 + int(d.textlength("kulups", font=wf)) if wordmark else 0)
    if center or x is None:
        x = (S - total) // 2
    d.rounded_rectangle([x, y, x + chip, y + chip], radius=26, fill=(255, 255, 255, 240))
    if LOGO_PATH.exists():
        lg = Image.open(LOGO_PATH).convert("RGBA")
        k = int(chip * 0.68)
        r = k / max(lg.size)
        lg = lg.resize((max(1, int(lg.width * r)), max(1, int(lg.height * r))), Image.LANCZOS)
        base.alpha_composite(lg, (x + (chip - lg.width) // 2, y + (chip - lg.height) // 2))
    if wordmark:
        d = ImageDraw.Draw(base)
        d.text((x + chip + 14, y + (chip - _lh(wf)) // 2 - 2), "kulups", font=wf, fill=(255, 255, 255, 245))
    return base.convert("RGB")


def _pill(d: ImageDraw.ImageDraw, x: int | None, y: int, text: str, *, fill, fg, size: int):
    f = _font(size, True)
    tw = d.textlength(text, font=f)
    pad_x, h = 34, int(size * 2.3)
    w = tw + pad_x * 2
    if x is None:
        x = int((S - w) / 2)
    d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=fill)
    d.text((x + pad_x, y + (h - _lh(f)) // 2), text, font=f, fill=fg)
    return y + h


def _cta_row(d: ImageDraw.ImageDraw, x: int, y: int, domain: str, note: str):
    df = _font(36, True)
    nf = _font(30, False)
    d.text((x, y + 12), domain, font=df, fill=GOLD)
    dw = d.textlength(domain, font=df)
    d.text((x + dw + 20, y + 17), "·", font=nf, fill=MUTED)
    d.text((x + dw + 42, y + 17), note, font=nf, fill=(203, 213, 225))


# ---- metin yardımcıları ----
def _fit(d, text, size, max_w, max_lines, bold):
    text = " ".join((text or "").split())
    if not text:
        return _font(size, bold), []
    for s in range(size, max(16, int(size * 0.55)) - 1, -2):
        f = _font(s, bold)
        lines = _wrap(d, text, f, max_w)
        if len(lines) <= max_lines:
            return f, lines
    f = _font(max(16, int(size * 0.55)), bold)
    lines = _wrap(d, text, f, max_w)[:max_lines]
    if lines:
        lines[-1] = lines[-1].rstrip(" ,.;:") + "…"
    return f, lines


def _wrap(d, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if d.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _lh(font) -> int:
    try:
        a, dd = font.getmetrics()
        return a + dd
    except Exception:
        return getattr(font, "size", 20) + 6


_FONTS = {
    True: ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"],
    False: ["/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"],
}


def _font(size: int, bold: bool = False):
    for p in _FONTS[bool(bold)]:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()
