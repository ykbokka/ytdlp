# YouTube Toolkit V9 — Final Release

<p align="center">
  <strong>One toolkit. Your entire media workflow.</strong><br>
  Download media. Keep your metadata tidy. Manage cover art. Take control of your music library.
</p>

<p align="center">
  <a href="https://github.com/ykbokka/ytdlp/releases"><strong>⬇️ Get YouTube Toolkit</strong></a>
  ·
  <a href="https://github.com/ykbokka/ytdlp/issues">Report a problem</a>
</p>

---

YouTube Toolkit is a Windows desktop application that brings media downloading and music-library maintenance into one place. Built around **yt-dlp**, **FFmpeg**, **YouTube Music metadata matching**, and a modern **PySide6 + Qt Quick interface**, it brings together the jobs that usually mean jumping between several different tools.

V9 is the **Final Release** edition of the toolkit: one app for downloading media, managing queues, editing tags, updating artwork, and maintaining a collection.

## ✨ What you can do

### 🎬 Download videos and music

- Download supported YouTube and YouTube Music sources.
- Choose video output formats such as **MKV** and **MP4**, or extract audio to **FLAC, MP3, M4A, or Opus**.
- Set a quality ceiling so the selected resolution is not exceeded when a lower-quality source is all that is available.
- Download playlists through a queue, monitor progress, and manage queued items.
- Choose subtitle options where supported by the source.
- Select performance and existing-file handling preferences.
- Keep temporary download and conversion files separate from completed output.

### 🎵 Find and maintain music metadata

- Inspect and edit common tags, including title, artist, album, date, genre, and comment.
- Use YouTube Music as the primary source for music-oriented matching.
- Prioritize exact contributing-artist matches and compare title and album information.
- Clean up unwanted album-artist tags and derive cleaner titles from filenames when appropriate.
- Use batch FLAC metadata tools to help keep a music collection consistent.

### 🖼️ Manage artwork and crop to 1:1

- Embed or replace artwork in supported audio and video files.
- Upgrade FLAC cover art with YouTube Music artwork where a suitable match is found.
- Crop a standalone image into a high-quality **square (1:1) JPEG**.
- Or choose **Embedded artwork in media file** to extract an existing cover from a supported media file and save a cropped JPEG separately.
- Choose the crop position: **Center, Top, Bottom, Left, or Right**.

When cropping embedded artwork, the output is saved separately; the source media file is not meant to be modified by that operation. Embedded-artwork extraction depends on the container, how the cover is stored, and whether the required stream or attachment can be read.

### 📚 Scan and overhaul a library

- Scan a folder of supported media files and review the results.
- Review filename-derived title suggestions and tag cleanup before applying changes.
- Run a full FLAC overhaul that can combine YouTube Music matching, metadata updates, and cover-art processing.
- Track operation status and review activity messages when troubleshooting.

**Make a backup before running bulk metadata or artwork operations.** A batch operation can change the files in the selected library.

### 🌙 A modern desktop experience

- A clean PySide6 + Qt Quick interface with dark and light appearance modes.
- Dedicated pages for Downloader, Queue, Metadata, Cover Art, Crop Art, Library Overhaul, Settings, and Activity.
- Saved preferences and configurable media folders.
- A custom application icon, progress feedback, and diagnostic logs.

## ⬇️ Download and launch

1. Open the [GitHub Releases page](https://github.com/ykbokka/ytdlp/releases).
2. Choose **YouTube Toolkit V9 — Final Release**.
3. Download the Windows executable attached to that release and launch it.

The standalone build bundles the application runtime and required helper tools, including yt-dlp, FFmpeg/FFprobe, Deno, and aria2. **A separate Python installation should not be needed to run the released executable.** The build process itself is intended for 64-bit Windows and requires internet access to obtain dependencies.

> **Release note:** Make sure you select the V9 Final Release asset, not an older release marked unstable.

## 🔐 Settings, cookies, and privacy

- Application settings are stored locally in `~/.ytm_music_toolkit.json` under your user profile.
- Personal settings and authentication cookies are kept outside the bundled executable.
- Some sources, bot checks, and private or account-bound playlists may require a valid `cookies.txt` file. Authentication needs can change with YouTube's systems.
- Treat cookies as passwords. Never upload, commit, or share your cookie file.
- Diagnostic logs can contain local file paths, source URLs, and other troubleshooting context. Review them before sharing.

YouTube Toolkit does not promise that every source, playlist, format, or account-restricted item will be available. Results depend on the source, your access, connectivity, and the behavior of third-party tools.

## 🛠️ Troubleshooting

**A download or extraction fails**  
Check that the source is accessible and that your connection is working. Some sources may need a valid cookie file. Upstream extractor changes can also temporarily affect downloads.

**Audio conversion or merging fails**  
Confirm that FFmpeg and FFprobe are present in the build or available to the application. Try a short, publicly accessible source before retrying a large playlist.

**Crop Art cannot extract a media file's thumbnail**  
The image must be embedded in a supported way, such as an audio cover tag, an attached-picture stream, or a readable MKV attachment. If the artwork is stored separately, switch the source type to **Image file**.

**A library scan finds no supported files**  
Check the selected folder path. The general scan supports common media types, while some batch operations specifically require FLAC files.

**The app reports an error**  
Check the Activity section and the diagnostic log referenced by the app. When reporting a problem, include the final error text and the operation you were performing—but never include cookie contents or other private authentication data.

## 🧰 Built with

YouTube Toolkit builds on work from these projects:

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — media extraction and downloading
- [FFmpeg](https://ffmpeg.org/) — media processing and stream handling
- [Deno](https://deno.com/) — JavaScript runtime support for compatible extraction workflows
- [aria2](https://github.com/aria2/aria2) — alternative download engine
- [PySide6 / Qt Quick](https://doc.qt.io/qtforpython/) — desktop interface
- [Mutagen](https://github.com/quodlibet/mutagen) — media metadata
- [Pillow](https://python-pillow.org/) — image processing
- [ytmusicapi](https://github.com/sigma67/ytmusicapi) — YouTube Music interface support

Each third-party component remains subject to its own license and terms.

## ❤️ Credits

Created and maintained by **Bokka**, with AI-assisted planning, implementation, debugging, and documentation support from **ChatGPT (OpenAI)**, **Gemini (Google)**, and **Claude (Anthropic)**. The product direction, priorities, and release decisions are driven by the project maintainer.

Thanks to the maintainers of the open-source projects that make this toolkit possible.

## ⚖️ Responsible use and licensing

YouTube Toolkit is an independent community project. It is not affiliated with or endorsed by YouTube, YouTube Music, Google, or Apple.

Use the application only for content you are authorized to access, download, and modify. Respect creators' rights, platform terms, and applicable laws.

This repository does not currently include a project-level `LICENSE` file. Public visibility alone does not grant permission to redistribute or reuse the project's own source code. Third-party components retain their respective licenses.

---

<p align="center">
  <strong>YouTube Toolkit V9 — Final Release</strong><br>
  <em>Download. Organize. Maintain.</em>
</p>
