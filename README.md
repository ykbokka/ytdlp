# YouTube Toolkit

**A Windows-first desktop toolkit for YouTube and YouTube Music workflows — from media downloads to metadata, artwork, and library maintenance.**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![yt-dlp](https://img.shields.io/badge/powered%20by-yt--dlp-111111)](https://github.com/yt-dlp/yt-dlp)
[![Last commit](https://img.shields.io/github/last-commit/ykbokka/ytdlp)](https://github.com/ykbokka/ytdlp/commits/main)
[![Repository size](https://img.shields.io/github/repo-size/ykbokka/ytdlp)](https://github.com/ykbokka/ytdlp)

YouTube Toolkit brings downloading and music-library utilities together in one desktop application. The project combines Python with **yt-dlp**, **FFmpeg**, and YouTube Music metadata lookup, with a focus on practical workflows: getting media, keeping tags consistent, managing artwork, and cleaning up a collection.

**Development acknowledgement:** Created and maintained by Bokka, with AI-assisted planning, implementation, debugging, and documentation support from **ChatGPT by OpenAI**. The project is built iteratively, with the maintainer directing priorities and reviewing changes.

> **Project status:** The existing CustomTkinter application is in `YTM_Music_Toolkit.pyw`. The `Qt_Quick_Migration/` directory contains an evolving PySide6 + Qt Quick interface and backend. The Qt Quick version is still a migration project, not yet a guaranteed feature-for-feature replacement. Review the status and known limitations before relying on it for a full library workflow.

---

## What it does

### Media downloads
- Download supported YouTube and YouTube Music sources through yt-dlp.
- Work with video and audio workflows supported by the selected application version.
- Use quality and format options where the source exposes compatible streams.
- Use playlist and queue workflows where implemented by the selected interface.

### Music metadata
- Use YouTube Music as the primary source for music-oriented matching.
- Prefer song results with an exact contributing-artist match, then score title/album similarity and use a video-result fallback when needed.
- Read and edit common audio tags, including title, artist, album, date, genre, and comment.
- Keep metadata matching tied to the source video where the backend supports source-ID validation.

### Artwork and library utilities
- Embed or replace artwork for supported media formats.
- Prepare high-quality square cover images.
- Scan media folders and review filename/title or tag-cleanup suggestions.
- Run batch FLAC metadata and artwork workflows in the versions that support them.

### Built with care for desktop use
- Windows-oriented desktop interface and background operations.
- Saved application settings and download-folder preferences.
- Failure logs and activity messages to help investigate errors.
- An experimental Qt Quick interface focused on smoother transitions and a more responsive feel.

**Feature availability can differ between the existing application and the Qt Quick migration.** The migration notes describe what is implemented and what still needs end-to-end testing.

---

## Choose your version

| Version | Location | Best for |
| --- | --- | --- |
| Existing desktop app | [`YTM_Music_Toolkit.pyw`](YTM_Music_Toolkit.pyw) | The current CustomTkinter implementation |
| Qt Quick migration | [`Qt_Quick_Migration/`](Qt_Quick_Migration/) | Trying the newer PySide6 + QML interface and helping validate parity |

For current migration setup instructions, packaging steps, supported workflows, and known limitations, read the [Qt Quick migration guide](Qt_Quick_Migration/README.md).

---

## Run the existing app from source

The main app is Windows-oriented and requires Python plus the external media tools it invokes.

### 1. Install prerequisites

Install **Python 3.11 or newer** and **FFmpeg**. Ensure `ffmpeg` and `ffprobe` are accessible from your terminal or supplied alongside your application build.

The app invokes yt-dlp as a command-line tool. The included requirements install its Python distribution and command entry point. A Deno runtime is recommended for YouTube extraction flows that need JavaScript challenge support; aria2c is optional and may be used for some download paths.

### 2. Download the repository

```powershell
git clone https://github.com/ykbokka/ytdlp.git
cd ytdlp
```

### 3. Create an isolated environment

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Launch

```powershell
python .\YTM_Music_Toolkit.pyw
```

You can also launch the `.pyw` file directly after installing the dependencies. If an operation reports that yt-dlp, FFmpeg, or another external executable is missing, check that tool's installation and PATH before troubleshooting the application itself.

---

## Try the Qt Quick migration

The newer interface is kept in its own directory so it can be tested separately from the existing app.

1. Download or clone this repository and open `Qt_Quick_Migration/`.
2. Double-click `Run-Prototype.bat`.
3. On first launch, the script creates an isolated `.venv`, installs Python dependencies, runs the available backend tests and QML smoke test, then launches the prototype.

To create a self-contained Windows executable, run `Install-Dependencies.bat` followed by `Build-Prototype-EXE.bat` from that directory. The initial setup downloads sizeable tools and needs an internet connection. Build output and further details are covered in the [migration guide](Qt_Quick_Migration/README.md).

The smoke tests are useful checks for syntax, backend logic, and QML loading; **they are not proof that every download, audio container, subtitle, account-bound playlist, or metadata workflow works end to end on every Windows system**. Keep backups and use a disposable output folder while evaluating the migration.

---

## Configuration, cookies, and privacy

- User settings are stored in `~/.ytm_music_toolkit.json` in the current user's home directory.
- Some YouTube Music or account-bound playlist workflows may require a valid Netscape-format `cookies.txt` file, depending on the source and application version.
- Treat cookies as authentication credentials. **Never commit or share your cookie file**, and remove cookie values from logs or screenshots before posting them.
- Failure logs can contain local paths, source URLs, and diagnostic details. Review them for personal information before attaching them to an issue.
- Download behavior is affected by source availability, network conditions, yt-dlp, extractor changes, and the installed media tools. No specific speed or successful result can be guaranteed for every source.

---

## Troubleshooting

**A download fails or YouTube extraction stops working**
- Update yt-dlp and confirm its command is available in the same environment that launches the app.
- Check whether the source is public, available, and accessible with your current session.
- Review the latest failure log. If JavaScript challenge support is involved, verify the Deno runtime and yt-dlp's documented requirements.

**Audio conversion, merging, or cover attachment fails**
- Confirm that FFmpeg and FFprobe are installed and discoverable.
- Try a short, public test video and a temporary output folder before retrying a large playlist.

**A batch operation finds no files**
- Confirm the exact folder path displayed by the app and that it contains files supported by that specific operation. Some workflows only operate on FLAC files, even though the general library scanner recognizes additional media formats.

**The Qt Quick prototype does not start**
- Run `Run-Prototype.bat` from its own directory and read the console output.
- If reporting an issue, include the failing step and the final relevant error lines, but never include cookie contents.

---

## Contributing

Bug reports, reproducible test cases, and thoughtful improvements are welcome.

For a useful issue, include:
- Windows version and Python version, if running from source.
- Which application version you tested: the existing app or the Qt Quick migration.
- The operation you attempted and the exact error message.
- Relevant failure-log excerpts with personal paths, private URLs, and authentication data removed.

For code changes, keep the existing and migration implementations clearly distinguished unless the change intentionally applies to both. Prefer small, testable changes and describe which manual workflows were verified. Please do not submit cookies, downloaded media, private account data, or other sensitive files.

---

## Responsible use

Use the application only for content you have the right to access and download. Respect creators' rights, platform terms, and applicable law. The project is an independent community tool and is not affiliated with or endorsed by YouTube, Google, or the yt-dlp project.

## Credits

This project builds on the work of the Python ecosystem, [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FFmpeg](https://ffmpeg.org/), [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter), [PySide6 / Qt Quick](https://doc.qt.io/qtforpython/), [ytmusicapi](https://github.com/sigma67/ytmusicapi), Pillow, and Mutagen. Visit each upstream project for its license and contribution information.

## License

There is not currently a `LICENSE` file in this repository. Until an explicit license is added, do not assume that public availability grants permission to redistribute or reuse the code. If you maintain this project, adding a clear license is an important next step for welcoming outside contributions.
