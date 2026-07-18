"""ideate.py — JSON parse/validate + anahtarsız şablon fallback."""
import pytest

from src import ideate, config


def test_parse_json_plain():
    assert ideate._parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_code_fence():
    raw = '```json\n{"a": 1, "b": "x"}\n```'
    assert ideate._parse_json(raw) == {"a": 1, "b": "x"}


def test_parse_json_with_surrounding_text():
    raw = 'İşte fikir:\n{"a": 1}\nUmarım beğenirsin'
    assert ideate._parse_json(raw) == {"a": 1}


def test_validate_requires_all_keys():
    with pytest.raises(ValueError):
        ideate._validate({"konsept_basligi": "x"})


def test_validate_normalizes_hashtags_from_string():
    data = {
        "konsept_basligi": "Başlık",
        "gorsel_prompt": "a scene",
        "negatif_prompt": "",
        "kisa_kurgu_metin": "kurgu",
        "hashtag_onerileri": "#cyberpunk, neon  future",
    }
    out = ideate._validate(data)
    assert out["hashtag_onerileri"] == ["cyberpunk", "neon", "future"]


def test_validate_rejects_empty_title():
    with pytest.raises(ValueError):
        ideate._validate({
            "konsept_basligi": "  ",
            "gorsel_prompt": "x",
            "negatif_prompt": "",
            "kisa_kurgu_metin": "y",
            "hashtag_onerileri": [],
        })


def test_template_fallback_valid_for_all_pillars():
    pillars = config.pillars()["pillars"]
    for key, pillar in pillars.items():
        out = ideate._template_fallback(key, pillar, [])
        for req in ideate.REQUIRED_KEYS:
            assert req in out
        assert out["konsept_basligi"]
        assert out["gorsel_prompt"]


def test_template_fallback_avoids_recent(monkeypatch):
    # A sütununun ilk şablon başlığını "yakın zamanda üretildi" say
    first = ideate._TEMPLATES["A"][0]["konsept_basligi"]
    out = ideate._template_fallback("A", {}, [first])
    assert out["konsept_basligi"] != first


def test_ideate_forced_template(monkeypatch):
    # IDEATE_PROVIDER=template → zincir sadece şablon, ağ'a gitmez
    monkeypatch.setattr(config, "env",
                        lambda k, d="": "template" if k == "IDEATE_PROVIDER" else "")
    out = ideate.ideate("B", config.pillars()["pillars"]["B"], [])
    assert out["konsept_basligi"]
    assert "gorsel_prompt" in out


def test_ideate_gemini_used(monkeypatch):
    import json as _json

    concept = {
        "konsept_basligi": "Gemini Konsept",
        "gorsel_prompt": "a scene",
        "negatif_prompt": "",
        "kisa_kurgu_metin": "kurgu",
        "hashtag_onerileri": ["a", "b"],
    }
    monkeypatch.setattr(config, "env", lambda k, d="":
                        {"IDEATE_PROVIDER": "gemini", "GEMINI_API_KEY": "K"}.get(k, ""))

    class R:
        status_code = 200
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": _json.dumps(concept)}]}}]}

    monkeypatch.setattr(ideate.requests, "post", lambda *a, **k: R())
    out = ideate.ideate("A", config.pillars()["pillars"]["A"], [])
    assert out["konsept_basligi"] == "Gemini Konsept"


def test_ideate_chain_falls_through_to_template(monkeypatch):
    # anahtar yok → gemini eler; pollinations ağ hatası → şablona düşer (ağsız)
    monkeypatch.setattr(config, "env", lambda k, d="": "")

    def boom(*a, **k):
        raise RuntimeError("net down")

    monkeypatch.setattr(ideate.requests, "post", boom)
    out = ideate.ideate("C", config.pillars()["pillars"]["C"], [])
    # C sütununun şablonlarından birine düşmeli
    c_titles = [o["konsept_basligi"] for o in ideate._TEMPLATES["C"]]
    assert out["konsept_basligi"] in c_titles
    for req in ideate.REQUIRED_KEYS:
        assert req in out
