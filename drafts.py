"""草稿与审批存储 — SQLite 落地,支持高风险消息人工确认"""
import os
import sqlite3
import threading
from datetime import datetime
from typing import Optional

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "drafts.db")

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS drafts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                chat          TEXT NOT NULL,
                sender        TEXT,
                original_msg  TEXT NOT NULL,
                context       TEXT,
                analysis_json TEXT,
                draft_reply   TEXT NOT NULL,
                risk          TEXT NOT NULL,
                status        TEXT NOT NULL DEFAULT 'pending',
                final_reply   TEXT,
                created_at    TEXT NOT NULL,
                decided_at    TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status, created_at);
            """
        )
    return _conn


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_draft(
    chat: str,
    sender: str,
    original_msg: str,
    context: str,
    analysis_json: str,
    draft_reply: str,
    risk: str,
) -> int:
    """落库一条待审批草稿,返回 draft id"""
    with _lock:
        cur = _get_conn().execute(
            """INSERT INTO drafts
               (chat, sender, original_msg, context, analysis_json,
                draft_reply, risk, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (chat, sender, original_msg, context, analysis_json,
             draft_reply, risk, _now()),
        )
        return cur.lastrowid


def list_pending() -> list[dict]:
    rows = _get_conn().execute(
        "SELECT * FROM drafts WHERE status='pending' ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_draft(draft_id: int) -> Optional[dict]:
    row = _get_conn().execute(
        "SELECT * FROM drafts WHERE id=?", (draft_id,)
    ).fetchone()
    return dict(row) if row else None


def decide(draft_id: int, status: str, final_reply: Optional[str] = None) -> bool:
    """status: approved / rejected / sent。final_reply 可改写"""
    if status not in ("approved", "rejected", "sent"):
        return False
    with _lock:
        cur = _get_conn().execute(
            "UPDATE drafts SET status=?, final_reply=?, decided_at=? "
            "WHERE id=? AND status IN ('pending','approved')",
            (status, final_reply, _now(), draft_id),
        )
        return cur.rowcount > 0


def stats() -> dict:
    rows = _get_conn().execute(
        "SELECT status, COUNT(*) AS n FROM drafts GROUP BY status"
    ).fetchall()
    out = {"pending": 0, "approved": 0, "rejected": 0, "sent": 0}
    for r in rows:
        out[r["status"]] = r["n"]
    return out
