"""Metin kartı: AI arka planı → koyu degrade örtü → gerçek metin + logo.

AI görsel modelleri düzgün yazı basamaz; özellik tanıtımı ise yazı ister.
Bu yüzden arka planı model üretir, METNİ burada Pillow ile biz basarız.
Sonuç: her arka planda okunabilir, marka tutarlı bir tanıtım kartı.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import config

log = config.get_logger("card")
ROOT = Path(__file__).resolve().parent.parent


def render_card(img: Image.Image, headline: str, benefit: str, style: dict) -> Image.Image:
    """Arka plan görselinin üstüne başlık/fayda metnini ve logoyu basar."""
    cfg = (style.get("card") or {})
    if not cfg.get("enabled", True):
        return img

    img = img.convert("RGB")
    w, h = img.size
    margin = int(cfg.get("margin", 78))

    img = _apply_overlay(img, cfg.get("overlay") or {})
    draw = ImageDraw.Draw(img)

    hl_cfg = cfg.get("headline") or {}
    bn_cfg = cfg.get("benefit") or {}
    ac_cfg = cfg.get("accent") or {}

    max_w = w - 2 * margin

    # Metinleri sığdır: kutuya sığmazsa punto küçülür, sonra satır kırpılır
    hl_font, hl_lines = _fit_text(
        draw, headline, int(hl_cfg.get("size", 74)), max_w,
        int(hl_cfg.get("max_lines", 3)), bold=True)
    bn_font, bn_lines = _fit_text(
        draw, benefit, int(bn_cfg.get("size", 38)), max_w,
        int(bn_cfg.get("max_lines", 3)), bold=False)

    hl_lh = _line_height(hl_font) + int(hl_cfg.get("line_spacing", 12))
    bn_lh = _line_height(bn_font) + int(bn_cfg.get("line_spacing", 9))
    hl_block = hl_lh * len(hl_lines)
    bn_block = bn_lh * len(bn_lines) if bn_lines else 0

    footer_cfg = cfg.get("footer") or {}
    footer_h = int(footer_cfg.get("size", 30)) + 18 if footer_cfg.get("text") else 0

    # Alttan yukarı yerleşim: footer → fayda → başlık → aksan çizgisi
    y = h - margin - footer_h - bn_block
    if bn_lines:
        y -= int(bn_cfg.get("gap", 26))
    y_headline_top = y - hl_block

    accent_h = int(ac_cfg.get("height", 7))
    y_accent = y_headline_top - int(ac_cfg.get("gap", 26)) - accent_h
    if ac_cfg.get("color"):
        draw.rounded_rectangle(
            [margin, y_accent, margin + int(ac_cfg.get("width", 96)), y_accent + accent_h],
            radius=accent_h // 2, fill=ac_cfg["color"])

    yy = y_headline_top
    for line in hl_lines:
        draw.text((margin, yy), line, font=hl_font, fill=hl_cfg.get("color", "#ffffff"))
        yy += hl_lh

    yy = y_headline_top + hl_block + (int(bn_cfg.get("gap", 26)) if bn_lines else 0)
    for line in bn_lines:
        draw.text((margin, yy), line, font=bn_font, fill=bn_cfg.get("color", "#dbe3f0"))
        yy += bn_lh

    if footer_cfg.get("text"):
        f_font = _load_font(int(footer_cfg.get("size", 30)), bold=False)
        draw.text((margin, h - margin - _line_height(f_font)), str(footer_cfg["text"]),
                  font=f_font, fill=footer_cfg.get("color", "#c8d3e6"))

    img = _paste_logo(img, cfg.get("logo") or {}, margin)
    return img


# ---------------------------------------------------------------------------
def _apply_overlay(img: Image.Image, ov: dict) -> Image.Image:
    """Üstten alta koyulaşan degrade — alt yarıdaki metni okunur kılar."""
    if not ov:
        return img
    w, h = img.size
    top_a = float(ov.get("top_alpha", 0.10))
    bot_a = float(ov.get("bottom_alpha", 0.92))
    start = float(ov.get("start", 0.30))

    mask = Image.new("L", (1, h))
    px = mask.load()
    for y in range(h):
        t = 0.0 if y < h * start else (y - h * start) / max(1.0, h * (1 - start))
        px[0, y] = int(255 * (top_a + (bot_a - top_a) * (t ** 1.35)))
    mask = mask.resize((w, h))

    layer = Image.new("RGB", (w, h), ov.get("color", "#0b1220"))
    return Image.composite(layer, img, mask)


def _paste_logo(img: Image.Image, lg: dict, margin: int) -> Image.Image:
    path = lg.get("path")
    if not path:
        return img
    p = ROOT / path
    if not p.exists():
        log.warning("logo bulunamadı: %s", p)
        return img
    logo = Image.open(p).convert("RGBA")
    target_h = int(lg.get("height", 92))
    ratio = target_h / logo.height
    logo = logo.resize((max(1, int(logo.width * ratio)), target_h), Image.LANCZOS)

    opacity = float(lg.get("opacity", 1.0))
    if opacity < 1.0:
        a = logo.getchannel("A").point(lambda v: int(v * opacity))
        logo.putalpha(a)

    base = img.convert("RGBA")
    base.alpha_composite(logo, (margin, margin))
    return base.convert("RGB")


def _fit_text(draw, text, size, max_w, max_lines, bold):
    """Punto küçülterek metni kutuya sığdırır; olmazsa son satırı '…' ile keser."""
    text = " ".join((text or "").split())
    if not text:
        return _load_font(size, bold), []
    for s in range(size, max(14, int(size * 0.55)) - 1, -2):
        font = _load_font(s, bold)
        lines = _wrap(draw, text, font, max_w)
        if len(lines) <= max_lines:
            return font, lines
    font = _load_font(max(14, int(size * 0.55)), bold)
    lines = _wrap(draw, text, font, max_w)[:max_lines]
    if lines:
        lines[-1] = lines[-1].rstrip(" ,.;:") + "…"
    return font, lines


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _line_height(font) -> int:
    try:
        a, d = font.getmetrics()
        return a + d
    except Exception:
        return getattr(font, "size", 20) + 6


_FONTS = {
    True: [   # kalın
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ],
    False: [  # normal
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ],
}


def _load_font(size: int, bold: bool = False):
    for path in _FONTS[bool(bold)]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()
