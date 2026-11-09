"""Local-only searchable metadata and transcript cues for RMA.

No network calls, LLM calls, or uploads happen in this module.
"""

import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

STAMP = re.compile(r"^\s*(?:\[)?(?P<stamp>(?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d{1,3})?)(?:\])?\s*(?:[-–—:]\s*)?(?P<words>.+?)\s*$")


def connect(db_path):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def setup_schema(db_path):
    with connect(db_path) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS reel_memory (
                reel_id INTEGER PRIMARY KEY REFERENCES reels(id) ON DELETE CASCADE,
                title TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reel_cues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reel_id INTEGER NOT NULL REFERENCES reels(id) ON DELETE CASCADE,
                start_seconds REAL NOT NULL,
                end_seconds REAL,
                text TEXT NOT NULL,
                source TEXT NOT NULL CHECK (source IN ('manual', 'asr'))
            );
            CREATE INDEX IF NOT EXISTS idx_reel_cues_reel_time
                ON reel_cues(reel_id, start_seconds);
        """)


def timestamp_seconds(value):
    chunks = value.split(":")
    if len(chunks) not in (2, 3):
        raise ValueError("Use mm:ss or hh:mm:ss timestamps")
    try:
        digits = [float(x) for x in chunks]
    except ValueError as exc:
        raise ValueError("Timestamp is not numeric") from exc
    if not all(math.isfinite(x) and x >= 0 for x in digits):
        raise ValueError("Invalid timestamp")
    if digits[-1] >= 60 or (len(digits) == 3 and digits[-2] >= 60):
        raise ValueError("Seconds and minutes must be below 60")
    seconds = digits[-1] + 60 * digits[-2]
    if len(digits) == 3:
        seconds += 3600 * digits[0]
    if seconds > 3600:
        raise ValueError("Timestamp exceeds one hour")
    return round(seconds, 3)


def format_time(seconds):
    seconds = max(0, int(float(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def parse_manual_transcript(raw):
    """Parse timestamped lines, or a single untimed transcript at zero seconds."""
    raw = raw.strip()
    if len(raw) > 60000:
        raise ValueError("Transcript exceeds 60,000 characters")
    if not raw:
        return []
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    timed = [STAMP.match(line) for line in lines]
    if not any(timed):
        return [(0.0, None, raw)]
    if not all(timed):
        raise ValueError("Use mm:ss text on every nonblank line, or paste an untimed transcript")
    if len(lines) > 1500:
        raise ValueError("Too many transcript segments")
    cues = []
    for match in timed:
        seconds = timestamp_seconds(match.group("stamp"))
        words = match.group("words").strip()
        if not words:
            raise ValueError("Empty caption segment")
        if cues and seconds < cues[-1][0]:
            raise ValueError("Caption timestamps must be in ascending order")
        cues.append((seconds, None, words))
    return cues


def require_ready_reel(con, reel_id):
    row = con.execute("SELECT * FROM reels WHERE id=? AND status='ready'", (reel_id,)).fetchone()
    if row is None:
        raise ValueError("Reel not found or processing incomplete")
    return row


def set_notes(db_path, reel_id, title, notes):
    title, notes = title.strip(), notes.strip()
    if len(title) > 180 or len(notes) > 12000:
        raise ValueError("Title or notes exceed the maximum length")
    with connect(db_path) as con:
        require_ready_reel(con, reel_id)
        con.execute("""INSERT INTO reel_memory(reel_id,title,notes,updated_at)
            VALUES (?,?,?,?) ON CONFLICT(reel_id) DO UPDATE SET
            title=excluded.title, notes=excluded.notes, updated_at=excluded.updated_at""",
            (reel_id, title, notes, datetime.now(timezone.utc).isoformat()))


def replace_cues(db_path, reel_id, source, cues):
    if source not in ("manual", "asr"):
        raise ValueError("Unknown transcript source")
    cues = list(cues)
    if len(cues) > 1500:
        raise ValueError("Too many transcript segments")
    normalized = []
    previous = -1.0
    for start, end, text in cues:
        start = float(start)
        end = float(end) if end is not None else None
        text = str(text).strip()
        if (not math.isfinite(start) or start < 0 or start > 3600 or
                start < previous or (end is not None and (not math.isfinite(end) or end < start or end > 3600)) or
                not text or len(text) > 5000):
            raise ValueError("Invalid caption timing or text")
        normalized.append((reel_id, start, end, text, source))
        previous = start
    with connect(db_path) as con:
        require_ready_reel(con, reel_id)
        con.execute("DELETE FROM reel_cues WHERE reel_id=? AND source=?", (reel_id, source))
        con.executemany("INSERT INTO reel_cues(reel_id,start_seconds,end_seconds,text,source) VALUES(?,?,?,?,?)", normalized)


def reel_detail(db_path, reel_id):
    with connect(db_path) as con:
        reel = require_ready_reel(con, reel_id)
        memory = con.execute("SELECT title,notes FROM reel_memory WHERE reel_id=?", (reel_id,)).fetchone()
        cues = con.execute("""SELECT id,start_seconds,end_seconds,text,source FROM reel_cues
                              WHERE reel_id=? ORDER BY start_seconds,id""", (reel_id,)).fetchall()
    return dict(reel), (dict(memory) if memory else {"title": "", "notes": ""}), [dict(c) for c in cues]


def search_reels(db_path, query="", limit=100):
    """AND-match search across titles, notes, Reel URLs and transcript segments.

    Returns a timestamp only when an actual caption contains a matching word.
    """
    query = query.strip()
    if len(query) > 160:
        raise ValueError("Search is limited to 160 characters")
    terms = [t.casefold() for t in re.findall(r"[^\W_]+", query, re.UNICODE)]
    if len(terms) > 12:
        raise ValueError("Search has too many terms")
    results = []
    with connect(db_path) as con:
        reels = con.execute("""SELECT r.*,COALESCE(m.title,'') AS title,
            COALESCE(m.notes,'') AS notes FROM reels r
            LEFT JOIN reel_memory m ON m.reel_id=r.id
            WHERE r.status='ready' ORDER BY r.id DESC""").fetchall()
        for reel in reels:
            cues = con.execute("""SELECT start_seconds,text,source FROM reel_cues
                WHERE reel_id=? ORDER BY start_seconds,id""", (reel["id"],)).fetchall()
            corpus = " ".join([reel["title"], reel["notes"], reel["reel_url"],
                               *(cue["text"] for cue in cues)]).casefold()
            if not all(term in corpus for term in terms):
                continue
            cue = next((c for c in cues if terms and all(t in c["text"].casefold() for t in terms)), None)
            item = dict(reel)
            item["cue_count"] = len(cues)
            item["hit_seconds"] = cue["start_seconds"] if cue else None
            item["hit_text"] = cue["text"][:260] if cue else ""
            results.append(item)
            if len(results) >= limit:
                break
    return results


def validated_folder(folder, batches_root):
    """Never serve media based on an arbitrary or tampered SQLite folder value."""
    root = Path(batches_root).resolve()
    path = Path(folder or "").resolve()
    if not folder or not path.is_relative_to(root) or path == root or not path.is_dir():
        raise ValueError("Reel media folder unavailable")
    return path