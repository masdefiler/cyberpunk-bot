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


CONCEPT = {"gorsel_prompt": "x", "negatif_prompt": ""}
STYLE = {"width": 1080, "height": 1350, "style_suffix": "s", "negative_prompt": "n", "post": {}}


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
                        lambda: {"provider_chain": ["bad", "good"], "image_retries": 1})
    monkeypatch.setattr(generate.config, "env", lambda k, d="": "")   # PROVIDER override yok

    data, used = generate.generate(CONCEPT, STYLE)
    assert used == "good"
    assert calls == ["bad", "good"]               # sırayla düştü
    assert Image.open(io.BytesIO(data)).size == (1080, 1350)


def test_generate_retries_transient_error(monkeypatch):
    """Geçici 500 → aynı sağlayıcı tekrar denenir ve başarır (canlıda yaşanan hata)."""
    calls = []

    def flaky(prompt, negative, w, h):
        calls.append("try")
        if len(calls) < 3:
            raise RuntimeError("500 Server Error")
        return _img_bytes(1080, 1350)

    monkeypatch.setattr(generate, "PROVIDERS", {"flaky": flaky})
    monkeypatch.setattr(generate.config, "settings",
                        lambda: {"provider_chain": ["flaky"], "image_retries": 3,
                                 "image_retry_backoff": 0})
    monkeypatch.setattr(generate.config, "env", lambda k, d="": "")
    monkeypatch.setattr(generate.time, "sleep", lambda s: None)

    data, used = generate.generate(CONCEPT, STYLE)
    assert used == "flaky"
    assert len(calls) == 3                        # 2 kez patladı, 3.'de tuttu
    assert Image.open(io.BytesIO(data)).size == (1080, 1350)


def test_generate_skips_keyless_provider_without_retrying(monkeypatch):
    """Anahtarı olmayan sağlayıcı tekrar denenmez, hemen sıradakine geçilir."""
    calls = []

    def nokey(prompt, negative, w, h):
        calls.append("nokey")
        raise generate.MissingKey("anahtar yok")

    def good(prompt, negative, w, h):
        calls.append("good")
        return _img_bytes(1080, 1350)

    monkeypatch.setattr(generate, "PROVIDERS", {"nokey": nokey, "good": good})
    monkeypatch.setattr(generate.config, "settings",
                        lambda: {"provider_chain": ["nokey", "good"], "image_retries": 3,
                                 "image_retry_backoff": 0})
    monkeypatch.setattr(generate.config, "env", lambda k, d="": "")
    monkeypatch.setattr(generate.time, "sleep", lambda s: None)

    data, used = generate.generate(CONCEPT, STYLE)
    assert used == "good"
    assert calls == ["nokey", "good"]             # nokey SADECE 1 kez denendi
