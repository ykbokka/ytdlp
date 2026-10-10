# YouTube Music Liked Music

You can download your personal Liked Music shelf directly with the toolkit:

`https://music.youtube.com/playlist?list=LM`

**No separate `ytmusicapi_browser.json` file or manual browser-header setup is required.**

1. Open `https://music.youtube.com` in Opera GX and confirm you're signed in to the account whose likes you want.
2. Export a fresh Netscape-format `cookies.txt` while on YouTube Music. Some cookie exporters filter cookies by the current site, so a file exported from `youtube.com` may not contain the session cookies needed for the Music API.
3. In the toolkit, select that `cookies.txt` file, then paste the Liked Music URL and start the download.

For this special shelf, the toolkit uses the selected cookie file to authenticate the YouTube Music API, retrieve the liked tracks, and send each track through the normal download pipeline. Any temporary API-auth file is created locally and removed after the client loads it; your cookies are not uploaded to GitHub.

If the toolkit says YouTube Music returned its signed-out Liked Music screen, the cookies were readable but were not accepted for the authenticated library request. Refresh the export from the signed-in YouTube Music site and try again. If that still fails, the account session or the export itself may need attention.

**Keep `cookies.txt` private.** It contains account-session credentials. Never upload or send it to anyone.
