"""pipeline.py — dry-run önizleme yazımı + 24s kota kısa devresi (ağsız)."""
import io

from PIL import Image

from src import pipeline
from src.state import State


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (1080, 1350), (20, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


CONCEPT = {
    "konsept_basligi": "Test Konsept",
    "kart_baslik": "Test kart başlığı",
    "kart_fayda": "Test fayda cümlesi.",
    "gorsel_prompt": "a test scene",
    "negatif_prompt": "",
    "caption_metin": "Bir test açıklaması.",
    "hashtag_onerileri": ["test"],
}


def _isolate(monkeypatch, tmp_path):
    from src import state as state_mod
    monkeypatch.setattr(state_mod, "DEFAULT_DB", tmp_path / "s.db")
    monkeypatch.setattr(pipeline, "PREVIEW_DIR", tmp_path / "preview")


def test_dry_run_writes_preview_and_records(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(pipeline, "ideate", lambda *a, **k: dict(CONCEPT))
    monkeypatch.setattr(pipeline, "generate", lambda *a, **k: (_png(), "fake"))

    result = pipeline.run_once(dry_run=True)

    assert result["status"] == "dry-run"
    assert result["provider"] == "fake"
    # önizleme dosyaları yazıldı
    pngs = list((tmp_path / "preview").glob("*.png"))
    txts = list((tmp_path / "preview").glob("*.txt"))
    assert len(pngs) == 1 and len(txts) == 1
    # state'e dry-run kaydı düştü + sütun ilerledi
    st = State(tmp_path / "s.db")
    assert st.recent_titles(1) == ["Test Konsept"]
    assert st.get_meta("last_pillar") == result["pillar"]


def test_publish_skips_when_24h_full(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    st = State(tmp_path / "s.db")
    for i in range(45):                          # settings.max_per_24h = 45
        st.record_post(pillar="A", title=f"p{i}", status="published")

    # ideate/generate çağrılırsa test patlamalı (kota önce kesmeli)
    def _boom(*a, **k):
        raise AssertionError("kota dolu iken üretim çağrılmamalı")
    monkeypatch.setattr(pipeline, "ideate", _boom)
    monkeypatch.setattr(pipeline, "generate", _boom)

    result = pipeline.run_once(dry_run=False)
    assert result["status"] == "skipped_limit"


def test_failure_marks_row_and_keeps_pillar(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(pipeline, "ideate", lambda *a, **k: dict(CONCEPT))

    def _fail(*a, **k):
        raise RuntimeError("üretim patladı")
    monkeypatch.setattr(pipeline, "generate", _fail)

    import pytest
    with pytest.raises(RuntimeError):
        pipeline.run_once(dry_run=True)

    st = State(tmp_path / "s.db")
    # sütun ilerlememeli (başarısızlıkta rotasyon sabit kalır)
    assert st.get_meta("last_pillar") is None
