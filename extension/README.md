# RMA Edge extension (prototype)

1. In your usual Microsoft Edge browser, open `edge://extensions`.
2. Enable **Developer mode**.
3. Choose **Load unpacked** and select the **extension** directory from this repository.
4. Use Instagram in your usual browser session. Open an individual Instagram reel URL, click the RMA toolbar icon, then **Save current Reel link**.
5. Use **Copy saved links** to export the collection.

This first prototype does **not** access credentials/cookies, capture audio/video, scroll automatically, or upload to Drive. It stores only explicitly saved reel links in extension-local storage, which can be cleared from the popup.

Media capture and analysis need a separately authorized user-initiated workflow. Do not grant extra permissions to unknown extensions or bypass Instagram checks.
