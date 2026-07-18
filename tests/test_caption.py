"""caption.py — hashtag adedi, tekilsizlik, ayraç, kurgu metni."""
from src import caption


CONCEPT = {
    "konsept_basligi": "Neon Şehir",
    "kisa_kurgu_metin": "Yağmur hiç dinmedi.",
    "hashtag_onerileri": ["ozelbir", "konsept"],
}


def test_hashtag_count_in_range():
    for _ in range(30):                          # rastgele — çok kez dene
        cap = caption.build_caption(CONCEPT)
        n = cap.count("#")
        assert 15 <= n <= 25


def test_hashtags_unique():
    cap = caption.build_caption(CONCEPT)
    tags = [w for w in cap.split() if w.startswith("#")]
    lowered = [t.lower() for t in tags]
    assert len(lowered) == len(set(lowered))     # tekrar yok


def test_fiction_first_and_separator_present():
    cap = caption.build_caption(CONCEPT)
    assert cap.splitlines()[0] == "Yağmur hiç dinmedi."
    assert caption.SEPARATOR in cap


def test_suggested_tags_can_appear():
    # 30 denemede özel önerilerden en az biri görünmeli
    seen = set()
    for _ in range(30):
        cap = caption.build_caption(CONCEPT)
        seen.update(w.lower() for w in cap.split() if w.startswith("#"))
    assert "#ozelbir" in seen or "#konsept" in seen
