import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, redirect, render_template_string, request, send_file, url_for
from werkzeug.utils import secure_filename

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "private"
BATCHES = DATA / "batches"
DATA.mkdir(exist_ok=True)
BATCHES.mkdir(exist_ok=True)
DB = DATA / "data.sqlite3"
MAX_BYTES = 250 * 1024 * 1024
INTERVAL = max(.2, float(os.environ.get("FRAME_INTERVAL", "1")))
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_BYTES
EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}

def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def setup():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS batches (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reels (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          batch_id INTEGER NOT NULL,
          reel_url TEXT NOT NULL,
          status TEXT NOT NULL,
          folder TEXT,
          error TEXT,
          created_at TEXT NOT NULL,
          UNIQUE(batch_id, reel_url),
          FOREIGN KEY(batch_id) REFERENCES batches(id)
        );
        """)

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def validate_reel_url(value):
    parsed = urlparse(value.strip())
    hostname = (parsed.hostname or "").lower()
    match = re.fullmatch(r"/reel/([A-Za-z0-9_-]+)/*", parsed.path)
    if parsed.scheme != "https" or hostname not in ("instagram.com", "www.instagram.com") or not match:
        raise ValueError("Use a full https://www.instagram.com/reel/SHORTCODE/ URL")
    return "https://www.instagram.com/reel/" + match.group(1) + "/"

def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=300)

def probe(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                           "-of", "json", str(path)]).stdout)

PAGE = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>RMA — Local reel research</title><style>
:root{font-family:Inter,ui-sans-serif,system-ui,sans-serif;color:#171717;background:#f7f7f5}
*{box-sizing:border-box}body{max-width:1040px;margin:0 auto;padding:36px 20px}
h1{font-size:34px;letter-spacing:-1.5px;margin:0}p{color:#656565}
.card{background:#fff;border:1px solid #e7e7e5;border-radius:18px;padding:22px;margin:18px 0}
input,select,button{font:inherit;padding:12px;border:1px solid #ddd;border-radius:10px}
input[type=url]{width:100%}input[type=file]{max-width:100%}
button,.button{background:#171717;color:white;border:0;cursor:pointer;text-decoration:none;display:inline-block;padding:12px 16px;border-radius:10px}
.row{display:flex;flex-wrap:wrap;gap:12px;align-items:center}
form{display:grid;gap:13px;margin-top:12px}.muted{font-size:13px;color:#777}
li{margin:12px 0}a{color:#171717}code{background:#f2f2f2;padding:3px 6px;border-radius:5px}
.tag{background:#f0f0ee;border-radius:20px;padding:4px 9px;font-size:12px}
</style></head><body><div class=row><h1>RMA</h1><span class=tag>Local-only · Phase 1</span></div>
<p>Reel research capture → timestamped frames + audio → batches for ChatGPT review.</p>
<div class=card><h2>Create batch</h2><form method=post action="/batches"><button>Create new batch</button></form></div>
<div class=card><h2>Import a reel recording</h2><p class=muted>Record only media you are authorized to capture. This app does not scrape Instagram.</p>
<form method=post action="/reels" enctype=multipart/form-data>
<label>Batch <select name=batch_id required>{% for b in batches %}<option value="{{b.id}}">Batch_{{'%03d'|format(b.id)}}</option>{% endfor %}</select></label>
<label>Original Reel URL <input type=url name=reel_url placeholder="https://www.instagram.com/reel/..." required></label>
<label>Video recording (MP4 / MOV / WEBM / MKV; max 250 MB) <input type=file name=video accept=".mp4,.mov,.webm,.mkv" required></label>
<button {% if not batches %}disabled{% endif %}>Extract and save</button></form></div>
{% for b in batches %}<div class=card><div class=row><h2>Batch_{{'%03d'|format(b.id)}}</h2><a class=button href="/batches/{{b.id}}/download">Download ZIP</a></div>
<ul>{% for reel in reels if reel.batch_id==b.id %}<li><a href="{{reel.reel_url}}" target=_blank rel="noopener noreferrer">{{reel.reel_url}}</a>
<span class=tag>{{reel.status}}</span>{% if reel.error %}<span class=muted>{{reel.error}}</span>{% endif %}</li>{% else %}<li class=muted>No reels yet</li>{% endfor %}</ul></div>{% endfor %}
<p class=muted>Browser login stays on your own machine. Private files are excluded from Git. Upload batch ZIPs to Drive for ChatGPT analysis.</p>
</body></html>
"""

@app.get("/")
def index():
    with connect() as con:
        batches = con.execute("SELECT * FROM batches ORDER BY id DESC").fetchall()
        reels = con.execute("SELECT * FROM reels ORDER BY id DESC").fetchall()
    return render_template_string(PAGE, batches=batches, reels=reels)

@app.post("/batches")
def new_batch():
    with connect() as con:
        con.execute("INSERT INTO batches(created_at) VALUES(?)", (utcnow(),))
    return redirect(url_for("index"))

@app.post("/reels")
def new_reel():
    try:
        batch_id = int(request.form["batch_id"])
        reel_url = validate_reel_url(request.form["reel_url"])
        upload = request.files["video"]
        if not upload or Path(secure_filename(upload.filename or "")).suffix.lower() not in EXTENSIONS:
            raise ValueError("Unsupported video file extension.")
        with connect() as con:
            if not con.execute("SELECT 1 FROM batches WHERE id=?", (batch_id,)).fetchone():
                raise ValueError("Batch does not exist")
            exists = con.execute("SELECT 1 FROM reels WHERE reel_url=? AND status='ready'", (reel_url,)).fetchone()
            if exists:
                raise ValueError("This reel has already been processed. Check existing batches.")
            cursor = con.execute("INSERT INTO reels(batch_id,reel_url,status,created_at) VALUES(?,?,?,?)",
                                 (batch_id, reel_url, "processing", utcnow()))
            reel_id = cursor.lastrowid
    except (ValueError, KeyError, sqlite3.IntegrityError) as exc:
        return f"Import rejected: {exc}", 400

    folder = BATCHES / f"Batch_{batch_id:03d}" / f"Reel_{reel_id:03d}"
    folder.mkdir(parents=True, exist_ok=False)
    suffix = Path(secure_filename(upload.filename)).suffix.lower()
    input_file = folder / ("source" + suffix)
    try:
        upload.save(input_file)
        info = probe(input_file)
        streams = info.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        if video is None:
            raise ValueError("Recording contains no video stream")
        duration = float(info.get("format", {}).get("duration", 0))
        if duration <= 0 or duration > 3600:
            raise ValueError("Recording duration must be between 0 and 3600 seconds")
        frame_dir = folder / "frames"
        frame_dir.mkdir()
        # FPS filter uses decoder timestamps; frame index maps to approximate seconds.
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(input_file),
             "-vf", f"fps=1/{INTERVAL}", "-q:v", "3", str(frame_dir / "%05d.jpg"), "-y"])
        frames = sorted(frame_dir.glob("*.jpg"))
        if not frames:
            raise ValueError("No frames were extracted")
        timestamps = [{"name": p.name, "approx_seconds": round(i * INTERVAL, 3)}
                      for i, p in enumerate(frames)]
        if has_audio:
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(input_file),
                 "-vn", "-c:a", "aac", "-b:a", "128k", str(folder / "audio.m4a"), "-y"])
        metadata = {
            "reel_url": reel_url, "captured_at": utcnow(), "duration_seconds": duration,
            "has_audio": has_audio, "frame_interval_seconds": INTERVAL,
            "frames": timestamps, "capture_method": "user_uploaded_recording",
            "status": "ready", "caveat": "Frame timestamps are approximate; reel may include recorder UI."
        }
        (folder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        # Do not retain full video by default; keeps Drive exports lighter.
        input_file.unlink()
        with connect() as con:
            con.execute("UPDATE reels SET status='ready',folder=? WHERE id=?", (str(folder), reel_id))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, OSError) as exc:
        with connect() as con:
            con.execute("UPDATE reels SET status='failed',error=? WHERE id=?",
                        (str(exc)[:300], reel_id))
        return f"Processing failed: {exc}", 422
    return redirect(url_for("index"))

@app.get("/batches/<int:batch_id>/download")
def download_batch(batch_id):
    with connect() as con:
        batch = con.execute("SELECT 1 FROM batches WHERE id=?", (batch_id,)).fetchone()
        rows = con.execute("SELECT * FROM reels WHERE batch_id=?", (batch_id,)).fetchall()
    if not batch:
        abort(404)
    manifest = {"batch_id": batch_id,
                "reels": [{"url": row["reel_url"], "status": row["status"],
                           "folder": (Path(row["folder"]).name if row["folder"] else None)}
                          for row in rows]}
    temp = tempfile.TemporaryFile()
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
        for row in rows:
            if row["status"] == "ready" and row["folder"]:
                folder = Path(row["folder"])
                if folder.is_dir() and folder.resolve().is_relative_to(BATCHES.resolve()):
                    for file in folder.rglob("*"):
                        if file.is_file():
                            z.write(file, f"{folder.name}/{file.relative_to(folder)}")
    temp.seek(0)
    return send_file(temp, mimetype="application/zip", as_attachment=True,
                     download_name=f"Batch_{batch_id:03d}.zip")

if __name__ == "__main__":
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("Install FFmpeg and ensure ffmpeg and ffprobe are on PATH.")
    setup()
    print("Open http://127.0.0.1:8765")
    app.run(host="127.0.0.1", port=8765, debug=False)
