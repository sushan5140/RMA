# RMA Phase 2 — Searchable Reel Memory

Phase 2 extends the existing local-only Flask importer. **It does not scrape Instagram, download reels, upload media, or use an API key.** Only import recordings you are authorized to keep and analyze.

## What works

- Open `http://127.0.0.1:8765/library` after importing recordings with the existing dashboard.
- Find recordings using title, private notes, URL or caption text. Multiword searches require all words to appear somewhere in that reel's indexed text.
- Edit a title and notes. Paste timestamped manual captions (`00:12 this part matters`) or untimed transcript text.
- See matching caption text and jump to the approximate time in extracted audio. Timestamps are from user-provided captions or model output, not proof of exact frame alignment.
- Preview extracted frames and play extracted audio locally. Original full video is **not** retained in Phase 1.
- Use optional **offline** CPU transcription when the user has installed `faster-whisper` and provided an existing local CTranslate2 Whisper model directory.

## Start (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Install FFmpeg separately and ensure ffmpeg and ffprobe are on PATH.
.\.venv\Scripts\python.exe app.py
```

Open the dashboard, create a batch, import an authorized MP4/MOV/WebM/MKV reel recording, then click **Open Reel Library**.

## Optional transcription (no automatic model downloads)

```powershell
.\.venv\Scripts\python.exe -m pip install faster-whisper
$env:RMA_WHISPER_MODEL_PATH = 'C:\path\to\your\existing\local-ctranslate2-whisper-model'
.\.venv\Scripts\python.exe app.py
```

The automatic transcription button refuses to run unless that local model directory exists. No model is pulled behind the scenes. CPU int8 can be slow on a modest laptop. Users can always paste a transcript without installing an ML dependency. Transcription quality depends on audio, language and model; it is not guaranteed.

## Safety and privacy

- Run only on `127.0.0.1` as the existing `app.py` does; do not expose the server to a network or public host.
- SQLite data, media and browser profiles remain under gitignored `private/`. Back them up yourself if important.
- Phase 2 forms use session-bound CSRF tokens. Private media access checks the path against the batch directory.
- No Instagram credentials, cookies or external video are added to Git or used for tests.
- An empty or no-audio recording is not automatically transcribed. Existing Phase 1 ZIP downloads remain unchanged; notes/captions live in the local database and **are not included in those ZIPs**.
- This phase does not implement Drive OAuth upload or automatic visual scene understanding; those require a separate, consent-aware design.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Test data consists of three synthetic two-second FFmpeg-generated clips. Integration tests require `ffmpeg`, `ffprobe` and Flask, but never contact Instagram. The standard-library storage tests run without Flask.