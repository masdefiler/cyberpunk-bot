"""state.py — sütun rotasyonu, tekrar önleme, 24s kotası."""
import time

from src.state import State


def test_rotation_advances(tmp_path):
    st = State(tmp_path / "s.db")
    rot = ["A", "B", "C", "D", "E"]
    assert st.next_pillar(rot) == "A"          # başlangıç
    st.mark_pillar_used("A")
    assert st.next_pillar(rot) == "B"
    st.mark_pillar_used("B")
    assert st.next_pillar(rot) == "C"
    st.mark_pillar_used("E")                    # sona atla
    assert st.next_pillar(rot) == "A"           # başa sar


def test_recent_titles_order_and_limit(tmp_path):
    st = State(tmp_path / "s.db")
    for i in range(5):
        st.record_post(pillar="A", title=f"başlık-{i}", status="dry-run")
    recent = st.recent_titles(limit=3)
    assert recent == ["başlık-4", "başlık-3", "başlık-2"]   # en yeniden eskiye


def test_count_last_24h_only_counts_published(tmp_path):
    st = State(tmp_path / "s.db")
    st.record_post(pillar="A", title="x", status="published")
    st.record_post(pillar="B", title="y", status="published")
    st.record_post(pillar="C", title="z", status="dry-run")   # sayılmaz
    st.record_post(pillar="D", title="w", status="failed")    # sayılmaz
    assert st.count_last_24h(("published",)) == 2


def test_old_posts_excluded_from_24h(tmp_path):
    st = State(tmp_path / "s.db")
    pid = st.record_post(pillar="A", title="eski", status="published")
    # created_at'i 25 saat öncesine çek
    with st._conn() as conn:
        conn.execute("UPDATE posts SET created_at = ? WHERE id = ?",
                     (time.time() - 25 * 3600, pid))
    assert st.count_last_24h(("published",)) == 0


def test_update_post_roundtrip(tmp_path):
    st = State(tmp_path / "s.db")
    pid = st.record_post(pillar="A", title="t", status="draft")
    st.update_post(pid, media_id="123", status="published")
    with st._conn() as conn:
        row = conn.execute("SELECT media_id, status FROM posts WHERE id = ?", (pid,)).fetchone()
    assert row["media_id"] == "123"
    assert row["status"] == "published"
