"""Launch an ordinary Microsoft Edge window for manual Instagram browsing.

No Playwright/automation flags. Profile stays local in private/.
"""
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / "private" / "edge-manual-profile"
PROFILE.mkdir(parents=True, exist_ok=True)

def find_edge():
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    return next((p for p in candidates if p.is_file()), None)

if __name__ == "__main__":
    edge = find_edge()
    if not edge:
        raise SystemExit("Microsoft Edge not found. Open https://www.instagram.com/reels/ in your normal Edge browser.")
    print("Opening ordinary Microsoft Edge. Browse and sign in manually.")
    print("This does not automatically capture or scroll reels.")
    subprocess.Popen([str(edge), f"--user-data-dir={PROFILE}", "--new-window",
                      "https://www.instagram.com/reels/"])
