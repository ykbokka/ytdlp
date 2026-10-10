# YouTube Music “Liked Music” authentication

The URL `https://music.youtube.com/playlist?list=LM` is YouTube Music's account-bound **Liked Music** shelf. It is not a normal YouTube playlist. yt-dlp redirects it to regular YouTube, which responds that playlist `LM` does not exist.

The toolkit now uses ytmusicapi to enumerate this special shelf. It looks for an authentication file at:

`%USERPROFILE%\Documents\YTDLP\ytmusicapi_browser.json`

You only need this file for listing the account's Liked Music items. The normal yt-dlp cookie file remains separate for individual media requests.

## Create the local browser-auth file in Opera GX

1. Open Opera GX and go to `https://music.youtube.com`. Confirm you are signed in to the account whose Liked Music you want to process.
2. Open Developer Tools with **Ctrl+Shift+I**, select **Network**, and filter for `browse`.
3. Click Library in YouTube Music if needed to generate requests. Find a successful **POST** request to `music.youtube.com` whose name includes `browse`.
4. Select that request and look at its **Request Headers**. Use values from that one request for the JSON fields below. Do not combine values from different requests.
5. Create the folder `%USERPROFILE%\Documents\YTDLP` if it does not exist. Save the JSON as `ytmusicapi_browser.json` inside it.

Example structure (replace each placeholder locally with the matching value from your own request):

```json
{
  "Accept": "*/*",
  "Authorization": "PASTE_AUTHORIZATION_HEADER_VALUE",
  "Content-Type": "application/json",
  "X-Goog-AuthUser": "0",
  "x-origin": "https://music.youtube.com",
  "Cookie": "PASTE_COOKIE_HEADER_VALUE"
}
```

Keep this file on your computer. It contains live account-session credentials, effectively granting access to your YouTube Music account. **Do not send it to anyone, upload it to a chat, include it in a ZIP, or commit it to GitHub.** If it is exposed, sign out of the relevant Google session and refresh your credentials.

## After setup

Run the toolkit's source refresh and rebuild steps, then try the `music.youtube.com/playlist?list=LM` URL again. The app should enumerate tracks through the authenticated YouTube Music API instead of asking yt-dlp to resolve `LM` as an ordinary playlist.

If the app reports an authentication/API error, re-create this file from a fresh successful `browse` request. Never paste the header values into a diagnostic log or chat.
