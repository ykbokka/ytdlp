# YouTube Music Liked Music

You can download your personal Liked Music shelf directly with the toolkit:

`https://music.youtube.com/playlist?list=LM`

**No separate `ytmusicapi_browser.json` file or manual browser-header setup is required.**

1. In the toolkit, select the same `cookies.txt` file you use for YouTube downloads.
2. Paste the Liked Music URL into the downloader and start the download.

For this special shelf, the toolkit now uses your existing cookie file to authenticate the YouTube Music API, retrieves the liked tracks, and sends each track through the normal download pipeline. Any temporary API-auth file is created locally and removed after the client loads it; your cookies are not uploaded to GitHub.

If authentication fails, the cookie export may be expired or missing the active `__Secure-3PAPISID` cookie required by YouTube Music. Export a fresh Netscape-format `cookies.txt` from your signed-in YouTube session, then select that file in the toolkit again.

**Keep `cookies.txt` private.** It contains account-session credentials. Never upload or send it to anyone.
