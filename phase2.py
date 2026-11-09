"""RMA Phase 2: local searchable Reel Library and optional offline transcription.

Call register_phase2(app, db_path, batches_root) from the existing Flask app.
All media stays on loopback, and ASR requires a user-provided local model.
"""

import hmac
import json
import os
import re
import secrets
from pathlib import Path

from flask import abort, redirect, render_template_string, request, send_file, session, url_for

from reel_memory import (format_time, parse_manual_transcript, reel_detail,
                         replace_cues, search_reels, set_notes, validated_folder)

STYLE = """
<style>
:root{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif;background:#0c1220;color:#f1f5ff}
*{box-sizing:border-box}body{max-width:1040px;margin:0 auto;padding:24px 18px 80px}
a{color:#8bd9ff}h1{font-size:clamp(28px,5vw,45px);letter-spacing:-1.4px}
p,.hint{color:#a6b3ca;line-height:1.55}.eyebrow{text-transform:uppercase;letter-spacing:2px;color:#64e6cb;font-weight:700;font-size:12px}
.panel{background:#151e30;border:1px solid #293850;border-radius:18px;padding:20px;margin:17px 0}
input,textarea,button{font:inherit;border-radius:10px;padding:11px 13px}input,textarea{background:#0a1424;color:#fff;border:1px solid #42516a;width:100%}textarea{min-height:140px;resize:vertical}
button,.action{background:#5cd8c2;color:#041b1f;border:none;cursor:pointer;font-weight:700;display:inline-block;text-decoration:none;padding:11px 15px;border-radius:10px}
.secondary{background:#283750;color:#e5f0ff}.row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}
.card{background:#111a2b;border:1px solid #293850;border-radius:16px;padding:18px;min-width:0}
small,.tag{color:#a6b3ca;font-size:12px}.tag{display:inline-block;border:1px solid #47617b;border-radius:20px;padding:3px 9px}
form{display:grid;gap:10px}.cue{padding:14px 0;border-bottom:1px solid #2b364c}.cue:last-child{border:0}
.code{font-family:ui-monospace,monospace}img{width:100%;border-radius:10px;object-fit:cover;max-height:160px}
</style>
"""

LIBRARY = """<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>RMA · Reel Library</title>""" + STYLE + """</head><body>
<div class=eyebrow>RMA / Phase 2 / Local-only</div><div class=row><h1>Reel Library</h1><a href='/' class='action secondary'>← Import recordings</a></div>
<p>Search your own imported reels by title, notes or spoken words. No scraping and no cloud processing.</p>
<div class=panel><form method=get action='/library'><label for=q>Search memory</label>
<div class=row><input style='flex:1' id=q type=search name=q value='{{query}}' placeholder='Korean universities, recipes, exam tips…' maxlength=160>
<button>Find reels</button></div></form></div>
{% if error %}<div class=panel role=alert>{{error}}</div>{% endif %}
<p>{{reels|length}} matching imported reel(s){% if query %} for “{{query}}”{% endif %}</p>
<div class=grid>{% for reel in reels %}
<article class=card><div class=row><span class=tag>Batch {{'%03d'|format(reel.batch_id)}}</span><span class=tag>{{reel.cue_count}} caption cues</span></div>
<h2><a href='{{url_for("rma_reel_detail", reel_id=reel.id)}}'>{{reel.title or ('Reel ' ~ reel.id)}}</a></h2>
<p>{{reel.notes[:230] or 'No notes yet — open this reel to add information.'}}</p>
{% if reel.hit_text %}<p><small>Caption {% if reel.hit_seconds is not none %}{{format_time(reel.hit_seconds)}}{% endif %}:</small> {{reel.hit_text}}</p>{% endif %}
<div class=row><a class=action href='{{url_for("rma_reel_detail", reel_id=reel.id)}}{% if reel.hit_seconds is not none %}?at={{reel.hit_seconds}}{% endif %}'>Open {% if reel.hit_seconds is not none %}at {{format_time(reel.hit_seconds)}}{% endif %}</a>
<a href='{{reel.reel_url}}' target=_blank rel='noopener noreferrer'>Original ↗</a></div></article>
{% else %}<div class=panel>No matches. Import a recording first, or add notes/captions to an existing reel.</div>{% endfor %}</div>
</body></html>"""

DETAIL = """<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>RMA · Reel details</title>""" + STYLE + """</head><body>
<div class=eyebrow>RMA / Local reel detail</div><p><a href='{{url_for("rma_library")}}'>← Back to library</a></p>
<h1>{{memory.title or ('Reel ' ~ reel.id)}}</h1><p><a href='{{reel.reel_url}}' target=_blank rel='noopener noreferrer'>Open original reel ↗</a> · Batch {{'%03d'|format(reel.batch_id)}}</p>
{% if has_audio %}<div class=panel><p>Local extracted audio · timestamps are approximate</p>
<audio id=player controls preload=none style='width:100%' src='{{url_for("rma_audio",reel_id=reel.id)}}'></audio>
</div>{% else %}<p>No audio was extracted for this recording.</p>{% endif %}
<div class=grid><section class=panel><h2>Title and notes</h2>
<form method=post action='{{url_for("rma_notes",reel_id=reel.id)}}'><input type=hidden name=csrf value='{{csrf}}'>
<label>Title <input name=title maxlength=180 value='{{memory.title}}'></label>
<label>Notes <textarea name=notes maxlength=12000 placeholder='Add what mattered…'>{{memory.notes}}</textarea></label>
<button>Save notes</button></form></section>
<section class=panel><h2>Transcript</h2><p class=hint>Paste one timestamped caption per line, e.g. <span class=code>00:12 Korean universities</span>. Untimed text is searchable but won't have accurate navigation.</p>
<form method=post action='{{url_for("rma_manual",reel_id=reel.id)}}'><input type=hidden name=csrf value='{{csrf}}'>
<textarea name=transcript maxlength=60000 placeholder='00:12 Korean universities&#10;00:25 Scholarships…'>{{manual_transcript}}</textarea>
<button>Save manual captions</button></form>
<p class=hint>Optional automatic transcription is fully local; requires <code>faster-whisper</code> and a model directory configured on your machine.</p>
<form method=post action='{{url_for("rma_transcribe",reel_id=reel.id)}}'><input type=hidden name=csrf value='{{csrf}}'><button class=secondary {% if not has_audio %}disabled{% endif %}>Transcribe local audio</button></form></section></div>
{% if frames %}<section class=panel><h2>Sampled frames</h2><div class=grid>{% for frame in frames %}
<div><a href='{{url_for("rma_frame",reel_id=reel.id,name=frame.name)}}' target=_blank rel=noopener><img loading=lazy alt='Reel frame at approximately {{format_time(frame.approx_seconds)}}' src='{{url_for("rma_frame",reel_id=reel.id,name=frame.name)}}'></a><small>{{format_time(frame.approx_seconds)}} approximate</small></div>{% endfor %}</div></section>{% endif %}
<section class=panel><h2>Caption timeline ({{cues|length}})</h2>
{% for cue in cues %}<div class=cue id='cue{{cue.id}}'><div class=row>
<button type=button class=secondary data-seek='{{cue.start_seconds}}'>{{format_time(cue.start_seconds)}}</button><span class=tag>{{cue.source}}</span></div>
<p>{{cue.text}}</p></div>{% else %}<p>No captions yet. Paste a transcript above or configure local transcription.</p>{% endfor %}
</section><script>
const player=document.getElementById('player');
function seek(t){if(player){player.currentTime=t;player.play().catch(()=>{});}}
document.querySelectorAll('[data-seek]').forEach(b=>b.addEventListener('click',()=>seek(Number(b.dataset.seek))));
const start=new URLSearchParams(location.search).get('at');if(start!==null&&Number.isFinite(Number(start)))seek(Number(start));
</script></body></html>"""


def offline_transcribe(audio_path):
    """Never downloads models or sends the audio to a third-party provider."""
    model_dir = os.environ.get("RMA_WHISPER_MODEL_PATH", "").strip()
    if not model_dir or not Path(model_dir).is_dir():
        raise ValueError("Set RMA_WHISPER_MODEL_PATH to an existing local model directory")
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ValueError("Install optional local dependency: pip install faster-whisper") from exc
    model = WhisperModel(model_dir, device="cpu", compute_type="int8", local_files_only=True)
    segments, _ = model.transcribe(str(audio_path), beam_size=1, vad_filter=True)
    return [(seg.start, seg.end, seg.text.strip()) for seg in segments if seg.text.strip()]


def register_phase2(app, db_path, batches_root):
    """Add Phase 2 routes to the existing Flask app without changing Phase 1 media extraction."""
    app.secret_key = secrets.token_bytes(32)

    def csrf_token():
        if "_rma_csrf" not in session:
            session["_rma_csrf"] = secrets.token_urlsafe(32)
        return session["_rma_csrf"]

    def check_csrf():
        expected = session.get("_rma_csrf", "")
        provided = request.form.get("csrf", "")
        if not expected or not hmac.compare_digest(expected, provided):
            abort(403)

    def read_detail(reel_id):
        try:
            return reel_detail(db_path, reel_id)
        except ValueError:
            abort(404)

    def media_folder(reel):
        try:
            return validated_folder(reel["folder"], batches_root)
        except ValueError:
            abort(404)

    @app.after_request
    def library_privacy_headers(response):
        if request.path.startswith("/library"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/library", endpoint="rma_library")
    def library():
        query = request.args.get("q", "")
        try:
            results = search_reels(db_path, query)
            error = ""
        except ValueError as exc:
            results, error = [], str(exc)
        return render_template_string(LIBRARY, reels=results, query=query[:160],
                                      error=error, format_time=format_time)

    @app.get("/library/<int:reel_id>", endpoint="rma_reel_detail")
    def detail(reel_id):
        reel, memory, cues = read_detail(reel_id)
        folder = media_folder(reel)
        try:
            metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
            frames = [f for f in metadata.get("frames", []) if re.fullmatch(r"\d{5}\.jpg", str(f.get("name", "")))][:12]
        except (OSError, ValueError, TypeError, AttributeError):
            frames = []
        manual = [f"{format_time(c['start_seconds'])} {c['text']}" for c in cues if c["source"] == "manual"]
        return render_template_string(DETAIL, reel=reel, memory=memory, cues=cues,
                                      manual_transcript="\n".join(manual), frames=frames,
                                      has_audio=(folder / "audio.m4a").is_file(),
                                      format_time=format_time, csrf=csrf_token())

    @app.post("/library/<int:reel_id>/notes", endpoint="rma_notes")
    def notes(reel_id):
        check_csrf()
        try:
            set_notes(db_path, reel_id, request.form.get("title", ""), request.form.get("notes", ""))
        except ValueError as exc:
            return str(exc), 400
        return redirect(url_for("rma_reel_detail", reel_id=reel_id))

    @app.post("/library/<int:reel_id>/transcript", endpoint="rma_manual")
    def manual(reel_id):
        check_csrf()
        try:
            cues = parse_manual_transcript(request.form.get("transcript", ""))
            replace_cues(db_path, reel_id, "manual", cues)
        except ValueError as exc:
            return str(exc), 400
        return redirect(url_for("rma_reel_detail", reel_id=reel_id))

    @app.post("/library/<int:reel_id>/transcribe", endpoint="rma_transcribe")
    def transcribe(reel_id):
        check_csrf()
        reel, _, _ = read_detail(reel_id)
        audio = media_folder(reel) / "audio.m4a"
        if not audio.is_file():
            abort(404)
        try:
            cues = offline_transcribe(audio)
            replace_cues(db_path, reel_id, "asr", cues)
        except ValueError as exc:
            return str(exc), 400
        return redirect(url_for("rma_reel_detail", reel_id=reel_id))

    @app.get("/library/<int:reel_id>/audio", endpoint="rma_audio")
    def audio(reel_id):
        reel, _, _ = read_detail(reel_id)
        path = media_folder(reel) / "audio.m4a"
        if not path.is_file():
            abort(404)
        return send_file(path, mimetype="audio/mp4", conditional=True)

    @app.get("/library/<int:reel_id>/frame/<name>", endpoint="rma_frame")
    def frame(reel_id, name):
        if not re.fullmatch(r"\d{5}\.jpg", name):
            abort(404)
        reel, _, _ = read_detail(reel_id)
        path = media_folder(reel) / "frames" / name
        if not path.is_file() or path.is_symlink():
            abort(404)
        return send_file(path, mimetype="image/jpeg", conditional=True)