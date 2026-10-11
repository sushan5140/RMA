"""Opens Instagram in an isolated persistent local Chromium profile.

No automated scrolling/scraping. You control the login and browsing.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / "private" / "browser-profile"
PROFILE.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    print("Launching a locally stored browser profile. Never commit private/.")
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=False,
            viewport={"width": 480, "height": 850},
            args=["--window-size=520,950"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.instagram.com/reels/", wait_until="domcontentloaded")
        print("Use the browser manually; close it when finished.")
        try:
            while context.pages:
                context.pages[0].wait_for_timeout(1000)
        except KeyboardInterrupt:
            pass
        finally:
            context.close()
