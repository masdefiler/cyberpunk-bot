"""Kalıcı durum: SQLite üzerinde sütun rotasyonu, tekrar önleme ve 24s kotası.

Tek sorumluluk: "sırada hangi sütun var, son üretilen başlıklar neydi, son 24
saatte kaç gönderi yayınladık" sorularını cevaplamak. Pipeline bununla konuşur.
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

# Repo kökü (src/'in bir üstü). DB varsayılan olarak burada durur.
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "state.db"


class State:
    """SQLite tabanlı durum deposu. Bağlantı her işlemde açılıp kapanır (Actions dostu)."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at  REAL    NOT NULL,   -- epoch saniye
                    date_iso    TEXT    NOT NULL,   -- okunabilir tarih
                    pillar      TEXT    NOT NULL,   -- A/B/C/D/E
                    title       TEXT    NOT NULL,   -- konsept başlığı (dedup anahtarı)
                    prompt      TEXT,               -- kullanılan görsel prompt
                    image_path  TEXT,               -- yerel/commit yolu
                    image_url   TEXT,               -- barındırılan public URL
                    media_id    TEXT,               -- Instagram media id
                    status      TEXT    NOT NULL    -- draft/published/dry-run/failed
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )

    # ---- Sütun rotasyonu ---------------------------------------------------
    def next_pillar(self, rotation: list[str]) -> str:
        """Rotasyondaki son kullanılan sütunun BİR sonrasını döndürür (dizinden okumaz).

        Sadece sıradakini hesaplar; kullanıldı olarak işaretlemek için
        `mark_pillar_used` çağrılır (gönderi başarıyla üretilince).
        """
        if not rotation:
            raise ValueError("rotation boş olamaz")
        last = self.get_meta("last_pillar")
        if last is None or last not in rotation:
            return rotation[0]
        idx = rotation.index(last)
        return rotation[(idx + 1) % len(rotation)]

    def mark_pillar_used(self, pillar: str) -> None:
        self.set_meta("last_pillar", pillar)

    # ---- Tekrar önleme -----------------------------------------------------
    def recent_titles(self, limit: int = 50) -> list[str]:
        """En son üretilen `limit` kadar konsept başlığı (yeniden eskiye)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT title FROM posts ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [r["title"] for r in rows]

    # ---- 24 saat kotası ----------------------------------------------------
    def count_last_24h(self, statuses: tuple[str, ...] = ("published",)) -> int:
        """Son 24 saatte verilen statülerdeki gönderi sayısı (limit kontrolü)."""
        cutoff = time.time() - 24 * 3600
        placeholders = ",".join("?" for _ in statuses)
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS n FROM posts "
                f"WHERE created_at >= ? AND status IN ({placeholders})",
                (cutoff, *statuses),
            ).fetchone()
        return int(row["n"])

    # ---- Kayıt yazma -------------------------------------------------------
    def record_post(
        self,
        *,
        pillar: str,
        title: str,
        prompt: str = "",
        image_path: str = "",
        image_url: str = "",
        media_id: str = "",
        status: str = "draft",
    ) -> int:
        """Bir gönderiyi kaydeder, satır id'sini döndürür."""
        now = time.time()
        date_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now))
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO posts
                    (created_at, date_iso, pillar, title, prompt,
                     image_path, image_url, media_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (now, date_iso, pillar, title, prompt,
                 image_path, image_url, media_id, status),
            )
            return int(cur.lastrowid)

    def update_post(self, post_id: int, **fields: str) -> None:
        """Var olan gönderi satırının alanlarını günceller (media_id, status ...)."""
        if not fields:
            return
        allowed = {"prompt", "image_path", "image_url", "media_id", "status"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        clause = ", ".join(f"{k} = ?" for k in sets)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE posts SET {clause} WHERE id = ?",
                (*sets.values(), post_id),
            )

    # ---- meta anahtar/değer ------------------------------------------------
    def get_meta(self, key: str) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
