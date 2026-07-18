"""Görsel üretimi: prompt → 1080x1350 (4:5) işlenmiş PNG bayt dizisi.

Sağlayıcılar ortak bir arayüz uygular:  _provider(prompt, negative, w, h) -> bytes
`generate()` sağlayıcı zincirini sırayla dener (biri patlarsa sıradakine düşer),
ham görseli 4:5'e getirir ve Pillow ile hafif son-işleme + filigran uygular.
"""
from __future__ import annotations

import base64
import io
import random
import urllib.parse
from typing import Callable

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from . import config

log = config.get_logger("generate")

HTTP_TIMEOUT = 120  # flux üretimi yavaş olabilir


class GenerationError(RuntimeError):
    """Tüm sağlayıcılar başarısız olduğunda yükseltilir."""


# ---------------------------------------------------------------------------
#  Prompt kurulumu — ortak stil eki her zaman sona eklenir
# ---------------------------------------------------------------------------
def build_prompt(gorsel_prompt: str, style: dict) -> str:
    suffix = " ".join((style.get("style_suffix") or "").split())
    return f"{gorsel_prompt.strip()}, {suffix}".strip(", ")


def build_negative(concept_negative: str, style: dict) -> str:
    base = " ".join((style.get("negative_prompt") or "").split())
    extra = (concept_negative or "").strip()
    return f"{extra}, {base}".strip(", ") if extra else base


# ---------------------------------------------------------------------------
#  Sağlayıcılar — her biri ham görsel baytları döndürür
# ---------------------------------------------------------------------------
def _pollinations(prompt: str, negative: str, w: int, h: int) -> bytes:
    """Anahtarsız, ücretsiz. Görseli doğrudan bayt olarak döndürür."""
    model = config.settings().get("providers", {}).get("pollinations", {}).get("model", "flux")
    encoded = urllib.parse.quote(prompt, safe="")
    seed = random.randint(1, 2_000_000_000)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={w}&height={h}&model={model}&nologo=true&seed={seed}"
    )
    r = requests.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    if not r.content or not r.headers.get("content-type", "").startswith("image"):
        raise GenerationError("pollinations görsel döndürmedi")
    return r.content


def _cloudflare(prompt: str, negative: str, w: int, h: int) -> bytes:
    """Cloudflare Workers AI FLUX-1-schnell. base64 JSON döndürür."""
    account = config.env("CLOUDFLARE_ACCOUNT_ID")
    token = config.env("CLOUDFLARE_API_TOKEN")
    if not (account and token):
        raise GenerationError("cloudflare anahtarları yok")
    model = config.settings().get("providers", {}).get("cloudflare", {}).get(
        "model", "@cf/black-forest-labs/flux-1-schnell"
    )
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": prompt, "steps": 6},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    b64 = (data.get("result") or {}).get("image")
    if not b64:
        raise GenerationError(f"cloudflare beklenmeyen yanıt: {str(data)[:200]}")
    return base64.b64decode(b64)


def _together(prompt: str, negative: str, w: int, h: int) -> bytes:
    """Together FLUX.1-schnell-Free. b64_json döndürür."""
    key = config.env("TOGETHER_API_KEY")
    if not key:
        raise GenerationError("together anahtarı yok")
    model = config.settings().get("providers", {}).get("together", {}).get(
        "model", "black-forest-labs/FLUX.1-schnell-Free"
    )
    r = requests.post(
        "https://api.together.xyz/v1/images/generations",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "prompt": prompt, "width": w, "height": h,
              "steps": 4, "n": 1, "response_format": "b64_json"},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    item = (r.json().get("data") or [{}])[0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        return _fetch(item["url"])
    raise GenerationError("together görsel döndürmedi")


def _fal(prompt: str, negative: str, w: int, h: int) -> bytes:
    """fal.ai flux/schnell (ücretli, opsiyonel). URL döndürür."""
    key = config.env("FAL_KEY")
    if not key:
        raise GenerationError("fal anahtarı yok")
    r = requests.post(
        "https://fal.run/fal-ai/flux/schnell",
        headers={"Authorization": f"Key {key}"},
        json={"prompt": prompt, "image_size": {"width": w, "height": h},
              "num_images": 1},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    imgs = r.json().get("images") or []
    if not imgs or not imgs[0].get("url"):
        raise GenerationError("fal görsel döndürmedi")
    return _fetch(imgs[0]["url"])


def _fetch(url: str) -> bytes:
    r = requests.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.content


PROVIDERS: dict[str, Callable[[str, str, int, int], bytes]] = {
    "pollinations": _pollinations,
    "cloudflare": _cloudflare,
    "together": _together,
    "fal": _fal,
}


# ---------------------------------------------------------------------------
#  Genel giriş — zinciri dene, işle, döndür
# ---------------------------------------------------------------------------
def generate(concept: dict, style: dict) -> tuple[bytes, str]:
    """Konsepti görsele çevirir. (işlenmiş_png_baytları, kullanılan_sağlayıcı) döndürür."""
    w = int(style.get("width", 1080))
    h = int(style.get("height", 1350))
    prompt = build_prompt(concept["gorsel_prompt"], style)
    negative = build_negative(concept.get("negatif_prompt", ""), style)

    settings = config.settings()
    forced = config.env("PROVIDER")
    chain = [forced] if forced else list(settings.get("provider_chain", ["pollinations"]))

    last_err: Exception | None = None
    for name in chain:
        fn = PROVIDERS.get(name)
        if not fn:
            log.warning("bilinmeyen sağlayıcı: %s", name)
            continue
        try:
            log.info("görsel üretiliyor → %s", name)
            raw = fn(prompt, negative, w, h)
            processed = postprocess(raw, style)
            log.info("görsel hazır (%s, %d bayt)", name, len(processed))
            return processed, name
        except Exception as exc:
            log.warning("sağlayıcı '%s' başarısız: %s", name, exc)
            last_err = exc
            continue
    raise GenerationError(f"tüm sağlayıcılar başarısız: {last_err}")


# ---------------------------------------------------------------------------
#  Pillow son-işleme: 4:5 kırp + kontrast/doygunluk + grain + vinyet + filigran
# ---------------------------------------------------------------------------
def postprocess(raw: bytes, style: dict) -> bytes:
    w = int(style.get("width", 1080))
    h = int(style.get("height", 1350))
    post = style.get("post", {}) or {}

    img = Image.open(io.BytesIO(raw)).convert("RGB")
    img = _crop_to_fill(img, w, h)

    if post.get("contrast"):
        img = ImageEnhance.Contrast(img).enhance(float(post["contrast"]))
    if post.get("saturation"):
        img = ImageEnhance.Color(img).enhance(float(post["saturation"]))
    if post.get("grain"):
        img = _add_grain(img, float(post["grain"]))
    if post.get("vignette"):
        img = _add_vignette(img, float(post["vignette"]))

    wm = post.get("watermark", {}) or {}
    if wm.get("enabled") and str(wm.get("text", "")).strip():
        img = _add_watermark(img, wm)

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _crop_to_fill(img: Image.Image, w: int, h: int) -> Image.Image:
    """Hedef en-boy oranına ortadan kırp, sonra tam boyuta ölçekle."""
    target = w / h
    src = img.width / img.height
    if src > target:  # çok geniş → yanlardan kırp
        new_w = int(img.height * target)
        left = (img.width - new_w) // 2
        img = img.crop((left, 0, left + new_w, img.height))
    elif src < target:  # çok uzun → üst/alttan kırp
        new_h = int(img.width / target)
        top = (img.height - new_h) // 2
        img = img.crop((0, top, img.width, top + new_h))
    return img.resize((w, h), Image.LANCZOS)


def _add_grain(img: Image.Image, amount: float) -> Image.Image:
    """Çok hafif tek renk film grain'i (0..1)."""
    if amount <= 0:
        return img
    import random as _r
    noise = Image.new("L", img.size)
    span = int(max(1, min(255, amount * 255)))
    noise.putdata([_r.randint(-span, span) % 256 for _ in range(img.width * img.height)])
    grain_rgb = Image.merge("RGB", (noise, noise, noise))
    return Image.blend(img, grain_rgb, min(0.12, amount * 1.5))


def _add_vignette(img: Image.Image, strength: float) -> Image.Image:
    """Kenarları hafifçe karartan radyal vinyet (0..1)."""
    if strength <= 0:
        return img
    from PIL import ImageFilter
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((-w * 0.25, -h * 0.25, w * 1.25, h * 1.25), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=min(w, h) * 0.18))
    black = Image.new("RGB", (w, h), (0, 0, 0))
    faded = Image.composite(img, black, mask)
    return Image.blend(img, faded, min(1.0, strength))


def _add_watermark(img: Image.Image, wm: dict) -> Image.Image:
    text = str(wm.get("text", "")).strip()
    size = int(wm.get("size", 26))
    opacity = int(max(0.0, min(1.0, float(wm.get("opacity", 0.32)))) * 255)
    margin = int(wm.get("margin", 34))
    position = str(wm.get("position", "bottom-right"))

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _load_font(size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    x = margin if "left" in position else img.width - tw - margin
    y = margin if "top" in position else img.height - th - margin
    # okunabilirlik için hafif gölge
    draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, opacity))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, opacity))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()
