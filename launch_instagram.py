"""Open a dedicated local Instagram window using installed Microsoft Edge.

You browse manually. No automated feed collection. The isolated profile
stays in private/ and is excluded from git.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / "private" / "browser-profile"
PROFILE.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    print("Launching Microsoft Edge using a private local RMA profile.")
    print("No Playwright Chromium download is required.")
    with sync_playwright() as playwright:
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE),
                channel="msedge",
                headless=False,
                viewport={"width": 480, "height": 850},
                args=["--window-size=520,950"],
            )
        except Exception as exc:
            raise SystemExit(
                "Cannot launch Microsoft Edge. Ensure Edge is installed and close "
                "other RMA browser instances. Details: " + str(exc)
            )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.instagram.com/reels/", wait_until="domcontentloaded")
            print("Browse manually; close the window when done.")
            while context.pages:
                context.pages[0].wait_for_timeout(1000)
        except KeyboardInterrupt:
            pass
        finally:
            context.close()
