# RMA — Reel Memory Agent

Local-first Instagram research capture. **Phase 1 MVP:** a local dashboard for importing a reel recording you made/are authorized to use, extracting its original audio and timestamped frames, organizing batches, and exporting them for review in ChatGPT/Google Drive.

This is **not** an Instagram scraper. Instagram cannot be embedded reliably in an external website; the included launcher opens a separate persistent Chromium window and you sign in yourself. No password, session cookie, browser profile, video, or audio is committed.

## Setup (Windows)

1. Install Python 3.10+ and [FFmpeg](https://ffmpeg.org/download.html) (both `ffmpeg` and `ffprobe` on PATH).
2. In PowerShell:
   ```powershell
   git clone https://github.com/sushan5140/RMA.git
   cd RMA
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python app.py
   ```
3. Open **http://127.0.0.1:8765**. Create a batch, enter the Reel URL, and import an MP4/MOV/WEBM recording you captured with permission. Save a reel before adding another.
4. Download the ZIP for a batch and upload it to a Google Drive folder for analysis here.

### Optional Instagram-only window

```powershell
python -m playwright install chromium
python launch_instagram.py
```

This opens a *local* persistent browser profile in `private/browser-profile/`. Log in directly to Instagram. Use a user-initiated recording tool to capture media you are authorized to record; then import the file in RMA.

### Outputs

```text
private/
  data.sqlite3
  batches/
    Batch_001/
      Reel_001/
        audio.m4a
        frames/00-00-00.000.jpg ...
        metadata.json
```

Each reel records the original URL, duration, capture sampling interval, audio presence, frame timestamps, and processing status. The `Batch_001.zip` download contains a manifest and all processed files. Defaults sample frames at 1 FPS; adjust `FRAME_INTERVAL` in your local environment (seconds) for finer sampling.

**Important:** An uploaded recording may have no audio; the app detects this and marks it in metadata. RMA does not claim complete frame-by-frame understanding, transcription, or Drive upload yet. Phase 2 will connect OAuth Drive upload after end-to-end local testing. Do not expose this local HTTP dashboard on the public internet.

### Safety & limits

- No Instagram credential storage in the app/database (the optional browser's persistent profile remains on your device).
- Only recordings you have the right to capture. Observe Instagram platform rules.
- No autonomous scrolling or capture of Instagram feeds in this version.
- Local file size limit is 250 MiB per import. Keep enough disk space for media and ZIP exports.
