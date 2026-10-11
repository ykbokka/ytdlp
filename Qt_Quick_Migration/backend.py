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
import urllib.parse
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
from ytmusic_resolver import YTMResolver, split_artist_title, canonicalize_thumbnail_url

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
                  here.parent / "EXE_Build_Kit" / "assets",
                  here.parent / "EXE_Build_Kit" / "build_workspace" / "assets",
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


def write_failure_log(context: str, exc: Any, details: str = "") -> str:
    """Write detailed diagnostics without serializing cookies or auth headers."""
    directory = Path.home() / "Documents" / "YTDLP"
    safe_context = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(context or "failure")).strip("._") or "failure"
    stamp = time.strftime("%Y%m%d_%H%M%S")
    unique = time.time_ns() % 1_000_000_000
    log_path = directory / f"FAILURE_{stamp}_{unique:09d}_{safe_context}.log"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if isinstance(exc, BaseException):
            exception_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        else:
            exception_text = str(exc or "Unknown failure")
        lines = [
            "YOUTUBE TOOLKIT FAILURE LOG",
            "=" * 72,
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Context: {safe_context}",
            "",
            "Exception / traceback:",
            exception_text,
        ]
        if details:
            lines.extend(["", "Additional details:", str(details)])
        log_path.write_text("\\n".join(lines) + "\\n", encoding="utf-8")
        return str(log_path)
    except OSError:
        return ""


def get_ytdlp() -> list[str]:
    exe = find_tool("yt-dlp")
    if exe:
        return [exe]
    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        return []


def build_native_ytdlp_fallback_command(command: list[str]) -> list[str] | None:
    """Remove only the aria2 routing options, preserving yt-dlp's own selection."""
    source = list(command or [])
    fallback = []
    index = 0
    changed = False
    while index < len(source):
        token = str(source[index])
        if token == "--downloader" and index + 1 < len(source):
            downloader = str(source[index + 1]).strip().lower()
            if downloader in {"aria2c", "dash,m3u8:native"}:
                index += 2
                changed = True
                continue
        if token == "--downloader-args" and index + 1 < len(source):
            argument = str(source[index + 1]).strip().lower()
            if argument.startswith("aria2c:"):
                index += 2
                changed = True
                continue
        fallback.append(source[index])
        index += 1
    return fallback if changed and fallback else None


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
        saved_paths = self.config.get("paths", {})
        if not isinstance(saved_paths, dict):
            saved_paths = {}
        downloads_default = str(Path.home() / "Downloads")
        self.path_settings = {
            "downloader": str(saved_paths.get("downloader") or self.config.get("download_dir") or downloads_default),
            "metadata": str(saved_paths.get("metadata") or downloads_default),
            "cover": str(saved_paths.get("cover") or downloads_default),
            "crop": str(saved_paths.get("crop") or downloads_default),
            "pipeline": str(saved_paths.get("pipeline") or downloads_default),
        }
        self.download_dir = str(self.config.get("download_dir") or self.path_settings["downloader"])
        self.path_settings["downloader"] = self.download_dir
        self.cookie_path = self._find_cookie_path()
        self.performance_mode = self._valid_choice(self.config.get("performance_mode"), {"conservative", "balanced", "aggressive"}, "aggressive")
        saved_file_type = str(self.config.get("file_type") or "Video (MKV)")
        self.file_type = saved_file_type if saved_file_type in {"Video (MKV)", "Video (MP4)", "Audio only"} else "Video (MKV)"
        saved_quality = str(self.config.get("quality") or "Best available").strip()
        self.quality = saved_quality[:40] if saved_quality else "Best available"
        saved_audio = str(self.config.get("audio_format") or "FLAC")
        self.audio_format = saved_audio if saved_audio in {"FLAC", "MP3", "M4A", "Opus"} else "FLAC"
        saved_subtitles = str(self.config.get("subtitle_mode") or "No subtitles")
        self.subtitle_mode = saved_subtitles if saved_subtitles in {"No subtitles", "Auto subtitles", "Manual subtitles"} else "No subtitles"
        self.conflict_mode = self._valid_choice(self.config.get("conflict_mode"), {"rename", "skip", "replace"}, "rename")
        self.appearance_mode = self._valid_choice(self.config.get("appearance_mode"), {"dark", "light"}, "dark")
        self.queue_items: list[dict[str, Any]] = [dict(x) for x in self.config.get("queue_items", []) if isinstance(x, dict)]
        for queued_item in self.queue_items:
            if str(queued_item.get("status") or "").strip().lower() == "downloading":
                queued_item["status"] = "Stopped"
        self.active_process = None
        self.process_lock = threading.RLock()
        self.cancel_event = threading.Event()
        self.download_active = False
        self.paused = False
        self.last_operation_id = ""
        self._workers: dict[str, OperationWorker] = {}
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
        self.path_settings["downloader"] = self.download_dir
        self.config.update({"config_version": 6, "download_dir": self.download_dir,
                            "paths": dict(self.path_settings),
                            "cookie_file_path": self.cookie_path, "performance_mode": self.performance_mode,
                            "file_type": self.file_type, "quality": self.quality,
                            "audio_format": self.audio_format, "subtitle_mode": self.subtitle_mode,
                            "conflict_mode": self.conflict_mode, "appearance_mode": self.appearance_mode,
                            "queue_items": getattr(self, "queue_items", [])})
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

    @staticmethod
    def _clear_temp_contents(folder):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        for item in folder.iterdir():
            try:
                if item.is_dir() and not item.is_symlink():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
            except OSError:
                pass

    def _record_history(self, operation, ok, message):
        history_path = Path.home() / "Documents" / "YTDLP" / "operation_history.json"
        try:
            history_path.parent.mkdir(parents=True, exist_ok=True)
            entries = []
            if history_path.is_file():
                try:
                    loaded = json.loads(history_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, list):
                        entries = loaded
                except (OSError, json.JSONDecodeError):
                    entries = []
            entries.append({
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "operation": str(operation or "operation"),
                "success": bool(ok),
                "message": str(message or "")[:500],
            })
            temporary = history_path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(entries[-250:], indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, history_path)
        except OSError as exc:
            self._log(f"Could not update operation history: {exc}")

    def _run_async(self, label, fn):
        key = f"{label}-{uuid.uuid4().hex[:8]}"
        worker = OperationWorker(key, fn)
        worker.signals.result.connect(self._worker_result)
        worker.signals.error.connect(self._worker_error)
        worker.signals.finished.connect(self._worker_finished)
        self._workers[key] = worker
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
            self._record_history(key.split("-", 1)[0], ok, message)
        elif marker == "download":
            ok, message = bool(payload.get("ok")), str(payload.get("message", ""))
            self.operationFinished.emit(key, ok, message)
            self.statusChanged.emit(message)
            self._record_history(key.split("-", 1)[0], ok, message)
        elif payload is not None:
            self.operationFinished.emit(key, True, str(payload))

    @Slot(str, str)
    def _worker_error(self, key, trace):
        last = trace.strip().splitlines()[-1] if trace.strip() else "Unknown error"
        if "InterruptedError" in trace and "cancelled" in trace.lower():
            message = "Download stopped by user."
            self._log(f"{key} stopped by user.")
            self.statusChanged.emit(message)
            self.operationFinished.emit(key, False, message)
            self._record_history(key.split("-", 1)[0], False, message)
            return
        log_path = write_failure_log(key.split("-", 1)[0], trace, details=f"Operation id: {key}")
        self._log(f"{key} failed: {last}" + (f" | Diagnostic log: {log_path}" if log_path else ""))
        self.statusChanged.emit(f"Operation failed: {last}" + (f" · Log: {log_path}" if log_path else ""))
        self.operationFinished.emit(key, False, last)
        self._record_history(key.split("-", 1)[0], False, last)

    @Slot(str)
    def _worker_finished(self, key):
        self._workers.pop(key, None)
        if key == self.last_operation_id:
            self.last_operation_id = ""

    @Slot(result="QVariantMap")
    def getSettings(self):
        return {"downloadDir": self.download_dir, "cookiePath": self.cookie_path,
                "hasCookies": bool(self.cookie_path), "performanceMode": self.performance_mode,
                "conflictMode": self.conflict_mode, "appearanceMode": self.appearance_mode,
                "metadataDir": self.path_settings["metadata"], "coverDir": self.path_settings["cover"],
                "cropDir": self.path_settings["crop"], "pipelineDir": self.path_settings["pipeline"],
                "fileType": self.file_type, "quality": self.quality,
                "audioFormat": self.audio_format, "subtitleMode": self.subtitle_mode}

    @Slot(str)
    def setDownloadDirectory(self, path):
        path = str(path or "").strip().strip('"')
        if path:
            Path(path).mkdir(parents=True, exist_ok=True)
            self.download_dir = str(Path(path).resolve())
            self._save_config()
            self.settingsChanged.emit(self.getSettings())
            self.statusChanged.emit("Download folder updated.")

    @Slot(str, str)
    def setOperationDirectory(self, key, path):
        key = str(key or "").strip().lower()
        path = str(path or "").strip().strip('"')
        if key not in {"metadata", "cover", "crop", "pipeline"} or not path:
            return
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            self.path_settings[key] = str(Path(path).resolve())
            self._save_config()
            self.settingsChanged.emit(self.getSettings())
            self.statusChanged.emit(f"{key.title()} folder saved.")
        except OSError as exc:
            self.statusChanged.emit(f"Could not save {key} folder: {exc}")

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

    @Slot(str, str, str, str)
    def setDownloadOptions(self, file_type, quality, audio_format, subtitle_mode):
        file_type = str(file_type or "").strip()
        quality = str(quality or "Best available").strip()[:40]
        audio_format = str(audio_format or "FLAC").strip()
        subtitle_mode = str(subtitle_mode or "No subtitles").strip()
        if file_type in {"Video (MKV)", "Video (MP4)", "Audio only"}:
            self.file_type = file_type
        if quality:
            self.quality = quality
        if audio_format in {"FLAC", "MP3", "M4A", "Opus"}:
            self.audio_format = audio_format
        if subtitle_mode in {"No subtitles", "Auto subtitles", "Manual subtitles"}:
            self.subtitle_mode = subtitle_mode
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
        cmd.extend([
            "--ignore-config", "--no-warnings", "--encoding", "utf-8",
            "--socket-timeout", "10",
            "--remote-components", "ejs:github",
            "--extractor-args", "youtube:player_client=default,web_embedded",
        ])
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

    def _extract(self, url, flat=False, track_process=False):
        cmd = self._base_command(False) + ["--dump-single-json", "--skip-download"]
        if flat:
            cmd.extend(["--flat-playlist", "--yes-playlist"])
        else:
            cmd.append("--no-playlist")
        cmd.append(url)
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", **hidden_kwargs()
        )
        if track_process:
            with self.process_lock:
                self.active_process = proc
                self.paused = False
        try:
            deadline = time.monotonic() + 120
            while True:
                if track_process and self.cancel_event.is_set():
                    self._terminate_process_tree(proc)
                    try:
                        proc.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.communicate()
                    raise InterruptedError("Download cancelled during source inspection.")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._terminate_process_tree(proc)
                    try:
                        proc.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.communicate()
                    raise TimeoutError("yt-dlp metadata extraction exceeded 120 seconds.")
                try:
                    stdout, stderr = proc.communicate(timeout=min(0.25, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            if proc.returncode:
                raise RuntimeError((stderr or stdout or "Metadata extraction failed")[-1600:])
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError("yt-dlp returned invalid JSON metadata.") from exc
            if not isinstance(payload, dict):
                raise RuntimeError("yt-dlp returned no usable metadata object. For account-bound playlists, use Add to Queue and ensure cookies.txt is configured.")
            return payload
        finally:
            if track_process:
                with self.process_lock:
                    if self.active_process is proc:
                        self.active_process = None
                    self.paused = False
            if proc.poll() is None:
                try:
                    self._terminate_process_tree(proc)
                except Exception:
                    pass

    @staticmethod
    def _duration(value):
        try:
            total = max(0, int(float(value or 0)))
            h, rem = divmod(total, 3600)
            m, s = divmod(rem, 60)
            return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        except (TypeError, ValueError):
            return "—"

    @staticmethod
    def _is_http_url(value):
        return str(value or "").strip().lower().startswith(("http://", "https://"))

    @staticmethod
    def _is_playlist_url(value):
        value = str(value or "").strip()
        try:
            parsed = urllib.parse.urlparse(value)
            query = urllib.parse.parse_qs(parsed.query)
            return bool(query.get("list")) or "/playlist" in parsed.path.lower()
        except Exception:
            return False

    @staticmethod
    def _is_liked_music_url(value):
        value = str(value or "").strip()
        try:
            parsed = urllib.parse.urlparse(value)
            query = urllib.parse.parse_qs(parsed.query)
            return str((query.get("list") or [""])[0]).upper() == "LM"
        except Exception:
            return "list=LM" in value.upper()

    def _resolve_user_input_with_metadata(self, value):
        value = str(value or "").strip()
        if self._is_http_url(value):
            return value, None
        artist, title = split_artist_title(value)
        match = YTMResolver().search(artist, title, "")
        if not match:
            raise RuntimeError("No exact contributing-artist YouTube Music match was found. Try 'Artist - Title' or paste a direct URL.")
        video_id = str(match.get("video_id") or "").strip()
        if not video_id:
            raise RuntimeError("The YouTube Music result did not include a usable video ID.")
        self._log(f"Search resolved to {match.get('artist') or 'Unknown artist'} — {match.get('title') or video_id} ({match.get('source') or 'YT Music'})")
        return f"https://www.youtube.com/watch?v={video_id}", match

    def _resolve_user_input(self, value):
        return self._resolve_user_input_with_metadata(value)[0]

    @Slot(str)
    def preview(self, url):
        requested = str(url or "").strip()
        if not requested:
            self.statusChanged.emit("Paste a YouTube URL or enter Artist - Title.")
            return

        def work():
            default_heights = [2160, 1440, 1080, 720, 480, 360]
            if self._is_liked_music_url(requested):
                return {"_kind": "preview", "title": "YouTube Music Liked Music",
                        "id": "LM", "uploader": "Your library", "album": "",
                        "duration": "—", "webpageUrl": requested, "thumbnail": "",
                        "isPlaylist": True, "playlistCount": 0, "heights": default_heights,
                        "formatCount": 0, "description": "Account-bound playlist; tracks are resolved when added to Queue."}
            if self._is_playlist_url(requested):
                data = self._extract(requested, flat=True)
                entries = data.get("entries") or []
                count = sum(1 for item in entries if isinstance(item, dict) and (item.get("id") or item.get("video_id") or item.get("videoId")))
                if not count:
                    raise RuntimeError("The playlist returned no usable video entries.")
                thumbnail = str(data.get("thumbnail") or "")
                if not thumbnail:
                    candidates = [item for item in (data.get("thumbnails") or []) if isinstance(item, dict) and item.get("url")]
                    candidates.sort(key=lambda item: int(item.get("width") or 0) * int(item.get("height") or 0), reverse=True)
                    thumbnail = str(candidates[0].get("url") or "") if candidates else ""
                return {"_kind": "preview", "title": str(data.get("title") or "YouTube Playlist"),
                        "id": str(data.get("id") or ""), "uploader": str(data.get("uploader") or data.get("channel") or ""),
                        "album": "", "duration": f"{count} videos", "webpageUrl": requested,
                        "thumbnail": thumbnail, "isPlaylist": True, "playlistCount": count,
                        "heights": default_heights, "formatCount": 0,
                        "description": "Per-video formats are checked as each queue item starts."}
            resolved_match = None
            source_url = requested
            if not self._is_http_url(requested):
                artist, title = split_artist_title(requested)
                resolved_match = YTMResolver().search(artist, title, "")
                if not resolved_match or not resolved_match.get("video_id"):
                    raise RuntimeError("No matching YouTube Music song was found. Use 'Artist - Title' or paste a URL.")
                source_url = f"https://www.youtube.com/watch?v={resolved_match['video_id']}"
            data = self._extract(source_url)
            formats = data.get("formats") or []
            heights = sorted({int(x["height"]) for x in formats if x.get("height") and x.get("vcodec") != "none"}, reverse=True)
            title = (resolved_match or {}).get("title") or data.get("title") or data.get("id") or "Untitled"
            artist = (resolved_match or {}).get("artist") or data.get("artist") or data.get("creator") or data.get("uploader") or data.get("channel") or ""
            album = (resolved_match or {}).get("album") or data.get("album") or ""
            thumb = (resolved_match or {}).get("cover_url") or data.get("thumbnail") or ""
            result = {"_kind": "preview", "title": str(title), "id": str(data.get("id") or ""),
                      "uploader": str(artist), "album": str(album), "duration": self._duration(data.get("duration")),
                      "thumbnail": str(thumb), "webpageUrl": str(data.get("webpage_url") or source_url),
                      "heights": heights, "formatCount": len(formats), "uploadDate": str(data.get("upload_date") or ""),
                      "description": str(data.get("description") or "")[:1000], "resolvedUrl": source_url}
            if resolved_match:
                result["source"] = resolved_match.get("source") or ""
            return result

        self.statusChanged.emit("Inspecting URL or resolving YouTube Music search…")
        self._log(f"Preview requested: {requested}")
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
            if ceiling:
                selector = f"bestvideo{ceiling}[ext=mp4]+bestaudio[ext=m4a]/best{ceiling}[ext=mp4]/best{ceiling}"
            else:
                selector = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            return ["-f", selector, "--merge-output-format", "mp4"]
        return ["-f", f"bestvideo{ceiling}+bestaudio/best{ceiling}/best", "--merge-output-format", "mkv"]

    def _run_stage(self, command, stage, progress_start=0.0, progress_span=100.0):
        active_command = list(command)
        active_stage = stage

        for attempt in range(2):
            proc = subprocess.Popen(
                active_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                **hidden_kwargs()
            )
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
                    tail = tail[-45:]
                    if line.startswith("__YT_PROGRESS__"):
                        fields = line[len("__YT_PROGRESS__"):].split("|")
                        try:
                            part = float(fields[0].replace("%", "").strip())
                        except (ValueError, IndexError):
                            part = 0.0
                        percent = progress_start + progress_span * max(0.0, min(100.0, part)) / 100.0
                        detail = " • ".join(x.strip() for x in fields[1:] if x.strip())
                        self.progressChanged.emit(percent, f"{active_stage}: {part:.1f}% {detail}".strip())
                    elif "Destination:" in line or "Merging formats" in line or "ERROR:" in line or "WARNING:" in line:
                        self.logMessage.emit(line)
                    if self.cancel_event.is_set():
                        self._terminate_process_tree(proc)
                        break
                code = proc.wait()
                if self.cancel_event.is_set():
                    raise InterruptedError("Download cancelled.")
            finally:
                with self.process_lock:
                    if self.active_process is proc:
                        self.active_process = None
                    self.paused = False
                try:
                    if proc.poll() is None:
                        self._terminate_process_tree(proc)
                except Exception:
                    pass

            if code == 0:
                return tail

            native_command = build_native_ytdlp_fallback_command(active_command)
            aria2_error = any("aria2c" in line.lower() for line in tail)
            if attempt == 0 and aria2_error and native_command:
                self._log(f"{active_stage}: aria2c failed; retrying once with yt-dlp's native downloader.")
                active_command = native_command
                active_stage = f"{stage} (native fallback)"
                continue

            raise RuntimeError(
                f"{active_stage} failed:\\n" +
                ("\\n".join(tail[-14:]) or f"Process exited with code {code}")
            )

        raise RuntimeError(f"{stage} failed without a usable fallback.")

    def _metadata_for_source(self, info, url, requested_result=None):
        """Use YT Music enrichment only when it is tied to the exact source video ID."""
        source_id = str(info.get("id") or "").strip()
        if not source_id:
            parsed = urllib.parse.urlparse(str(url or ""))
            source_id = str((urllib.parse.parse_qs(parsed.query).get("v") or [""])[0]).strip()

        artist = str(info.get("artist") or info.get("creator") or info.get("uploader") or info.get("channel") or "").strip()
        title = str(info.get("track") or info.get("title") or source_id or "Untitled").strip()
        album = str(info.get("album") or "").strip()
        uploaded = str(info.get("release_year") or info.get("upload_date") or "").strip()
        year = uploaded[:4] if len(uploaded) >= 4 else ""
        candidates = []
        thumbs = [item for item in (info.get("thumbnails") or []) if isinstance(item, dict)]
        thumbs.sort(key=lambda item: int(item.get("width") or 0) * int(item.get("height") or 0), reverse=True)
        if info.get("thumbnail"):
            candidate = canonicalize_thumbnail_url(info.get("thumbnail"))
            if candidate:
                candidates.append(candidate)
        for item in thumbs:
            candidate = canonicalize_thumbnail_url(item.get("url") or "")
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        direct = {
            "video_id": source_id, "title": title, "artist": artist, "album": album,
            "year": year, "cover_url": candidates[0] if candidates else "",
            "thumbnail_candidates": candidates, "source": "YouTube source metadata",
        }

        match = None
        if isinstance(requested_result, dict):
            requested_id = str(requested_result.get("video_id") or "").strip()
            if source_id and requested_id == source_id:
                match = dict(requested_result)
        if match is None and "music.youtube.com" in str(url or "").lower() and title:
            try:
                candidate = YTMResolver().search(artist, title, album)
                candidate_id = str((candidate or {}).get("video_id") or "").strip()
                if source_id and candidate_id == source_id:
                    match = candidate
                elif candidate_id:
                    self._log("Rejected a YouTube Music metadata match because its video ID differed from the source.")
            except Exception as exc:
                self._log(f"YouTube Music metadata enrichment unavailable; using exact source metadata: {exc}")

        if match:
            merged = dict(direct)
            merged.update(match)
            merged["video_id"] = source_id or str(match.get("video_id") or "")
            merged["title"] = str(match.get("title") or direct["title"])
            merged["artist"] = str(match.get("artist") or direct["artist"])
            merged["album"] = str(match.get("album") or direct["album"])
            merged["year"] = str(match.get("year") or direct["year"])
            merged["thumbnail_candidates"] = list(match.get("thumbnail_candidates") or candidates)
            merged["cover_url"] = str(match.get("cover_url") or (merged["thumbnail_candidates"][0] if merged["thumbnail_candidates"] else direct["cover_url"]))
            merged["source"] = match.get("source") or direct["source"]
            return merged
        return direct

    @staticmethod
    def _safe_name(value):
        value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(value or "Untitled"))
        value = re.sub(r"\s+", " ", value).strip(" .")
        return (value[:150] or "Untitled")

    @staticmethod
    def _language_label(code):
        value = str(code or "und").replace("_", "-").strip()
        parts = value.split("-")
        names = {
            "ab": "Abkhazian", "aa": "Afar", "af": "Afrikaans", "ak": "Akan",
            "sq": "Albanian", "am": "Amharic", "ar": "Arabic", "hy": "Armenian",
            "as": "Assamese", "ay": "Aymara", "az": "Azerbaijani", "bm": "Bambara",
            "eu": "Basque", "be": "Belarusian", "bn": "Bengali", "bh": "Bihari",
            "bs": "Bosnian", "br": "Breton", "bg": "Bulgarian", "my": "Burmese",
            "ca": "Catalan", "ceb": "Cebuano", "zh": "Chinese", "co": "Corsican",
            "hr": "Croatian", "cs": "Czech", "da": "Danish", "nl": "Dutch",
            "en": "English", "eo": "Esperanto", "et": "Estonian", "ee": "Ewe",
            "fo": "Faroese", "fa": "Persian", "fj": "Fijian", "fi": "Finnish",
            "fr": "French", "fy": "Frisian", "ff": "Fulah", "gl": "Galician",
            "lg": "Ganda", "ka": "Georgian", "de": "German", "el": "Greek",
            "gn": "Guarani", "gu": "Gujarati", "ht": "Haitian Creole", "ha": "Hausa",
            "haw": "Hawaiian", "he": "Hebrew", "hi": "Hindi", "hu": "Hungarian",
            "is": "Icelandic", "ig": "Igbo", "id": "Indonesian", "ia": "Interlingua",
            "ga": "Irish", "it": "Italian", "ja": "Japanese", "jv": "Javanese",
            "kn": "Kannada", "kk": "Kazakh", "km": "Khmer", "rw": "Kinyarwanda",
            "ko": "Korean", "ku": "Kurdish", "ky": "Kyrgyz", "lo": "Lao",
            "la": "Latin", "lv": "Latvian", "ln": "Lingala", "lt": "Lithuanian",
            "lb": "Luxembourgish", "mk": "Macedonian", "mg": "Malagasy", "ms": "Malay",
            "ml": "Malayalam", "mt": "Maltese", "mi": "Maori", "mr": "Marathi",
            "mn": "Mongolian", "ne": "Nepali", "no": "Norwegian", "ny": "Nyanja",
            "or": "Odia", "om": "Oromo", "ps": "Pashto", "pl": "Polish",
            "pt": "Portuguese", "pa": "Punjabi", "ro": "Romanian", "ru": "Russian",
            "sm": "Samoan", "sa": "Sanskrit", "gd": "Scottish Gaelic", "sr": "Serbian",
            "sn": "Shona", "sd": "Sindhi", "si": "Sinhala", "sk": "Slovak",
            "sl": "Slovenian", "so": "Somali", "es": "Spanish", "su": "Sundanese",
            "sw": "Swahili", "sv": "Swedish", "tl": "Tagalog", "tg": "Tajik",
            "ta": "Tamil", "tt": "Tatar", "te": "Telugu", "th": "Thai",
            "bo": "Tibetan", "ti": "Tigrinya", "to": "Tongan", "tr": "Turkish",
            "tk": "Turkmen", "uk": "Ukrainian", "ur": "Urdu", "ug": "Uyghur",
            "uz": "Uzbek", "vi": "Vietnamese", "cy": "Welsh", "wo": "Wolof",
            "xh": "Xhosa", "yi": "Yiddish", "yo": "Yoruba", "zu": "Zulu",
            "ja": "Japanese", "zh": "Chinese", "uk": "Ukrainian", "fa": "Persian",
        }
        base = parts[0].lower() if parts else "und"
        return names.get(base, value if value and value != "und" else "Unknown language")

    def _audio_language_name(self, fmt):
        code = str(fmt.get("language") or "").strip()
        base = code.replace("_", "-").split("-")[0].lower()
        if base not in {"", "und", "unknown", "none"}:
            label = self._language_label(code)
            if label != "Unknown language":
                return label

        note = str(fmt.get("format_note") or "").strip()
        prefix = note.split(",", 1)[0].strip()
        prefix = re.sub(r"\([^)]*\)", "", prefix)
        prefix = re.sub(r"\b(?:audio|track|original|default|medium|low|high)\b", " ", prefix, flags=re.I)
        prefix = re.sub(r"\s+", " ", prefix).strip(" -:")
        if prefix and len(prefix) <= 60:
            return prefix.title()
        return self._language_label(code)

    def _audio_language_key(self, fmt):
        code = str(fmt.get("language") or "").strip()
        base = code.replace("_", "-").split("-")[0].lower()
        if base not in {"", "und", "unknown", "none"}:
            return base

        label = self._audio_language_name(fmt)
        reverse = {
            "english": "en", "arabic": "ar", "spanish": "es", "french": "fr",
            "german": "de", "italian": "it", "portuguese": "pt", "russian": "ru",
            "japanese": "ja", "korean": "ko", "chinese": "zh", "hindi": "hi",
            "turkish": "tr", "indonesian": "id", "thai": "th", "vietnamese": "vi",
            "polish": "pl", "dutch": "nl", "swedish": "sv", "ukrainian": "uk",
            "persian": "fa", "urdu": "ur", "bengali": "bn", "tamil": "ta", "telugu": "te",
        }
        normalized = label.casefold().strip()
        if normalized in reverse:
            return reverse[normalized]
        if normalized and normalized != "unknown language":
            return "name:" + clean_text(normalized)
        return "und"

    @staticmethod
    def _language_iso639(code):
        base = str(code or "").replace("_", "-").split("-")[0].lower()
        mapping = {"en":"eng","ar":"ara","es":"spa","fr":"fra","de":"deu","it":"ita","pt":"por","ru":"rus",
                   "ja":"jpn","ko":"kor","zh":"zho","hi":"hin","tr":"tur","id":"ind","th":"tha","vi":"vie",
                   "pl":"pol","nl":"nld","sv":"swe","uk":"ukr","fa":"fas","ur":"urd","bn":"ben","ta":"tam","te":"tel",
                   "english":"eng","arabic":"ara","spanish":"spa","french":"fra","german":"deu","italian":"ita",
                   "portuguese":"por","russian":"rus","japanese":"jpn","korean":"kor","chinese":"zho","hindi":"hin",
                   "turkish":"tur","indonesian":"ind","thai":"tha","vietnamese":"vie","polish":"pol",
                   "dutch":"nld","swedish":"swe","ukrainian":"ukr","persian":"fas","urdu":"urd","bengali":"ben",
                   "tamil":"tam","telugu":"tel"}
        return mapping.get(base, "und")

    def _download_mkv_with_flac_tracks(self, url, quality, subtitles, preserve_temp=False, metadata_result=None):
        output = Path(self.download_dir).expanduser()
        output.mkdir(parents=True, exist_ok=True)
        temp = output / "tempytm"
        if preserve_temp:
            self._clear_temp_contents(temp)
        else:
            if temp.exists():
                shutil.rmtree(temp)
            temp.mkdir(parents=True, exist_ok=True)
        try:
            info = self._extract(url, flat=False, track_process=True)
            if self.cancel_event.is_set():
                raise InterruptedError("Download cancelled.")
            metadata = self._metadata_for_source(info, url, metadata_result)
            title = str(metadata.get("title") or info.get("track") or info.get("title") or info.get("id") or "Untitled")
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

            match = re.search(r"(\d{3,4})\s*p", str(quality), re.I)
            ceiling = int(match.group(1)) if match else 0
            available_heights = [
                int(fmt.get("height")) for fmt in available_video
                if fmt.get("height") and str(fmt.get("height")).isdigit()
            ]
            if ceiling and not any(height <= ceiling for height in available_heights):
                raise RuntimeError(f"No video format at or below the selected {ceiling}p quality ceiling is available.")
            selector = f"bestvideo[height<={ceiling}]" if ceiling else "bestvideo"

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
            for source_fmt in audio_formats:
                fmt = dict(source_fmt)
                language_key = self._audio_language_key(fmt)
                fmt["_toolkit_language_key"] = language_key
                fmt["_toolkit_language_label"] = self._audio_language_name(fmt)
                format_id = str(fmt.get("format_id") or "").lower()
                format_note = str(fmt.get("format_note") or "").lower()
                is_drc = format_id.endswith("-drc") or any(part.strip() == "drc" for part in format_note.split(","))
                try:
                    abr = float(fmt.get("abr") or 0)
                except (TypeError, ValueError):
                    abr = 0.0
                try:
                    asr = int(fmt.get("asr") or 0)
                except (TypeError, ValueError):
                    asr = 0
                try:
                    channels = int(fmt.get("audio_channels") or 0)
                except (TypeError, ValueError):
                    channels = 0
                try:
                    total_bitrate = float(fmt.get("tbr") or 0)
                except (TypeError, ValueError):
                    total_bitrate = 0.0
                rank = (0 if is_drc else 1, abr, asr, channels, total_bitrate)
                previous = by_language.get(language_key)
                if previous is None or rank > previous[0]:
                    by_language[language_key] = (rank, fmt)
            tracks = [pair[1] for pair in by_language.values()]
            tracks.sort(key=lambda fmt: (
                0 if fmt.get("language_preference", 0) and float(fmt.get("language_preference") or 0) > 0 else 1,
                str(fmt.get("_toolkit_language_label") or "Unknown language").lower(),
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
                language_label = str(fmt.get("_toolkit_language_label") or self._language_label(language))
                safe_language = re.sub(r"[^a-zA-Z0-9_-]+", "_", language_label.casefold())[:18] or f"track{index}"
                audio_target = temp / f"audio_{index:02d}_{safe_language}.%(ext)s"
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
                label = language_label
                self._log(f"Downloading {label} audio track ({index}/{len(tracks)})")
                self._run_stage(audio_cmd, label, start, span)
                matches = [p for p in temp.glob(f"audio_{index:02d}_{safe_language}.*") if p.is_file() and p.suffix.lower() == ".flac"]
                if not matches:
                    raise RuntimeError(f"The {label} audio track did not produce a FLAC file.")
                audio_paths.append(matches[0])
                track_meta = dict(metadata)
                self._apply_ytmusic_flac_metadata(matches[0], track_meta, embed_cover=True)
                track_labels.append((label, self._language_iso639(language if language.lower() not in {"", "und", "unknown"} else label)))

            cover_path = temp / "cover.jpg"
            thumbnail_url = str(metadata.get("cover_url") or info.get("thumbnail") or "")
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
            source_artist = str(metadata.get("artist") or info.get("artist") or info.get("creator") or info.get("uploader") or info.get("channel") or "").strip()
            source_album = str(metadata.get("album") or info.get("album") or "").strip()
            source_year = str(metadata.get("year") or info.get("release_year") or info.get("upload_date") or "").strip()[:4]
            if source_artist:
                merge_cmd.extend(["-metadata", f"artist={source_artist}"])
            if source_album:
                merge_cmd.extend(["-metadata", f"album={source_album}"])
            if source_year:
                merge_cmd.extend(["-metadata", f"date={source_year}"])
            for track_index, (label, language_code) in enumerate(track_labels):
                merge_cmd.extend([f"-metadata:s:a:{track_index}", f"title={label}"])
                merge_cmd.extend([f"-metadata:s:a:{track_index}", f"language={language_code}"])
            if cover_path.exists():
                merge_cmd.extend(["-attach", str(cover_path), "-metadata:s:t", "mimetype=image/jpeg",
                                  "-metadata:s:t", "filename=cover.jpg"])
            if self.conflict_mode == "replace":
                merge_cmd.append("-y")
            staged_final = temp / final_path.name
            merge_cmd.append(str(staged_final))
            self.statusChanged.emit("Muxing video and language-specific FLAC audio tracks…")
            self._log(f"Merging {len(audio_paths)} FLAC audio track(s) into {final_path.name}")
            self.progressChanged.emit(90, "Muxing audio tracks into MKV")
            self._run_stage(merge_cmd, "Mux", 90, 10)
            if not staged_final.is_file() or staged_final.stat().st_size <= 0:
                raise RuntimeError("FFmpeg finished without producing the staged MKV output.")
            os.replace(staged_final, final_path)

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
            if preserve_temp:
                self._clear_temp_contents(temp)
            else:
                shutil.rmtree(temp, ignore_errors=True)

    def _download_one(self, url, file_type, quality, audio_format, subtitles, preserve_temp=False, metadata_result=None):
        if file_type == "Video (MKV)":
            return self._download_mkv_with_flac_tracks(url, quality, subtitles, preserve_temp=preserve_temp, metadata_result=metadata_result)

        output = Path(self.download_dir).expanduser()
        output.mkdir(parents=True, exist_ok=True)
        temp = output / "tempytm"
        if preserve_temp:
            self._clear_temp_contents(temp)
        else:
            if temp.exists():
                shutil.rmtree(temp)
            temp.mkdir(parents=True, exist_ok=True)

        try:
            # All staging and intermediate files live in tempytm. Only completed
            # media and explicitly requested subtitle sidecars leave this folder.
            info = self._extract(url, flat=False, track_process=True)
            if self.cancel_event.is_set():
                raise InterruptedError("Download cancelled.")
            metadata = self._metadata_for_source(info, url, metadata_result)
            title = str(metadata.get("title") or info.get("track") or info.get("title") or info.get("id") or "Untitled")
            video_id = str(info.get("id") or metadata.get("video_id") or uuid.uuid4().hex[:8])
            guessed_stem = self._safe_name(f"{title} [{video_id}]")
            expected_extension = {
                "FLAC": ".flac", "MP3": ".mp3", "M4A": ".m4a", "Opus": ".opus"
            }.get(audio_format, ".flac") if file_type == "Audio only" else (
                ".mp4" if file_type == "Video (MP4)" else ".mkv"
            )
            predicted_output = output / (guessed_stem + expected_extension)
            if self.conflict_mode == "skip" and predicted_output.exists():
                self._log(f"Skipped existing output: {predicted_output.name}")
                self.statusChanged.emit(f"Skipped existing file: {predicted_output.name}")
                return True

            staging_template = str(temp / "%(title).180B [%(id)s].%(ext)s")
            cmd = self._base_command(True) + self._format_args(file_type, quality, audio_format)
            cmd += [
                "--output", staging_template,
                "--paths", f"temp:{temp}",
                "--windows-filenames",
                "--embed-metadata",
                "--embed-thumbnail",
                "--write-thumbnail",
                "--convert-thumbnails", "jpg",
            ]
            if subtitles == "Auto subtitles":
                cmd += ["--write-auto-subs", "--sub-langs", "all,-live_chat"]
            elif subtitles == "Manual subtitles":
                cmd += ["--write-subs", "--sub-langs", "all,-live_chat"]

            cmd += [
                "--progress-template",
                "download:__YT_PROGRESS__%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
                url,
            ]
            active_command = list(cmd)
            for attempt in range(2):
                process = subprocess.Popen(
                    active_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    encoding="utf-8", errors="replace", bufsize=1, **hidden_kwargs()
                )
                with self.process_lock:
                    self.active_process = process
                    self.paused = False

                tail = []
                try:
                    assert process.stdout is not None
                    for line in process.stdout:
                        line = line.rstrip()
                        if not line:
                            continue
                        tail.append(line)
                        tail = tail[-45:]
                        if line.startswith("__YT_PROGRESS__"):
                            fields = line[len("__YT_PROGRESS__"):].split("|")
                            try:
                                percent = float(fields[0].replace("%", "").strip())
                            except (ValueError, IndexError):
                                percent = 0.0
                            detail = " • ".join(x.strip() for x in fields[1:] if x.strip())
                            self.progressChanged.emit(percent, f"{percent:.1f}% {detail}".strip())
                        elif "Destination:" in line or "Merging formats" in line or "ERROR:" in line or "WARNING:" in line:
                            self.logMessage.emit(line)
                        if self.cancel_event.is_set():
                            self._terminate_process_tree(process)
                            break
                    code = process.wait()
                    if self.cancel_event.is_set():
                        raise InterruptedError("Download cancelled.")
                finally:
                    with self.process_lock:
                        if self.active_process is process:
                            self.active_process = None
                        self.paused = False
                    try:
                        if process.poll() is None:
                            self._terminate_process_tree(process)
                    except Exception:
                        pass

                if code == 0:
                    break

                native_command = build_native_ytdlp_fallback_command(active_command)
                aria2_error = any("aria2c" in line.lower() for line in tail)
                if attempt == 0 and aria2_error and native_command:
                    self._log("aria2c failed during download; retrying once with yt-dlp's native downloader.")
                    active_command = native_command
                    continue

                raise RuntimeError("\\n".join(tail[-14:]) or f"yt-dlp exited with {code}")

            expected_media = {
                ".flac", ".mp3", ".m4a", ".mp4", ".mkv", ".webm", ".opus",
                ".ogg", ".wav", ".aac", ".wma", ".m4v", ".mov"
            }
            staged_files = [item for item in temp.iterdir() if item.is_file()]
            media_files = [
                item for item in staged_files
                if item.suffix.lower() in expected_media
                and not item.name.lower().endswith((".part", ".ytdl", ".tmp", ".temp"))
            ]
            preferred = [item for item in media_files if item.suffix.lower() == expected_extension]
            if not preferred:
                preferred = media_files
            if not preferred:
                raise RuntimeError("yt-dlp completed, but no final media file was found inside tempytm.")
            media_source = max(preferred, key=lambda item: item.stat().st_mtime)
            source_stem = media_source.stem
            self._apply_download_metadata(media_source, metadata)

            desired_stem = self._safe_name(f"{metadata.get('title') or source_stem} [{metadata.get('video_id') or video_id}]")
            desired_name = desired_stem + media_source.suffix.lower()
            media_target = output / desired_name
            if self.conflict_mode == "skip":
                if media_target.exists():
                    self._log(f"Skipped completed duplicate: {media_target.name}")
                    return True
            elif self.conflict_mode == "rename":
                suffix = 2
                while media_target.exists():
                    media_target = output / f"{desired_stem} ({suffix}){media_source.suffix.lower()}"
                    suffix += 1

            os.replace(media_source, media_target)
            self._log(f"Completed media exported from tempytm: {media_target.name}")

            subtitle_extensions = {".vtt", ".srt", ".ass", ".ssa", ".lrc", ".ttml"}
            if subtitles in {"Auto subtitles", "Manual subtitles"}:
                for sidecar in list(temp.iterdir()):
                    if not sidecar.is_file() or sidecar.suffix.lower() not in subtitle_extensions:
                        continue
                    mapped_name = sidecar.name
                    if source_stem and source_stem in mapped_name:
                        mapped_name = mapped_name.replace(source_stem, media_target.stem, 1)
                    sidecar_target = output / mapped_name
                    if self.conflict_mode == "rename" and sidecar_target.exists():
                        sidecar_target = self._unique_sidecar_path(output, mapped_name)
                    try:
                        os.replace(sidecar, sidecar_target)
                    except OSError as exc:
                        self._log(f"Subtitle sidecar could not be exported ({sidecar.name}): {exc}")

            self.progressChanged.emit(100, "Download complete")
            return True
        finally:
            with self.process_lock:
                self.active_process = None
                self.paused = False
            if preserve_temp:
                self._clear_temp_contents(temp)
            else:
                shutil.rmtree(temp, ignore_errors=True)

    @staticmethod
    def _unique_sidecar_path(folder, filename):
        path = Path(filename)
        candidate = Path(folder) / path.name
        n = 2
        while candidate.exists():
            candidate = Path(folder) / f"{path.stem} ({n}){path.suffix}"
            n += 1
        return candidate

    @Slot(str, str, str, str, str)
    def startDownload(self, url, file_type, quality, audio_format, subtitles):
        requested = str(url or "").strip()
        if self.download_active:
            self.statusChanged.emit("A download is already active.")
            return
        if not requested:
            self.statusChanged.emit("Paste a URL or enter Artist - Title first.")
            return
        if self._is_playlist_url(requested):
            self.addQueueUrl(requested)
            return
        self.cancel_event.clear()
        self.download_active = True
        def work():
            try:
                actual_url, metadata_result = self._resolve_user_input_with_metadata(requested)
                if actual_url != requested:
                    self.statusChanged.emit("YouTube Music match resolved; starting exact video download…")
                self.download_percent = 0
                self._download_one(actual_url, file_type, quality, audio_format, subtitles, metadata_result=metadata_result)
                return {"_kind": "download", "ok": True, "message": "Download finished successfully."}
            finally:
                self.download_active = False
        self.last_operation_id = self._run_async("download", work)
        self.statusChanged.emit("Download started.")
        self._log(f"Download requested: {requested}")

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

    @Slot(str, str, str, str, str)
    def addQueueUrl(self, url, file_type, quality, audio_format, subtitles):
        url = str(url or "").strip()
        file_type = str(file_type or self.file_type)
        quality = str(quality or self.quality)
        audio_format = str(audio_format or self.audio_format)
        subtitles = str(subtitles or self.subtitle_mode)
        if not url:
            self.statusChanged.emit("Paste a URL to add it to the queue.")
            return

        def work():
            if self._is_liked_music_url(url):
                tracks = YTMResolver().liked_songs(cookie_path=self.cookie_path)
                rows = []
                for track in tracks:
                    rows.append({
                        "id": uuid.uuid4().hex[:10],
                        "file_type": file_type,
                        "quality": quality,
                        "audio_format": audio_format,
                        "subtitle_mode": subtitles,
                        "title": str(track.get("title") or track.get("video_id") or "Liked track"),
                        "url": str(track.get("source_url") or ""),
                        "video_id": str(track.get("video_id") or ""),
                        "artist": str(track.get("artist") or ""),
                        "album": str(track.get("album") or ""),
                        "ytm_metadata": track.get("ytm_metadata") or {},
                        "ytm_enrich": True,
                        "status": "Pending",
                        "duration": str(track.get("duration") or "—"),
                    })
                if not rows:
                    raise RuntimeError("Liked Music did not return any usable tracks.")
                return {"_kind": "queue", "items": self.queue_items + rows,
                        "message": f"Added {len(rows)} Liked Music tracks to the queue."}
            try:
                data = self._extract(url, flat=True)
                entries = data.get("entries")
                rows = []
                if isinstance(entries, list) and entries:
                    seen = set()
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                        vid = str(entry.get("id") or entry.get("video_id") or entry.get("videoId") or "").strip()
                        source = str(entry.get("webpage_url") or entry.get("url") or "").strip()
                        if vid and not source.startswith(("http://", "https://")):
                            source = f"https://www.youtube.com/watch?v={vid}"
                        if source and source not in seen:
                            seen.add(source)
                            artist_value = entry.get("artist") or entry.get("creator") or entry.get("uploader") or entry.get("channel") or ""
                            if isinstance(artist_value, (list, tuple)):
                                artist_value = ", ".join(str(name).strip() for name in artist_value if str(name).strip())
                            album_value = entry.get("album") or ""
                            if isinstance(album_value, dict):
                                album_value = str(album_value.get("name") or "")
                            rows.append({
                                "id": uuid.uuid4().hex[:10],
                                "file_type": file_type,
                                "quality": quality,
                                "audio_format": audio_format,
                                "subtitle_mode": subtitles,
                                "title": str(entry.get("track") or entry.get("title") or vid or source),
                                "url": source,
                                "video_id": vid,
                                "artist": str(artist_value or ""),
                                "album": str(album_value or ""),
                                "year": str(entry.get("release_year") or entry.get("upload_date") or "")[:4],
                                "ytm_enrich": "music.youtube.com" in url.lower(),
                                "status": "Pending",
                                "duration": self._duration(entry.get("duration")),
                            })
                if not rows:
                    source = str(data.get("webpage_url") or url)
                    artist_value = data.get("artist") or data.get("creator") or data.get("uploader") or data.get("channel") or ""
                    if isinstance(artist_value, (list, tuple)):
                        artist_value = ", ".join(str(name).strip() for name in artist_value if str(name).strip())
                    album_value = data.get("album") or ""
                    if isinstance(album_value, dict):
                        album_value = str(album_value.get("name") or "")
                    rows.append({
                        "id": uuid.uuid4().hex[:10],
                        "file_type": file_type,
                        "quality": quality,
                        "audio_format": audio_format,
                        "subtitle_mode": subtitles,
                        "title": str(data.get("track") or data.get("title") or url),
                        "url": source,
                        "video_id": str(data.get("id") or ""),
                        "artist": str(artist_value or ""),
                        "album": str(album_value or ""),
                        "year": str(data.get("release_year") or data.get("upload_date") or "")[:4],
                        "ytm_enrich": "music.youtube.com" in url.lower(),
                        "status": "Pending",
                        "duration": self._duration(data.get("duration")),
                    })
                return {"_kind": "queue", "items": self.queue_items + rows,
                        "message": f"Added {len(rows)} item(s) to queue."}
            except Exception:
                if self._is_playlist_url(url):
                    raise
                return {"_kind": "queue", "items": self.queue_items + [{
                    "id": uuid.uuid4().hex[:10], "title": url, "url": url,
                    "file_type": file_type, "quality": quality,
                    "audio_format": audio_format, "subtitle_mode": subtitles,
                    "status": "Pending", "duration": "—"
                }], "message": "Added URL to queue; details will be resolved when downloading."}

        self.statusChanged.emit("Resolving URL / playlist for queue…")
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
            queue_temp = Path(self.download_dir).expanduser() / "tempytm"
            try:
                if queue_temp.exists():
                    shutil.rmtree(queue_temp)
                queue_temp.mkdir(parents=True, exist_ok=True)
                for item in pending:
                    if self.cancel_event.is_set():
                        break
                    item["status"] = "Downloading"
                    self.queue_items = [dict(x) for x in self.queue_items]
                    for current in self.queue_items:
                        if current.get("id") == item.get("id"):
                            current["status"] = "Downloading"
                    self.queueChanged.emit(self.queue_items)
                    self._save_config()
                    self.statusChanged.emit(f"Downloading: {item['title']}")
                    try:
                        actual_url, metadata_result = self._resolve_user_input_with_metadata(item["url"])
                        if item.get("ytm_metadata") and isinstance(item.get("ytm_metadata"), dict):
                            known = dict(item["ytm_metadata"])
                            known_id = str(known.get("video_id") or "").strip()
                            queued_id = str(item.get("video_id") or "").strip()
                            if known_id and queued_id and known_id == queued_id:
                                metadata_result = known
                        elif item.get("ytm_enrich"):
                            queued_id = str(item.get("video_id") or "").strip()
                            artist = str(item.get("artist") or "").strip()
                            title = str(item.get("title") or "").strip()
                            album = str(item.get("album") or "").strip()
                            if queued_id and title:
                                try:
                                    candidate = YTMResolver().search(artist, title, album)
                                    if str((candidate or {}).get("video_id") or "").strip() == queued_id:
                                        metadata_result = candidate
                                    elif candidate:
                                        self._log(f"Rejected playlist YT Music metadata for {title}: video ID did not match.")
                                except Exception as exc:
                                    self._log(f"Playlist YT Music metadata lookup failed for {title}: {exc}")
                        item_file_type = str(item.get("file_type") or file_type)
                        if item_file_type not in {"Video (MKV)", "Video (MP4)", "Audio only"}:
                            item_file_type = file_type
                        item_quality = str(item.get("quality") or quality)
                        item_audio_format = str(item.get("audio_format") or audio_format)
                        item_subtitles = str(item.get("subtitle_mode") or subtitles)
                        self._download_one(actual_url, item_file_type, item_quality, item_audio_format, item_subtitles,
                                           preserve_temp=True, metadata_result=metadata_result)
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
                    self._save_config()
                message = f"Queue finished: {completed} completed, {failed} failed."
                if self.cancel_event.is_set():
                    message = f"Queue stopped: {completed} completed, {failed} failed."
                return {"_kind": "download", "ok": failed == 0, "message": message}
            finally:
                self.download_active = False
                shutil.rmtree(queue_temp, ignore_errors=True)
        self.last_operation_id = self._run_async("queue-run", work)

    @staticmethod
    def _tag_text(tags, key):
        try:
            value = tags.get(key) or []
            if isinstance(value, (list, tuple)):
                return ", ".join(str(item).strip() for item in value if str(item).strip())
            return str(value or "").strip()
        except Exception:
            return ""

    def _cover_bytes_from_result(self, result):
        candidates = list(result.get("thumbnail_candidates") or [])
        if result.get("cover_url"):
            candidates.insert(0, result["cover_url"])
        seen = set()
        for candidate in candidates:
            url = canonicalize_thumbnail_url(candidate)
            if not url or url in seen:
                continue
            seen.add(url)
            try:
                response = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
                response.raise_for_status()
                from io import BytesIO
                with Image.open(BytesIO(response.content)) as image:
                    normalized = ImageOps.exif_transpose(image).convert("RGB")
                    buffer = BytesIO()
                    normalized.save(buffer, "JPEG", quality=100, subsampling=0)
                    return buffer.getvalue()
            except Exception as exc:
                self._log(f"Artwork candidate failed; trying the next YT Music image: {exc}")
        return b""

    @staticmethod
    def _set_flac_tag(flac, key, value):
        value = str(value or "").strip()
        if value:
            flac[key] = [value]
        else:
            try:
                del flac[key]
            except KeyError:
                pass

    def _apply_ytmusic_flac_metadata(self, path, result, embed_cover=True):
        flac = FLAC(str(path))
        self._set_flac_tag(flac, "title", result.get("title"))
        self._set_flac_tag(flac, "artist", result.get("artist"))
        self._set_flac_tag(flac, "album", result.get("album"))
        self._set_flac_tag(flac, "date", result.get("year"))
        for key in ("albumartist", "album artist"):
            try:
                del flac[key]
            except KeyError:
                pass
        if embed_cover:
            cover_bytes = self._cover_bytes_from_result(result)
            if cover_bytes:
                picture = Picture()
                picture.type = 3
                picture.mime = "image/jpeg"
                picture.desc = "Cover"
                picture.data = cover_bytes
                flac.clear_pictures()
                flac.add_picture(picture)
        flac.save()

    def _apply_download_metadata(self, path, metadata):
        """Apply resolved source tags and the best matching artwork to downloaded media."""
        path = Path(path)
        ext = path.suffix.lower()
        title = str(metadata.get("title") or "").strip()
        artist = str(metadata.get("artist") or "").strip()
        album = str(metadata.get("album") or "").strip()
        year = str(metadata.get("year") or "").strip()
        if ext == ".flac":
            self._apply_ytmusic_flac_metadata(path, metadata, embed_cover=True)
            return

        try:
            media = MutagenFile(str(path), easy=True)
            if media is not None:
                if media.tags is None:
                    media.add_tags()
                for key, value in (("title", title), ("artist", artist), ("album", album), ("date", year)):
                    try:
                        if value:
                            media.tags[key] = [value]
                        elif key in media.tags:
                            del media.tags[key]
                    except (KeyError, TypeError):
                        pass
                try:
                    for key in ("albumartist", "album artist"):
                        try:
                            del media.tags[key]
                        except (KeyError, TypeError):
                            pass
                except Exception:
                    pass
                media.save()
        except Exception as exc:
            self._log(f"Tag writing skipped for {path.name}: {exc}")

        if ext not in {".mp3", ".m4a", ".mp4", ".m4v", ".mov", ".opus", ".ogg"}:
            return
        cover_bytes = self._cover_bytes_from_result(metadata)
        if not cover_bytes:
            return
        try:
            if ext == ".mp3":
                tags = ID3(str(path))
                tags.delall("APIC")
                tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_bytes))
                tags.save(str(path))
            elif ext in {".m4a", ".mp4", ".m4v", ".mov"}:
                mp4 = MP4(str(path))
                mp4["covr"] = [MP4Cover(cover_bytes, imageformat=MP4Cover.FORMAT_JPEG)]
                mp4.save()
            elif ext in {".opus", ".ogg"}:
                import base64
                picture = Picture()
                picture.type = 3
                picture.mime = "image/jpeg"
                picture.desc = "Cover"
                picture.data = cover_bytes
                encoded = base64.b64encode(picture.write()).decode("ascii")
                media = MutagenFile(str(path), easy=True)
                if media is not None:
                    media["metadata_block_picture"] = [encoded]
                    media.save()
        except Exception as exc:
            self._log(f"Artwork could not be embedded into {path.name}: {exc}")

    @Slot(str)
    def rewriteFolderMetadata(self, folder):
        folder = str(folder or "").strip()

        def work():
            root = Path(folder)
            if not root.is_dir():
                raise NotADirectoryError("Choose a valid metadata folder.")
            files = [p for p in root.rglob("*.flac") if p.is_file()]
            if not files:
                raise RuntimeError("No FLAC files were found in this folder.")
            resolver = YTMResolver()
            changed = failed = unmatched = 0
            total = len(files)
            for index, path in enumerate(files, 1):
                self.progressChanged.emit((index - 1) * 100 / total, f"Metadata {index}/{total}: {path.name}")
                try:
                    flac = FLAC(str(path))
                    artist = self._tag_text(flac, "artist")
                    title = self._tag_text(flac, "title") or path.stem
                    album = self._tag_text(flac, "album")
                    if not artist and " - " in path.stem:
                        artist, title_from_name = split_artist_title(path.stem)
                        title = title_from_name or title
                    result = resolver.search(artist, title, album)
                    if not result:
                        unmatched += 1
                        self._log(f"No YouTube Music match for {path.name}; left unchanged.")
                        continue
                    self._apply_ytmusic_flac_metadata(path, result, embed_cover=True)
                    changed += 1
                    self._log(f"Updated tags and artwork: {path.name} → {result.get('title') or title}")
                except Exception as exc:
                    failed += 1
                    self._log(f"Metadata rewrite failed for {path.name}: {exc}")
            self.progressChanged.emit(100.0, "Metadata rewrite complete")
            return {"_kind": "done", "ok": failed == 0,
                    "message": f"Metadata rewrite finished: {changed} updated, {unmatched} unmatched, {failed} failed."}

        self.statusChanged.emit("Preparing batch YouTube Music metadata rewrite…")
        self._run_async("metadata-batch-rewrite", work)

    @Slot(str)
    def upgradeFolderCovers(self, folder):
        folder = str(folder or "").strip()

        def work():
            root = Path(folder)
            if not root.is_dir():
                raise NotADirectoryError("Choose a valid cover-art folder.")
            files = [p for p in root.rglob("*.flac") if p.is_file()]
            if not files:
                raise RuntimeError("No FLAC files were found in this folder.")
            resolver = YTMResolver()
            updated = failed = unmatched = 0
            total = len(files)
            for index, path in enumerate(files, 1):
                self.progressChanged.emit((index - 1) * 100 / total, f"Cover art {index}/{total}: {path.name}")
                try:
                    flac = FLAC(str(path))
                    artist = self._tag_text(flac, "artist")
                    title = self._tag_text(flac, "title") or path.stem
                    album = self._tag_text(flac, "album")
                    if not artist and " - " in path.stem:
                        artist, title_from_name = split_artist_title(path.stem)
                        title = title_from_name or title
                    result = resolver.search(artist, title, album)
                    if not result:
                        unmatched += 1
                        self._log(f"No YouTube Music artwork match for {path.name}; left unchanged.")
                        continue
                    cover_bytes = self._cover_bytes_from_result(result)
                    if not cover_bytes:
                        failed += 1
                        self._log(f"No usable artwork could be downloaded for {path.name}.")
                        continue
                    picture = Picture()
                    picture.type = 3
                    picture.mime = "image/jpeg"
                    picture.desc = "Cover"
                    picture.data = cover_bytes
                    flac.clear_pictures()
                    flac.add_picture(picture)
                    flac.save()
                    updated += 1
                    self._log(f"Updated cover art: {path.name}")
                except Exception as exc:
                    failed += 1
                    self._log(f"Cover upgrade failed for {path.name}: {exc}")
            self.progressChanged.emit(100.0, "Cover upgrade complete")
            return {"_kind": "done", "ok": failed == 0,
                    "message": f"Cover upgrade finished: {updated} updated, {unmatched} unmatched, {failed} failed."}

        self.statusChanged.emit("Preparing batch YouTube Music cover upgrade…")
        self._run_async("cover-batch-upgrade", work)

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
            artist_from_name, title_from_name = split_artist_title(Path(path).stem)
            artist = artist or artist_from_name
            title = title or title_from_name
        if not artist and not title:
            self.statusChanged.emit("Enter an artist/title or choose a media file first.")
            return

        def work():
            result = YTMResolver().search(artist, title, album)
            if not result:
                raise RuntimeError("YouTube Music returned no matching songs or videos.")
            path_value = str(Path(path).resolve()) if path else ""
            return {
                "_kind": "metadata",
                "path": path_value,
                "title": result.get("title") or title,
                "artist": result.get("artist") or artist,
                "album": result.get("album") or album,
                "date": result.get("year") or "",
                "genre": "",
                "comment": "",
                "thumbnail": result.get("cover_url") or "",
                "video_id": result.get("video_id") or "",
                "source": result.get("source") or "",
            }

        self.statusChanged.emit("Searching YouTube Music (exact contributing-artist match first)…")
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
            elif ext in {".mp4", ".m4v", ".mov"}:
                ffmpeg = find_tool("ffmpeg")
                if not ffmpeg:
                    raise RuntimeError("FFmpeg was not found.")
                cover = path.with_name("." + path.stem + ".cover-tmp.jpg")
                temp_out = path.with_name("." + path.stem + ".cover-tmp" + ext)
                cover.write_bytes(data)
                try:
                    p = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                                        "-i", str(path), "-i", str(cover), "-map", "0", "-map", "1:v:0",
                                        "-c", "copy", "-disposition:v:1", "attached_pic",
                                        "-metadata:s:v:1", "title=Cover", "-metadata:s:v:1", "comment=Cover",
                                        "-movflags", "+faststart", str(temp_out)],
                                       capture_output=True, text=True, timeout=180, **hidden_kwargs())
                    if p.returncode:
                        raise RuntimeError((p.stderr or "Could not embed the cover")[-1200:])
                    os.replace(temp_out, path)
                finally:
                    cover.unlink(missing_ok=True)
                    temp_out.unlink(missing_ok=True)
            else:
                raise ValueError("Artwork embedding supports FLAC, MP3, M4A, MKV, MP4, M4V, and MOV.")
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
