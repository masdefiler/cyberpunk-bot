"""generate.py — prompt kurulumu, 4:5 kırpma, son-işleme, sağlayıcı fallback."""
import io

from PIL import Image

from src import generate


def _img_bytes(w, h, color=(120, 40, 160)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def test_build_prompt_appends_suffix():
    style = {"style_suffix": "cinematic  cyberpunk"}
    out = generate.build_prompt("a neon street", style)
    assert out.startswith("a neon street")
    assert "cinematic cyberpunk" in out          # fazla boşluklar tekilleşir


def test_build_negative_combines():
    style = {"negative_prompt": "blurry, text"}
    assert "ugly" in generate.build_negative("ugly", style)
    assert "blurry" in generate.build_negative("ugly", style)


def test_crop_to_fill_from_square():
    img = Image.new("RGB", (1000, 1000))
    out = generate._crop_to_fill(img, 1080, 1350)
    assert out.size == (1080, 1350)


def test_crop_to_fill_from_wide():
    img = Image.new("RGB", (2000, 800))
    out = generate._crop_to_fill(img, 1080, 1350)
    assert out.size == (1080, 1350)


def test_postprocess_outputs_target_png():
    style = {
        "width": 1080, "height": 1350,
        "post": {"contrast": 1.05, "saturation": 1.05, "grain": 0.03, "vignette": 0.1,
                 "watermark": {"enabled": True, "text": "TEST", "size": 24}},
    }
    out = generate.postprocess(_img_bytes(1024, 1024), style)
    im = Image.open(io.BytesIO(out))
    assert im.size == (1080, 1350)
    assert im.format == "PNG"


def test_generate_falls_back_to_second_provider(monkeypatch):
    calls = []

    def bad(prompt, negative, w, h):
        calls.append("bad")
        raise RuntimeError("patladı")

    def good(prompt, negative, w, h):
        calls.append("good")
        return _img_bytes(1080, 1350)

    monkeypatch.setattr(generate, "PROVIDERS", {"bad": bad, "good": good})
    monkeypatch.setattr(generate.config, "settings",
                        lambda: {"provider_chain": ["bad", "good"]})
    monkeypatch.setattr(generate.config, "env", lambda k, d="": "")   # PROVIDER override yok

    concept = {"gorsel_prompt": "x", "negatif_prompt": ""}
    style = {"width": 1080, "height": 1350, "style_suffix": "s", "negative_prompt": "n", "post": {}}
    data, used = generate.generate(concept, style)
    assert used == "good"
    assert calls == ["bad", "good"]               # sırayla düştü
    assert Image.open(io.BytesIO(data)).size == (1080, 1350)
