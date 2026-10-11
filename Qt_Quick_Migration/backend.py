from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

import requests
from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from mutagen import File as MutagenFile
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, APIC
from mutagen.mp4 import MP4, MP4Cover

CONFIG_FILE = Path.home() / ".ytm_music_toolkit.json"
COOKIE_ENV = "YTM_MUSIC_TOOLKIT_COOKIES"
MEDIA_EXTENSIONS = {".flac", ".mp3", ".m4a", ".mp4", ".mkv", ".webm", ".opus", ".ogg", ".wav", ".aac", ".wma", ".m4v", ".mov"}
AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".opus", ".ogg", ".wav", ".aac", ".wma"}


def resource_dirs() -> list[Path]:
    roots = []
    if getattr(sys, "_MEIPASS", None):
        roots.append(Path(sys._MEIPASS))
    here = Path(__file__).resolve().parent
    roots.extend([here, here.parent, here.parent.parent,
                  here.parent.parent / "EXE_Build_Kit" / "assets",
                  here.parent.parent / "EXE_Build_Kit" / "build_workspace" / "assets",
                  Path.home() / "Documents" / "YTDLP"])
    if getattr(sys, "frozen", False):
        roots.insert(0, Path(sys.executable).resolve().parent)
    seen, unique = set(), []
    for root in roots:
        try:
            key = os.path.normcase(str(root.resolve()))
        except OSError:
            key = str(root)
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def find_tool(name: str) -> str:
    for root in resource_dirs():
        for filename in (name, name + ".exe"):
            candidate = root / filename
            if candidate.is_file():
                return str(candidate)
    return shutil.which(name) or shutil.which(name + ".exe") or ""


def hidden_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = subprocess.SW_HIDE
    return {"startupinfo": info, "creationflags": subprocess.CREATE_NO_WINDOW}


def cookie_is_valid(path: str | Path) -> bool:
    try:
        with Path(path).open("r", encoding="utf-8-sig", errors="replace") as stream:
            return stream.readline().strip() in {"# Netscape HTTP Cookie File", "# HTTP Cookie File"}
    except OSError:
        return False


def get_ytdlp() -> list[str]:
    exe = find_tool("yt-dlp")
    if exe:
        return [exe]
    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        return []


class WorkerSignals(QObject):
    result = Signal(str, object)
    error = Signal(str, str)
    finished = Signal(str)


class OperationWorker(QRunnable):
    def __init__(self, key: str, operation: Callable[[], Any]):
        super().__init__()
        self.key, self.operation = key, operation
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.result.emit(self.key, self.operation())
        except Exception:
            self.signals.error.emit(self.key, traceback.format_exc())
        finally:
            self.signals.finished.emit(self.key)


class ToolkitBackend(QObject):
    statusChanged = Signal(str)
    logMessage = Signal(str)
    progressChanged = Signal(float, str)
    previewReady = Signal("QVariantMap")
    queueChanged = Signal("QVariantList")
    operationFinished = Signal(str, bool, str)
    metadataLoaded = Signal("QVariantMap")
    libraryScanReady = Signal("QVariantMap")
    settingsChanged = Signal("QVariantMap")

    def __init__(self):
        super().__init__()
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(max(3, min(6, os.cpu_count() or 4)))
        self.config = self._load_config()
        self.download_dir = str(self.config.get("download_dir") or (Path.home() / "Downloads"))
        self.cookie_path = self._find_cookie_path()
        self.performance_mode = self._valid_choice(self.config.get("performance_mode"), {"conservative", "balanced", "aggressive"}, "aggressive")
        self.conflict_mode = self._valid_choice(self.config.get("conflict_mode"), {"rename", "skip", "replace"}, "rename")
        self.appearance_mode = self._valid_choice(self.config.get("appearance_mode"), {"dark", "light"}, "dark")
        self.queue_items: list[dict[str, Any]] = [dict(x) for x in self.config.get("queue_items", []) if isinstance(x, dict)]
        self.active_process = None
        self.process_lock = threading.RLock()
        self.cancel_event = threading.Event()
        self.download_active = False
        self.paused = False
        self.last_operation_id = ""
        self._log("Qt Quick backend ready.")
        if not get_ytdlp():
            self._log("WARNING: yt-dlp executable was not found. Prepare the EXE build-kit assets or install yt-dlp.")
        if not find_tool("ffmpeg"):
            self._log("WARNING: FFmpeg is missing; audio conversion/merging and MKV cover attachments need it.")

    @staticmethod
    def _valid_choice(value, options, fallback):
        value = str(value or "").strip().lower()
        return value if value in options else fallback

    def _load_config(self):
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_config(self):
        self.config.update({"config_version": 6, "download_dir": self.download_dir,
                            "cookie_file_path": self.cookie_path, "performance_mode": self.performance_mode,
                            "conflict_mode": self.conflict_mode, "appearance_mode": self.appearance_mode, "queue_items": getattr(self, "queue_items", [])})
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = CONFIG_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.config, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, CONFIG_FILE)
        except OSError as exc:
            self._log(f"Settings could not be saved: {exc}")

    def _find_cookie_path(self):
        saved = str(self.config.get("cookie_file_path") or "").strip()
        env = os.environ.get(COOKIE_ENV, "").strip().strip('"')
        candidates = [saved, env]
        app_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        candidates.extend([str(app_dir / "cookies.txt"), str(Path.home() / "Documents" / "YTDLP" / "cookies.txt"), str(Path.home() / "cookies.txt")])
        for candidate in candidates:
            if candidate and cookie_is_valid(os.path.expandvars(os.path.expanduser(candidate))):
                return str(Path(candidate).expanduser().resolve())
        return ""

    def _log(self, text):
        self.logMessage.emit(f"[{time.strftime('%H:%M:%S')}] {text}")

    def _run_async(self, label, fn):
        key = f"{label}-{uuid.uuid4().hex[:8]}"
        worker = OperationWorker(key, fn)
        worker.signals.result.connect(self._worker_result)
        worker.signals.error.connect(self._worker_error)
        worker.signals.finished.connect(self._worker_finished)
        self.pool.start(worker)
        return key

    @Slot(str, object)
    def _worker_result(self, key, payload):
        marker = payload.pop("_kind", "") if isinstance(payload, dict) else ""
        if marker == "preview":
            self.previewReady.emit(payload)
        elif marker == "metadata":
            self.metadataLoaded.emit(payload)
        elif marker == "library":
            self.libraryScanReady.emit(payload)
        elif marker == "queue":
            self.queue_items = payload.get("items", [])
            self._save_config()
            self.queueChanged.emit(self.queue_items)
            self.statusChanged.emit(payload.get("message", "Queue updated."))
        elif marker == "done":
            ok, message = bool(payload.get("ok")), str(payload.get("message", ""))
            self.operationFinished.emit(key, ok, message)
            self.statusChanged.emit(message)
        elif marker == "download":
            ok, message = bool(payload.get("ok")), str(payload.get("message", ""))
            self.operationFinished.emit(key, ok, message)
            self.statusChanged.emit(message)
        elif payload is not None:
            self.operationFinished.emit(key, True, str(payload))

    @Slot(str, str)
    def _worker_error(self, key, trace):
        last = trace.strip().splitlines()[-1] if trace.strip() else "Unknown error"
        self._log(f"{key} failed: {last}")
        self.statusChanged.emit(f"Operation failed: {last}")
        self.operationFinished.emit(key, False, last)

    @Slot(str)
    def _worker_finished(self, key):
        if key == self.last_operation_id:
            self.last_operation_id = ""

    @Slot(result="QVariantMap")
    def getSettings(self):
        return {"downloadDir": self.download_dir, "cookiePath": self.cookie_path,
                "hasCookies": bool(self.cookie_path), "performanceMode": self.performance_mode,
                "conflictMode": self.conflict_mode, "appearanceMode": self.appearance_mode}

    @Slot(str)
    def setDownloadDirectory(self, path):
        path = str(path or "").strip().strip('"')
        if path:
            Path(path).mkdir(parents=True, exist_ok=True)
            self.download_dir = str(Path(path).resolve())
            self._save_config()
            self.settingsChanged.emit(self.getSettings())
            self.statusChanged.emit("Download folder updated.")

    @Slot(str)
    def setCookieFile(self, path):
        path = str(path or "").strip().strip('"')
        if path and not cookie_is_valid(path):
            self.statusChanged.emit("That is not a valid Netscape-format cookies.txt file.")
            return
        if path:
            self.cookie_path = str(Path(path).resolve())
            self._save_config()
            self.settingsChanged.emit(self.getSettings())
            self.statusChanged.emit("Cookie file saved.")

    @Slot(str)
    def setPerformanceMode(self, mode):
        self.performance_mode = self._valid_choice(mode, {"conservative", "balanced", "aggressive"}, "aggressive")
        self._save_config()
        self.settingsChanged.emit(self.getSettings())

    @Slot(str)
    def setConflictMode(self, mode):
        self.conflict_mode = self._valid_choice(mode, {"rename", "skip", "replace"}, "rename")
        self._save_config()
        self.settingsChanged.emit(self.getSettings())

    @Slot(str)
    def setAppearanceMode(self, mode):
        self.appearance_mode = self._valid_choice(mode, {"dark", "light"}, "dark")
        self._save_config()
        self.settingsChanged.emit(self.getSettings())

    def _base_command(self, download=False):
        cmd = get_ytdlp()
        if not cmd:
            raise RuntimeError("yt-dlp executable not found. Install it or prepare EXE_Build_Kit assets.")
        cmd.extend(["--ignore-config", "--no-warnings", "--encoding", "utf-8", "--remote-components", "ejs:github"])
        if self.cookie_path and cookie_is_valid(self.cookie_path):
            cmd.extend(["--cookies", self.cookie_path])
        deno = find_tool("deno")
        if deno:
            cmd.extend(["--js-runtimes", f"deno:{deno}"])
        if download:
            cmd.extend(["--newline", "--progress"])
            if self.performance_mode == "conservative":
                cmd.extend(["--concurrent-fragments", "4"])
            elif self.performance_mode == "balanced":
                cmd.extend(["--concurrent-fragments", "12"])
            else:
                cmd.extend(["--concurrent-fragments", "24"])
            aria2 = find_tool("aria2c")
            if aria2 and self.performance_mode != "conservative":
                n = 8 if self.performance_mode == "balanced" else 16
                split = "2M" if n == 8 else "1M"
                cmd.extend(["--downloader", "aria2c", "--downloader", "dash,m3u8:native",
                            "--downloader-args", f"aria2c:-x {n} -s {n} -k {split} --file-allocation=none --no-conf=true --max-download-limit=0 --max-overall-download-limit=0"])
        return cmd

    def _extract(self, url, flat=False):
        cmd = self._base_command(False) + ["--dump-single-json", "--skip-download"]
        if flat:
            cmd.extend(["--flat-playlist", "--yes-playlist"])
        else:
            cmd.append("--no-playlist")
        cmd.append(url)
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=120, **hidden_kwargs())
        if proc.returncode:
            raise RuntimeError((proc.stderr or proc.stdout or "Metadata extraction failed")[-1600:])
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("yt-dlp returned invalid JSON metadata.") from exc

    @staticmethod
    def _duration(value):
        try:
            total = max(0, int(float(value or 0)))
            h, rem = divmod(total, 3600)
            m, s = divmod(rem, 60)
            return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        except (TypeError, ValueError):
            return "—"

    @Slot(str)
    def preview(self, url):
        url = str(url or "").strip()
        if not url:
            self.statusChanged.emit("Paste a YouTube URL first.")
            return
        def work():
            data = self._extract(url)
            formats = data.get("formats") or []
            heights = sorted({int(x["height"]) for x in formats if x.get("height") and x.get("vcodec") != "none"}, reverse=True)
            return {"_kind": "preview", "title": data.get("title") or data.get("id") or "Untitled",
                    "id": str(data.get("id") or ""), "uploader": str(data.get("artist") or data.get("creator") or data.get("uploader") or data.get("channel") or ""),
                    "album": str(data.get("album") or ""), "duration": self._duration(data.get("duration")),
                    "thumbnail": str(data.get("thumbnail") or ""), "webpageUrl": str(data.get("webpage_url") or url),
                    "heights": heights, "formatCount": len(formats), "uploadDate": str(data.get("upload_date") or ""),
                    "description": str(data.get("description") or "")[:1000]}
        self.statusChanged.emit("Inspecting source…")
        self._log(f"Inspecting: {url}")
        self._run_async("preview", work)

    def _format_args(self, file_type, quality, audio_format):
        if file_type == "Audio only":
            formats = {"FLAC": ["--extract-audio", "--audio-format", "flac"],
                       "MP3": ["--extract-audio", "--audio-format", "mp3", "--audio-quality", "0"],
                       "M4A": ["--extract-audio", "--audio-format", "m4a", "--audio-quality", "0"],
                       "Opus": ["--extract-audio", "--audio-format", "opus", "--audio-quality", "0"]}
            return ["-f", "bestaudio/best"] + formats.get(audio_format, formats["FLAC"])
        match = re.search(r"(\d{3,4})\s*p", str(quality), re.I)
        height = int(match.group(1)) if match else 0
        ceiling = f"[height<={height}]" if height else ""
        if file_type == "Video (MP4)":
            return ["-f", f"bestvideo{ceiling}[ext=mp4]+bestaudio[ext=m4a]/best{ceiling}[ext=mp4]/best{ceiling}/best",
                    "--merge-output-format", "mp4"]
        return ["-f", f"bestvideo{ceiling}+bestaudio/best{ceiling}/best", "--merge-output-format", "mkv"]

    def _run_stage(self, command, stage, progress_start=0.0, progress_span=100.0):
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", bufsize=1, **hidden_kwargs())
        with self.process_lock:
            self.active_process = proc
            self.paused = False
        tail = []
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                tail.append(line)
                tail = tail[-35:]
                if line.startswith("__YT_PROGRESS__"):
                    fields = line[len("__YT_PROGRESS__"):].split("|")
                    try:
                        part = float(fields[0].replace("%", "").strip())
                    except (ValueError, IndexError):
                        part = 0.0
                    percent = progress_start + progress_span * max(0.0, min(100.0, part)) / 100.0
                    detail = " • ".join(x.strip() for x in fields[1:] if x.strip())
                    self.progressChanged.emit(percent, f"{stage}: {part:.1f}% {detail}".strip())
                elif "Destination:" in line or "Merging formats" in line or "ERROR:" in line or "WARNING:" in line:
                    self.logMessage.emit(line)
                if self.cancel_event.is_set():
                    self._terminate_process_tree(proc)
                    break
            code = proc.wait()
            if self.cancel_event.is_set():
                raise InterruptedError("Download cancelled.")
            if code:
                raise RuntimeError(f"{stage} failed:\n" + ("\n".join(tail[-14:]) or f"Process exited with code {code}"))
            return tail
        finally:
            with self.process_lock:
                if self.active_process is proc:
                    self.active_process = None
                self.paused = False
            try:
                if proc.poll() is None:
                    proc.kill()
            except OSError:
                pass

    @staticmethod
    def _safe_name(value):
        value = re.sub(r'[<>:"/\\\\|?*\\x00-\\x1f]+', "_", str(value or "Untitled"))
        value = re.sub(r"\\s+", " ", value).strip(" .")
        return (value[:150] or "Untitled")

    @staticmethod
    def _language_label(code):
        value = str(code or "und").replace("_", "-").strip()
        parts = value.split("-")
        names = {"en": "English", "ar": "Arabic", "es": "Spanish", "fr": "French", "de": "German",
                 "it": "Italian", "pt": "Portuguese", "ru": "Russian", "ja": "Japanese", "ko": "Korean",
                 "zh": "Chinese", "hi": "Hindi", "tr": "Turkish", "id": "Indonesian", "th": "Thai",
                 "vi": "Vietnamese", "pl": "Polish", "nl": "Dutch", "sv": "Swedish", "uk": "Ukrainian",
                 "fa": "Persian", "ur": "Urdu", "bn": "Bengali", "ta": "Tamil", "te": "Telugu"}
        base = parts[0].lower() if parts else "und"
        return names.get(base, value if value and value != "und" else "Unknown language")

    @staticmethod
    def _language_iso639(code):
        base = str(code or "").replace("_", "-").split("-")[0].lower()
        mapping = {"en":"eng","ar":"ara","es":"spa","fr":"fra","de":"deu","it":"ita","pt":"por","ru":"rus",
                   "ja":"jpn","ko":"kor","zh":"zho","hi":"hin","tr":"tur","id":"ind","th":"tha","vi":"vie",
                   "pl":"pol","nl":"nld","sv":"swe","uk":"ukr","fa":"fas","ur":"urd","bn":"ben","ta":"tam","te":"tel"}
        return mapping.get(base, "und")

    def _download_mkv_with_flac_tracks(self, url, quality, subtitles):
        output = Path(self.download_dir).expanduser()
        output.mkdir(parents=True, exist_ok=True)
        temp = output / "tempytm"
        temp.mkdir(parents=True, exist_ok=True)
        try:
            info = self._extract(url, flat=False)
            title = str(info.get("title") or info.get("id") or "Untitled")
            video_id = str(info.get("id") or uuid.uuid4().hex[:8])
            final_stem = self._safe_name(f"{title} [{video_id}]")
            final_path = output / f"{final_stem}.mkv"
            if self.conflict_mode == "rename":
                suffix = 2
                while final_path.exists():
                    final_path = output / f"{final_stem} ({suffix}).mkv"
                    suffix += 1
            elif self.conflict_mode == "skip" and final_path.exists():
                self._log(f"Skipping existing file: {final_path.name}")
                return True

            ffmpeg = find_tool("ffmpeg")
            if not ffmpeg:
                raise RuntimeError("FFmpeg is required for the MKV + FLAC audio-track workflow.")
            formats = [fmt for fmt in (info.get("formats") or []) if isinstance(fmt, dict)]
            available_video = [fmt for fmt in formats if fmt.get("vcodec") not in (None, "none")]
            if not available_video:
                raise RuntimeError("No video streams were reported by yt-dlp.")

            match = re.search(r"(\\d{3,4})\\s*p", str(quality), re.I)
            ceiling = int(match.group(1)) if match else 0
            selector = f"bestvideo[height<={ceiling}]/bestvideo" if ceiling else "bestvideo"

            audio_formats = []
            for fmt in formats:
                if fmt.get("acodec") in (None, "none") or fmt.get("vcodec") not in (None, "none"):
                    continue
                if fmt.get("has_drm") or not fmt.get("format_id"):
                    continue
                audio_formats.append(fmt)
            # Select one highest-quality audio rendition for each language, not
            # every bitrate/codec duplicate exposed by the extractor.
            by_language = {}
            for fmt in audio_formats:
                language = str(fmt.get("language") or "und").strip().lower()
                rank = (
                    int(fmt.get("language_preference") or 0),
                    float(fmt.get("abr") or 0),
                    int(fmt.get("asr") or 0),
                    int(fmt.get("audio_channels") or 0),
                )
                previous = by_language.get(language)
                if previous is None or rank > previous[0]:
                    by_language[language] = (rank, fmt)
            tracks = [pair[1] for pair in by_language.values()]
            tracks.sort(key=lambda fmt: (
                0 if fmt.get("language_preference", 0) and float(fmt.get("language_preference") or 0) > 0 else 1,
                str(fmt.get("language") or "und").lower(),
            ))
            tracks = tracks[:12]
            if not tracks:
                raise RuntimeError("No separate audio-only streams were available for the requested video.")

            video_target = temp / "video.%(ext)s"
            video_cmd = self._base_command(True) + [
                "--no-playlist", "--no-embed-thumbnail", "--no-embed-metadata",
                "--no-write-thumbnail", "--format", selector, "--remux-video", "mkv",
                "--output", str(video_target), "--no-part",
                "--progress-template", "download:__YT_PROGRESS__%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
                url,
            ]
            self._log(f"Downloading video stream for {title}")
            self._run_stage(video_cmd, "Video", 0, 45)
            video_files = [p for p in temp.glob("video.*") if p.is_file() and p.suffix.lower() in {".mkv", ".mp4", ".webm", ".mov"}]
            if not video_files:
                raise RuntimeError("yt-dlp finished, but the video-only MKV staging file was not found.")
            video_path = video_files[0]

            audio_paths = []
            track_labels = []
            for index, fmt in enumerate(tracks, 1):
                if self.cancel_event.is_set():
                    raise InterruptedError("Download cancelled.")
                language = str(fmt.get("language") or "und")
                safe_language = re.sub(r"[^a-zA-Z0-9_-]+", "_", language)[:18] or f"track{index}"
                audio_target = temp / f"audio_{safe_language}.%(ext)s"
                audio_cmd = self._base_command(True) + [
                    "--no-playlist", "--no-embed-thumbnail", "--no-embed-metadata",
                    "--no-write-thumbnail", "--format", str(fmt["format_id"]),
                    "--extract-audio", "--audio-format", "flac",
                    "--output", str(audio_target), "--no-part",
                    "--progress-template", "download:__YT_PROGRESS__%(progress._percent_str)s|%(progress._speed_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
                    url,
                ]
                start = 45 + (35 * (index - 1) / len(tracks))
                span = 35 / len(tracks)
                label = self._language_label(language)
                self._log(f"Downloading {label} audio track ({index}/{len(tracks)})")
                self._run_stage(audio_cmd, label, start, span)
                matches = [p for p in temp.glob(f"audio_{safe_language}.*") if p.is_file() and p.suffix.lower() == ".flac"]
                if not matches:
                    raise RuntimeError(f"The {label} audio track did not produce a FLAC file.")
                audio_paths.append(matches[0])
                track_labels.append((label, self._language_iso639(language)))

            cover_path = temp / "cover.jpg"
            thumbnail_url = str(info.get("thumbnail") or "")
            if thumbnail_url:
                try:
                    response = requests.get(thumbnail_url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
                    response.raise_for_status()
                    from io import BytesIO
                    with Image.open(BytesIO(response.content)) as image:
                        ImageOps.exif_transpose(image).convert("RGB").save(cover_path, "JPEG", quality=100, subsampling=0)
                except Exception as exc:
                    self._log(f"Thumbnail could not be prepared; continuing without cover attachment: {exc}")
                    cover_path.unlink(missing_ok=True)

            merge_cmd = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-i", str(video_path)]
            for audio_path in audio_paths:
                merge_cmd.extend(["-i", str(audio_path)])
            merge_cmd.extend(["-map", "0:v:0"])
            for input_index in range(1, len(audio_paths) + 1):
                merge_cmd.extend(["-map", f"{input_index}:a:0"])
            merge_cmd.extend(["-c:v", "copy", "-c:a", "copy", "-metadata", f"title={title}"])
            for track_index, (label, language_code) in enumerate(track_labels):
                merge_cmd.extend([f"-metadata:s:a:{track_index}", f"title={label}"])
                merge_cmd.extend([f"-metadata:s:a:{track_index}", f"language={language_code}"])
            if cover_path.exists():
                merge_cmd.extend(["-attach", str(cover_path), "-metadata:s:t", "mimetype=image/jpeg",
                                  "-metadata:s:t", "filename=cover.jpg"])
            if self.conflict_mode == "replace":
                merge_cmd.append("-y")
            merge_cmd.append(str(final_path))
            self.statusChanged.emit("Muxing video and language-specific FLAC audio tracks…")
            self._log(f"Merging {len(audio_paths)} FLAC audio track(s) into {final_path.name}")
            self.progressChanged.emit(90, "Muxing audio tracks into MKV")
            self._run_stage(merge_cmd, "Mux", 90, 10)

            if subtitles in {"Auto subtitles", "Manual subtitles"}:
                subtitle_cmd = self._base_command(True) + ["--no-playlist", "--skip-download",
                    "--sub-langs", "all,-live_chat", "--output", str(temp / "subtitle.%(ext)s"),
                    "--no-part"]
                subtitle_cmd.extend(["--write-auto-subs"] if subtitles == "Auto subtitles" else ["--write-subs"])
                subtitle_cmd.append(url)
                try:
                    self._run_stage(subtitle_cmd, "Subtitles", 98, 2)
                    for subtitle in temp.glob("subtitle.*"):
                        if subtitle.is_file() and subtitle.suffix.lower() in {".vtt", ".srt", ".ass", ".lrc"}:
                            language_suffix = subtitle.name[len("subtitle"):]
                            destination = output / f"{final_path.stem}{language_suffix}"
                            shutil.move(str(subtitle), str(destination))
                except Exception as exc:
                    if isinstance(exc, InterruptedError):
                        raise
                    self._log(f"Subtitles were not added: {exc}")

            self.progressChanged.emit(100, "Download complete")
            self._log(f"Completed MKV with {len(audio_paths)} FLAC track(s): {final_path}")
            return True
        finally:
            with self.process_lock:
                self.active_process = None
                self.paused = False
            shutil.rmtree(temp, ignore_errors=True)

    def _download_one(self, url, file_type, quality, audio_format, subtitles):
        if file_type == "Video (MKV)":
            return self._download_mkv_with_flac_tracks(url, quality, subtitles)
        output = Path(self.download_dir).expanduser()
        output.mkdir(parents=True, exist_ok=True)
        temp = output / "tempytm"
        temp.mkdir(parents=True, exist_ok=True)
        cmd = self._base_command(True) + self._format_args(file_type, quality, audio_format)
        cmd += ["--output", str(output / "%(title).180B [%(id)s].%(ext)s"),
                "--paths", f"temp:{temp}", "--windows-filenames", "--embed-metadata",
                "--embed-thumbnail", "--write-thumbnail", "--convert-thumbnails", "jpg"]
        if subtitles == "Auto subtitles":
            cmd += ["--write-auto-subs", "--sub-langs", "all,-live_chat"]
        elif subtitles == "Manual subtitles":
            cmd += ["--write-subs", "--sub-langs", "all,-live_chat"]
        if self.conflict_mode == "skip":
            cmd.append("--no-overwrites")
        elif self.conflict_mode == "replace":
            cmd.append("--force-overwrites")
        else:
            cmd += ["--output", str(output / "%(title).180B [%(id)s]-%(autonumber)03d.%(ext)s")]
        cmd += ["--progress-template", "download:__YT_PROGRESS__%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s", url]
        self.cancel_event.clear() if not self.cancel_event.is_set() else None
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                   encoding="utf-8", errors="replace", bufsize=1, **hidden_kwargs())
        with self.process_lock:
            self.active_process = process
            self.paused = False
        try:
            assert process.stdout is not None
            tail = []
            for line in process.stdout:
                line = line.rstrip()
                if not line:
                    continue
                tail.append(line)
                tail = tail[-40:]
                if line.startswith("__YT_PROGRESS__"):
                    fields = line[len("__YT_PROGRESS__"):].split("|")
                    try:
                        percent = float(fields[0].replace("%", "").strip())
                    except (ValueError, IndexError):
                        percent = 0.0
                    detail = " • ".join(x.strip() for x in fields[1:] if x.strip())
                    self.progressChanged.emit(percent, f"{percent:.1f}% {detail}")
                elif "Destination:" in line or "Merging formats" in line or "ERROR:" in line or "WARNING:" in line:
                    self.logMessage.emit(line)
                if self.cancel_event.is_set():
                    process.terminate()
                    break
            code = process.wait()
            if self.cancel_event.is_set():
                raise InterruptedError("Download cancelled.")
            if code:
                raise RuntimeError("\n".join(tail[-12:]) or f"yt-dlp exited with {code}")
            self.progressChanged.emit(100, "Download complete")
            return True
        finally:
            with self.process_lock:
                if self.active_process is process:
                    self.active_process = None
                self.paused = False
            try:
                if process.poll() is None:
                    process.kill()
            except OSError:
                pass
            shutil.rmtree(temp, ignore_errors=True)

    @Slot(str, str, str, str, str)
    def startDownload(self, url, file_type, quality, audio_format, subtitles):
        if self.download_active:
            self.statusChanged.emit("A download is already active.")
            return
        if not str(url or "").strip():
            self.statusChanged.emit("Paste a URL first.")
            return
        self.cancel_event.clear()
        self.download_active = True
        def work():
            try:
                self._download_one(url, file_type, quality, audio_format, subtitles)
                return {"_kind": "download", "ok": True, "message": "Download finished successfully."}
            finally:
                self.download_active = False
        self.last_operation_id = self._run_async("download", work)
        self.statusChanged.emit("Download started.")
        self._log(f"Download requested: {url}")

    @Slot(result=bool)
    def togglePause(self):
        with self.process_lock:
            proc = self.active_process
            currently_paused = self.paused
        if not proc or proc.poll() is not None:
            self.statusChanged.emit("There is no active download process to pause.")
            return self.paused
        try:
            import psutil
            parent = psutil.Process(proc.pid)
            processes = parent.children(recursive=True) + [parent]
            if currently_paused:
                for process in reversed(processes):
                    try:
                        process.resume()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                with self.process_lock:
                    self.paused = False
                self.statusChanged.emit("Download resumed.")
            else:
                for process in processes:
                    try:
                        process.suspend()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                with self.process_lock:
                    self.paused = True
                self.statusChanged.emit("Download paused.")
            return self.paused
        except Exception as exc:
            self._log(f"Pause/resume unavailable: {exc}")
            self.statusChanged.emit("Pause/resume failed; see Activity.")
            return self.paused

    def _terminate_process_tree(self, proc):
        if not proc or proc.poll() is not None:
            return
        try:
            import psutil
            parent = psutil.Process(proc.pid)
            children = parent.children(recursive=True)
            for child in reversed(children):
                try:
                    child.resume()
                    child.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            try:
                parent.resume()
                parent.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            _, alive = psutil.wait_procs([parent] + children, timeout=2)
            for process in alive:
                try:
                    process.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            try:
                proc.terminate()
            except OSError:
                pass

    @Slot()
    def stopDownload(self):
        self.cancel_event.set()
        with self.process_lock:
            proc = self.active_process
            self.paused = False
        self._terminate_process_tree(proc)
        self.statusChanged.emit("Stopping current operation…")

    @Slot(str)
    def addQueueUrl(self, url):
        url = str(url or "").strip()
        if not url:
            self.statusChanged.emit("Paste a URL to add it to the queue.")
            return
        def work():
            try:
                data = self._extract(url, flat=True)
                entries = data.get("entries")
                rows = []
                if isinstance(entries, list) and entries:
                    for entry in entries:
                        if not entry:
                            continue
                        vid = str(entry.get("id") or "")
                        source = str(entry.get("webpage_url") or entry.get("url") or "")
                        if vid and not source.startswith(("http://", "https://")):
                            source = f"https://www.youtube.com/watch?v={vid}"
                        if source:
                            rows.append({"id": uuid.uuid4().hex[:10], "title": str(entry.get("title") or vid or source),
                                         "url": source, "status": "Pending", "duration": self._duration(entry.get("duration"))})
                if not rows:
                    rows.append({"id": uuid.uuid4().hex[:10], "title": str(data.get("title") or url),
                                 "url": str(data.get("webpage_url") or url), "status": "Pending", "duration": self._duration(data.get("duration"))})
                return {"_kind": "queue", "items": self.queue_items + rows, "message": f"Added {len(rows)} item(s) to queue."}
            except Exception:
                return {"_kind": "queue", "items": self.queue_items + [{"id": uuid.uuid4().hex[:10], "title": url, "url": url, "status": "Pending", "duration": "—"}],
                        "message": "Added URL to queue; it will be inspected when downloading."}
        self.statusChanged.emit("Resolving playlist for queue…")
        self._run_async("queue-add", work)

    @Slot(str)
    def removeQueueItem(self, item_id):
        self.queue_items = [x for x in self.queue_items if x.get("id") != item_id]
        self._save_config()
        self.queueChanged.emit(self.queue_items)

    @Slot()
    def clearQueue(self):
        if self.download_active:
            self.statusChanged.emit("Stop the active download before clearing the queue.")
            return
        self.queue_items = []
        self._save_config()
        self.queueChanged.emit(self.queue_items)
        self.statusChanged.emit("Queue cleared.")

    @Slot(str, str, str, str)
    def startQueue(self, file_type, quality, audio_format, subtitles):
        if self.download_active:
            self.statusChanged.emit("A download is already active.")
            return
        pending = [dict(x) for x in self.queue_items if x.get("status") in {"Pending", "Failed", "Stopped"}]
        if not pending:
            self.statusChanged.emit("The queue has no pending items.")
            return
        self.cancel_event.clear()
        self.download_active = True
        def work():
            completed = failed = 0
            try:
                for item in pending:
                    if self.cancel_event.is_set():
                        break
                    item["status"] = "Downloading"
                    self.queue_items = [dict(x) for x in self.queue_items]
                    for current in self.queue_items:
                        if current.get("id") == item.get("id"):
                            current["status"] = "Downloading"
                    self.queueChanged.emit(self.queue_items)
                    self.statusChanged.emit(f"Downloading: {item['title']}")
                    try:
                        self._download_one(item["url"], file_type, quality, audio_format, subtitles)
                        item["status"] = "Completed"
                        completed += 1
                    except InterruptedError:
                        item["status"] = "Stopped"
                        break
                    except Exception as exc:
                        item["status"] = "Failed"
                        failed += 1
                        self._log(f"Queue item failed: {item['title']}: {exc}")
                    for current in self.queue_items:
                        if current.get("id") == item.get("id"):
                            current["status"] = item["status"]
                    self.queueChanged.emit(self.queue_items)
                message = f"Queue finished: {completed} completed, {failed} failed."
                if self.cancel_event.is_set():
                    message = f"Queue stopped: {completed} completed, {failed} failed."
                return {"_kind": "download", "ok": failed == 0, "message": message}
            finally:
                self.download_active = False
        self.last_operation_id = self._run_async("queue-run", work)

    @Slot(str)
    def inspectMediaFile(self, path):
        path = str(path or "").strip()
        def work():
            media = MutagenFile(path, easy=True)
            if media is None:
                raise ValueError("Unsupported media file.")
            tags = media.tags or {}
            def first(key):
                value = tags.get(key)
                return str(value[0] if isinstance(value, (list, tuple)) and value else value or "")
            return {"_kind": "metadata", "path": str(Path(path).resolve()),
                    "title": first("title") or Path(path).stem, "artist": first("artist"),
                    "album": first("album"), "date": first("date") or first("year"),
                    "genre": first("genre"), "comment": first("comment") or first("description")}
        self._run_async("metadata-read", work)

    @Slot(str, str, str, str)
    def lookupYtMusicMetadata(self, path, artist, title, album):
        path = str(path or "").strip()
        artist = str(artist or "").strip()
        title = str(title or "").strip()
        album = str(album or "").strip()
        if path and not title:
            stem = Path(path).stem
            if " - " in stem:
                left, right = stem.split(" - ", 1)
                artist = artist or left.strip()
                title = right.strip()
            else:
                title = stem
        if not title and not artist:
            self.statusChanged.emit("Enter an artist/title or choose a media file first.")
            return

        def work():
            from ytmusicapi import YTMusic
            ytm = YTMusic()
            query = " ".join(part for part in (artist, title, album) if part).strip()
            results = [item for item in (ytm.search(query, filter="songs", limit=12) or []) if isinstance(item, dict)]
            if not results:
                results = [item for item in (ytm.search(query, filter="videos", limit=12) or []) if isinstance(item, dict)]
            if not results:
                raise RuntimeError("YouTube Music returned no matching songs or videos.")

            def norm(value):
                return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())

            wanted_artist, wanted_title, wanted_album = norm(artist), norm(title), norm(album)
            best_item, best_score = None, -1.0
            for item in results:
                names = [str(x.get("name") or "") for x in (item.get("artists") or []) if isinstance(x, dict)]
                exact_artist = bool(wanted_artist and any(norm(name) == wanted_artist for name in names))
                result_title = str(item.get("title") or "")
                title_score = SequenceMatcher(None, wanted_title, norm(result_title)).ratio() if wanted_title else 0.3
                album_data = item.get("album") or {}
                result_album = str(album_data.get("name") or "") if isinstance(album_data, dict) else str(album_data)
                album_score = 0.1 if wanted_album and norm(result_album) == wanted_album else 0.0
                score = title_score * 0.78 + (0.20 if exact_artist else 0.0) + album_score
                if score > best_score:
                    best_item, best_score = item, score
            if best_item is None:
                raise RuntimeError("No suitable YouTube Music result was found.")
            album_data = best_item.get("album") or {}
            result_album = str(album_data.get("name") or "") if isinstance(album_data, dict) else str(album_data)
            thumbs = best_item.get("thumbnails") or []
            thumb = str(thumbs[-1].get("url") or "") if thumbs and isinstance(thumbs[-1], dict) else ""
            artists = ", ".join(str(x.get("name") or "") for x in (best_item.get("artists") or []) if isinstance(x, dict))
            path_value = str(Path(path).resolve()) if path else ""
            self._log(f"YT Music match selected: {best_item.get('title', 'Untitled')} (score {best_score:.2f})")
            return {"_kind": "metadata", "path": path_value,
                    "title": str(best_item.get("title") or title),
                    "artist": artists or artist, "album": result_album or album,
                    "date": str(best_item.get("year") or ""), "genre": "", "comment": "", "thumbnail": thumb}

        self.statusChanged.emit("Searching YouTube Music for matching metadata…")
        self._run_async("ytmusic-lookup", work)

    @Slot(str, "QVariantMap")
    def saveMetadata(self, path, values):
        values = dict(values or {})
        def work():
            media = MutagenFile(path, easy=True)
            if media is None:
                raise ValueError("Unsupported media format.")
            if media.tags is None:
                media.add_tags()
            fields = {k: str(values.get(k) or "").strip() for k in ("title", "artist", "album", "date", "genre", "comment")}
            for key, value in fields.items():
                try:
                    if value:
                        media.tags[key] = [value]
                    elif key in media.tags:
                        del media.tags[key]
                except (KeyError, TypeError):
                    pass
            for key in ("albumartist", "album artist", "aART"):
                try:
                    del media.tags[key]
                except (KeyError, TypeError):
                    pass
            media.save()
            return {"_kind": "done", "ok": True, "message": f"Metadata saved: {Path(path).name}"}
        self._run_async("metadata-save", work)

    @Slot(str, str)
    def embedArtwork(self, media_path, artwork_source):
        def work():
            path = Path(media_path)
            if not path.is_file():
                raise FileNotFoundError("Choose a valid media file.")
            source = str(artwork_source or "").strip()
            if source.startswith(("https://", "http://")):
                response = requests.get(source, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
                response.raise_for_status()
                raw = response.content
            else:
                raw = Path(source).read_bytes()
            from io import BytesIO
            with Image.open(BytesIO(raw)) as img:
                img = ImageOps.exif_transpose(img).convert("RGB")
                buf = BytesIO()
                img.save(buf, "JPEG", quality=100, subsampling=0)
                data = buf.getvalue()
            ext = path.suffix.lower()
            if ext in AUDIO_EXTENSIONS:
                media = MutagenFile(str(path))
                if isinstance(media, FLAC):
                    picture = Picture()
                    picture.type, picture.mime, picture.desc, picture.data = 3, "image/jpeg", "Cover", data
                    media.clear_pictures()
                    media.add_picture(picture)
                    media.save()
                elif ext == ".mp3":
                    tags = ID3(str(path))
                    tags.delall("APIC")
                    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=data))
                    tags.save(str(path))
                elif isinstance(media, MP4):
                    media["covr"] = [MP4Cover(data, imageformat=MP4Cover.FORMAT_JPEG)]
                    media.save()
                else:
                    raise ValueError("Supported audio artwork formats: FLAC, MP3, and M4A.")
            elif ext == ".mkv":
                ffmpeg = find_tool("ffmpeg")
                if not ffmpeg:
                    raise RuntimeError("FFmpeg was not found.")
                cover = path.with_name("." + path.stem + ".cover-tmp.jpg")
                temp_out = path.with_name("." + path.stem + ".cover-tmp.mkv")
                cover.write_bytes(data)
                try:
                    p = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
                                        "-map", "0", "-c", "copy", "-attach", str(cover),
                                        "-metadata:s:t", "mimetype=image/jpeg", "-metadata:s:t", "filename=cover.jpg",
                                        str(temp_out)], capture_output=True, text=True, timeout=180, **hidden_kwargs())
                    if p.returncode:
                        raise RuntimeError((p.stderr or "Could not attach the cover")[-1200:])
                    os.replace(temp_out, path)
                finally:
                    cover.unlink(missing_ok=True)
                    temp_out.unlink(missing_ok=True)
            else:
                raise ValueError("This prototype embeds artwork into audio files and MKV video.")
            return {"_kind": "done", "ok": True, "message": f"Artwork embedded: {path.name}"}
        self._run_async("cover", work)

    @Slot(str, str, str)
    def cropArtwork(self, source, destination, position):
        def work():
            if not Path(source).is_file():
                raise FileNotFoundError("Choose a source image.")
            if not destination:
                raise ValueError("Choose an output path.")
            with Image.open(source) as original:
                image = ImageOps.exif_transpose(original).convert("RGB")
                w, h = image.size
                side = min(w, h)
                p = str(position or "Center").lower()
                left = 0 if "left" in p else (w-side if "right" in p else (w-side)//2)
                top = 0 if "top" in p else (h-side if "bottom" in p else (h-side)//2)
                image.crop((left, top, left+side, top+side)).save(destination, "JPEG", quality=100, subsampling=0)
            return {"_kind": "done", "ok": True, "message": f"Artwork crop saved: {destination}"}
        self._run_async("crop", work)

    @Slot(str)
    def scanLibrary(self, folder):
        def work():
            root = Path(folder)
            if not root.is_dir():
                raise NotADirectoryError("Choose a valid folder.")
            rows = []
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
                    continue
                try:
                    media = MutagenFile(str(path), easy=True)
                    tags = media.tags or {} if media else {}
                    rows.append({"path": str(path), "name": path.name,
                                 "title": str((tags.get("title") or [""])[0]),
                                 "proposedTitle": re.sub(r"\s+", " ", path.stem.replace("_", " ")).strip(),
                                 "removeAlbumArtist": bool(tags.get("albumartist") or tags.get("album artist")),
                                 "status": "Ready"})
                except Exception as exc:
                    rows.append({"path": str(path), "name": path.name, "title": "", "proposedTitle": path.stem,
                                 "removeAlbumArtist": False, "status": f"Unreadable: {exc}"})
            return {"_kind": "library", "folder": str(root), "rows": rows}
        self.statusChanged.emit("Scanning library…")
        self._run_async("library-scan", work)

    @Slot("QVariantList", bool)
    def applyLibraryOverhaul(self, rows, rewrite_titles):
        items = [dict(x) for x in (rows or [])]
        def work():
            updated = failed = 0
            for row in items:
                try:
                    media = MutagenFile(str(row.get("path") or ""), easy=True)
                    if media is None:
                        continue
                    if media.tags is None:
                        media.add_tags()
                    if rewrite_titles and row.get("proposedTitle"):
                        media.tags["title"] = [str(row["proposedTitle"])]
                    for key in ("albumartist", "album artist"):
                        try:
                            del media.tags[key]
                        except (KeyError, TypeError):
                            pass
                    media.save()
                    updated += 1
                except Exception as exc:
                    failed += 1
                    self._log(f"Library item failed: {row.get('name')}: {exc}")
            return {"_kind": "done", "ok": failed == 0, "message": f"Library overhaul: {updated} updated, {failed} failed."}
        self._run_async("library-overhaul", work)
