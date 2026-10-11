import os
import re
import json
import time
import sys
import subprocess
import threading
from queue import Empty, Queue
import shutil
import traceback
import urllib.parse
import tempfile
import hashlib
import http.cookiejar
import http.cookies
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from io import BytesIO

import requests
import customtkinter as ctk
from tkinter import filedialog, messagebox, Misc, StringVar, Canvas, Toplevel
from PIL import Image, ImageDraw, ImageGrab, ImageOps, ImageTk

from mutagen.flac import FLAC, Picture, StreamInfo
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, APIC
from mutagen.mp4 import MP4, MP4Cover
from ytmusicapi import YTMusic

try:
    from ytmusicapi.constants import USER_AGENT as YTMUSICAPI_USER_AGENT
except ImportError:
    YTMUSICAPI_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:88.0) "
        "Gecko/20100101 Firefox/88.0"
    )


# ============================================================
# YTM MUSIC TOOLKIT
# ============================================================
# One windowed .pyw application merging the downloader,
# metadata rewriter, cover updater, and crop tools.
#
# Source of truth:
#   YouTube / YouTube Music via ytmusicapi
#
# Matching policy:
#   1) YT Music "songs" filter
#   2) exact contributing-artist-name match
#   3) best title match
#   4) YT Music "videos" fallback
#
# Spotify / Deezer are intentionally not used.
# ============================================================


APP_NAME = "YTM Music Toolkit v3"
APP_FONT = "SF Pro Text"

# Apple-inspired dark appearance: graphite surfaces, quiet separators,
# high-contrast text, and restrained system accent colors.
APPLE_WINDOW_BG = "#1C1C1E"
APPLE_ROOT_BG = "#0B0B0C"
APPLE_SURFACE = "#2C2C2E"
APPLE_SURFACE_ELEVATED = "#3A3A3C"
APPLE_INPUT_BG = "#232325"
APPLE_CONSOLE_BG = "#171719"
APPLE_SEPARATOR = "#3D3D40"
APPLE_SEPARATOR_HOVER = "#5B5B60"
APPLE_TEXT = "#F5F5F7"
APPLE_MUTED = "#98989D"
APPLE_BLUE = "#0A84FF"
APPLE_BLUE_HOVER = "#409CFF"
APPLE_BLUE_PRESSED = "#0066CC"
APPLE_GREEN = "#30D158"
APPLE_ORANGE = "#FF9F0A"
APPLE_RED = "#FF453A"

APPLE_THEME_PALETTES = {
    "dark": {
        "root_bg": "#0B0B0C",
        "window_bg": "#1C1C1E",
        "surface": "#2C2C2E",
        "surface_elevated": "#3A3A3C",
        "input_bg": "#232325",
        "console_bg": "#171719",
        "separator": "#3D3D40",
        "separator_hover": "#5B5B60",
        "text": "#F5F5F7",
        "muted": "#98989D",
        "blue": "#0A84FF",
        "blue_hover": "#409CFF",
        "blue_pressed": "#0066CC",
        "green": "#30D158",
        "green_pulse": "#69E889",
        "orange": "#FF9F0A",
        "orange_pulse": "#FFD080",
        "red": "#FF453A",
        "red_hover": "#FF6961",
        "badge_bg": "#223956",
        "badge_border": "#365B86",
    },
    "light": {
        "root_bg": "#E5E5EA",
        "window_bg": "#F2F2F7",
        "surface": "#FFFFFF",
        "surface_elevated": "#F2F2F7",
        "input_bg": "#FFFFFF",
        "console_bg": "#F8F8FA",
        "separator": "#D1D1D6",
        "separator_hover": "#AEAEB2",
        "text": "#1C1C1E",
        "muted": "#6C6C70",
        "blue": "#007AFF",
        "blue_hover": "#0066CC",
        "blue_pressed": "#004999",
        "green": "#248A3D",
        "green_pulse": "#34A853",
        "orange": "#C93400",
        "orange_pulse": "#E56B1F",
        "red": "#D70015",
        "red_hover": "#B00012",
        "badge_bg": "#E2EEFF",
        "badge_border": "#B7D3FF",
    },
}
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".ytm_music_toolkit.json")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
REQUEST_TIMEOUT = 20
REQUEST_DELAY = 0.7

# All operation failures are persisted here. On the user's Windows
# profile this resolves to: C:\Users\Souhaib Bokka\Documents\YTDLP
FAILURE_LOG_DIR = os.path.join(
    os.path.expanduser("~"),
    "Documents",
    "YTDLP",
)


def ensure_failure_log_dir():
    Path(FAILURE_LOG_DIR).mkdir(
        parents=True,
        exist_ok=True,
    )
    return Path(FAILURE_LOG_DIR)


def write_failure_log(context, exc, details=None):
    """Persist a detailed failure report without exposing cookie contents."""
    try:
        directory = ensure_failure_log_dir()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_context = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "_",
            str(context or "failure"),
        ).strip("_") or "failure"
        unique = time.time_ns() % 1_000_000_000
        log_path = directory / f"FAILURE_{timestamp}_{unique:09d}_{safe_context}.log"

        lines = [
            "YTM MUSIC TOOLKIT FAILURE LOG",
            "=" * 72,
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Context: {context}",
            f"Exception: {type(exc).__name__}",
            f"Message: {exc}",
            f"Python: {sys.version}",
            f"Working Directory: {os.getcwd()}",
        ]

        if details:
            lines.extend(["", "Details:", str(details)])

        lines.extend([
            "",
            "Traceback:",
            traceback.format_exc(),
        ])

        log_path.write_text(
            "\n".join(lines),
            encoding="utf-8",
        )
        return str(log_path)
    except Exception:
        return None

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


# ============================================================
# WINDOWS / RESOURCE HELPERS
# ============================================================

def get_resource_dir():
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


RESOURCE_DIR = get_resource_dir()
os.environ["PATH"] = RESOURCE_DIR + os.pathsep + os.environ.get("PATH", "")

try:
    import pyi_splash
except ImportError:
    pyi_splash = None


if os.name == "nt":
    try:
        import ctypes
        from ctypes import wintypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ytm.music.toolkit.v1"
        )
        COMTYPES_AVAILABLE = True
    except Exception:
        ctypes = None
        wintypes = None
        COMTYPES_AVAILABLE = False
else:
    ctypes = None
    wintypes = None
    COMTYPES_AVAILABLE = False


def get_hidden_subprocess_kwargs():
    startupinfo = None
    creationflags = 0

    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = subprocess.CREATE_NO_WINDOW

    return {
        "startupinfo": startupinfo,
        "creationflags": creationflags,
    }


def find_executable(name):
    candidates = [
        os.path.join(RESOURCE_DIR, name),
        os.path.join(RESOURCE_DIR, name + ".exe"),
        os.path.join(os.path.dirname(sys.executable), name),
        os.path.join(os.path.dirname(sys.executable), name + ".exe"),
    ]

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    return shutil.which(name) or shutil.which(name + ".exe")


def get_ytdlp_command():
    exe = find_executable("yt-dlp")
    return exe or "yt-dlp"


def get_concurrent_fragment_count(performance_mode="aggressive"):
    """Return native DASH/HLS concurrency for the selected speed preset."""
    return {
        "conservative": 4,
        "balanced": 12,
        "aggressive": 24,
    }.get(str(performance_mode or "aggressive").strip().lower(), 24)


def get_ytdlp_runtime_args(performance_mode=None):
    """Return lightweight extraction args unless this is an actual media download."""
    args = ["--remote-components", "ejs:github"]

    deno = find_executable("deno")
    if not deno:
        default_deno = Path.home() / ".deno" / "bin" / "deno.exe"
        if default_deno.is_file():
            deno = str(default_deno)

    if deno:
        args.extend(["--js-runtimes", f"deno:{deno}"])

    # Metadata, previews, and playlist enumeration only need the extractor
    # runtime. Do not initialize aria2, large read buffers, or HTTP chunking
    # until the user has actually started a media transfer.
    if performance_mode is None:
        return args

    mode = str(performance_mode or "aggressive").strip().lower()
    profiles = {
        "conservative": {"buffer": "1M", "connections": 4, "split": "4M"},
        "balanced": {"buffer": "2M", "connections": 8, "split": "2M"},
        "aggressive": {"buffer": "4M", "connections": 16, "split": "1M"},
    }
    profile = profiles.get(mode, profiles["aggressive"])
    args.extend(["--buffer-size", profile["buffer"], "--resize-buffer"])

    # aria2 can split direct HTTP/HTTPS media URLs across multiple ranges.
    # Keep DASH/HLS on yt-dlp's native fragment downloader.
    aria2 = find_executable("aria2c")
    if aria2:
        connections = profile["connections"]
        args.extend([
            "--downloader", "aria2c",
            "--downloader", "dash,m3u8:native",
            "--downloader-args",
            f"aria2c:-x {connections} -s {connections} -k {profile['split']} "
            "--file-allocation=none --no-conf=true "
            "--max-download-limit=0 --max-overall-download-limit=0",
        ])
    # Without aria2c, keep yt-dlp's native HTTP request strategy untouched.
    # Forced HTTP chunking can leave some YouTube media streams stalled mid-download.

    return args


def build_native_ytdlp_fallback_command(command, performance_mode="aggressive"):
    """Remove aria2c routing and fall back to yt-dlp's native HTTP downloader."""
    source = list(command or [])
    fallback = []
    i = 0

    while i < len(source):
        token = str(source[i])

        if token == "--downloader" and i + 1 < len(source):
            downloader = str(source[i + 1]).strip().lower()
            if downloader in {"aria2c", "dash,m3u8:native"}:
                i += 2
                continue

        if token == "--downloader-args" and i + 1 < len(source):
            downloader_args = str(source[i + 1]).strip().lower()
            if downloader_args.startswith("aria2c:"):
                i += 2
                continue

        fallback.append(source[i])
        i += 1

    if fallback == source or not fallback:
        return None

    # Do not force HTTP chunk boundaries in the native fallback.
    # Let yt-dlp use its default HTTP request strategy instead.
    return fallback


def get_ffmpeg_command():
    exe = find_executable("ffmpeg")
    return exe or "ffmpeg"


# ============================================================
# TASKBAR PROGRESS
# ============================================================

TASKBAR_AVAILABLE = False


class WindowsTaskbarProgress:
    def __init__(self, root):
        self.hwnd = None
        self.tbl_inst = None

        if not COMTYPES_AVAILABLE:
            return

        try:
            root.update_idletasks()
            self.hwnd = wintypes.HWND(root.winfo_id())

            ctypes.oledll.ole32.CoInitialize(None)

            import comtypes.client as cc
            cc.GetModule("TaskbarLib.tlb")

            import comtypes.gen.TaskbarLib as tbl

            self.tbl_inst = cc.CreateObject(
                "{56FDF344-FD6D-11d0-958A-006097C9A090}",
                interface=tbl.ITaskbarList3,
            )
            self.tbl_inst.HrInit()

            global TASKBAR_AVAILABLE
            TASKBAR_AVAILABLE = True
        except Exception:
            TASKBAR_AVAILABLE = False

    def set_progress(self, current, total):
        if not TASKBAR_AVAILABLE or not self.hwnd or not self.tbl_inst:
            return

        try:
            if current <= 0:
                self.tbl_inst.SetProgressState(self.hwnd.value, 0)
            else:
                self.tbl_inst.SetProgressState(self.hwnd.value, 2)
                self.tbl_inst.SetProgressValue(
                    self.hwnd.value,
                    int(current),
                    max(1, int(total)),
                )
        except Exception:
            pass

    def set_state(self, state_flag):
        if not TASKBAR_AVAILABLE or not self.hwnd or not self.tbl_inst:
            return

        try:
            self.tbl_inst.SetProgressState(self.hwnd.value, state_flag)
        except Exception:
            pass


# ============================================================
# LEGACY-STYLE GRADIENT BACKGROUND
# ============================================================

class GradientFrame(ctk.CTkCanvas):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            highlightthickness=0,
            bd=0,
            **kwargs,
        )
        self.bind("<Configure>", self.schedule_draw)
        self._last_width = 0
        self._last_height = 0
        self._draw_job = None

    @staticmethod
    def hex_to_rgb(hex_str):
        hex_str = hex_str.lstrip("#")
        return tuple(int(hex_str[i:i + 2], 16) for i in (0, 2, 4))

    @staticmethod
    def rgb_to_hex(rgb):
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def schedule_draw(self, _event=None):
        width = self.winfo_width()
        height = self.winfo_height()

        if (
            width < 10
            or height < 10
            or (width == self._last_width and height == self._last_height)
        ):
            return

        self._last_width = width
        self._last_height = height

        if self._draw_job:
            try:
                self.after_cancel(self._draw_job)
            except Exception:
                pass

        self._draw_job = self.after(40, self.draw_gradient)

    def draw_gradient(self):
        width = self.winfo_width()
        height = self.winfo_height()

        self.delete("gradient")

        stops = ["#475569", "#000000", "#01436f"]
        rgb_stops = [self.hex_to_rgb(c) for c in stops]
        num_stops = len(rgb_stops)

        for i in range(height):
            p = i / max(1, height - 1)
            scaled_p = p * (num_stops - 1)
            idx = int(scaled_p)

            if idx >= num_stops - 1:
                idx = num_stops - 2
                local_p = 1.0
            else:
                local_p = scaled_p - idx

            c1 = rgb_stops[idx]
            c2 = rgb_stops[idx + 1]

            rgb = (
                int(c1[0] + (c2[0] - c1[0]) * local_p),
                int(c1[1] + (c2[1] - c1[1]) * local_p),
                int(c1[2] + (c2[2] - c1[2]) * local_p),
            )

            self.create_line(
                0,
                i,
                width,
                i,
                fill=self.rgb_to_hex(rgb),
                tags=("gradient",),
            )


# ============================================================
# SHARED TEXT / MATCH HELPERS
# ============================================================

def clean_text(text):
    text = str(text or "").casefold()
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = text.replace("&", "and")
    text = "".join(
        char if char.isalnum() or char.isspace() else " "
        for char in text
    )
    return " ".join(text.split())


def derive_title_from_filename(file_path):
    name = Path(file_path).stem
    name = re.sub(r"^\d+[\s._\-]+", "", name)
    return name.replace("_", " ").strip()


def split_artist_title(query):
    separators = [" - ", " – ", " — "]

    for sep in separators:
        if sep in query:
            artist, title = query.split(sep, 1)
            artist = artist.strip()
            title = title.strip()

            if artist and title:
                return artist, title

    return "", query.strip()


def normalize_artist_name(name):
    cleaned = clean_text(name)
    return cleaned


def exact_artist_name_match(target_artist, result_artist_names):
    """
    Artist matching is based ONLY on contributing artists.
    Album artist is never consulted.

    A target like "A, B" is considered an exact match when each
    target contributing artist appears exactly in the result artist list.
    """
    if not target_artist:
        return True

    target_parts = [
        p.strip()
        for p in re.split(r"\s*(?:,|&)\s*", str(target_artist))
        if p.strip()
    ]

    result_names = [
        str(name).strip()
        for name in (result_artist_names or [])
        if str(name).strip()
    ]

    if not target_parts or not result_names:
        return False

    target_clean = [normalize_artist_name(x) for x in target_parts]
    result_clean = [normalize_artist_name(x) for x in result_names]

    return all(item in result_clean for item in target_clean)


def title_score(wanted_title, result_title):
    w = clean_text(wanted_title)
    r = clean_text(result_title)

    if not w or not r:
        return 0

    if w == r:
        return 200

    if w in r or r in w:
        return 120

    wanted_tokens = set(w.split())
    result_tokens = set(r.split())

    if not wanted_tokens or not result_tokens:
        return 0

    overlap = len(wanted_tokens & result_tokens)
    return int((overlap / max(1, len(wanted_tokens))) * 80)


def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*]', "_", str(name or ""))
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] or "download"


def get_url_host(value):
    try:
        parsed = urllib.parse.urlparse(str(value or "").strip())
        return (parsed.netloc or "").lower().split(":")[0]
    except Exception:
        return ""


def is_youtube_music_url(value):
    """Return True only for first-party YouTube Music hosts."""
    return get_url_host(value) in {
        "music.youtube.com",
        "www.music.youtube.com",
    }


def is_youtube_music_liked_url(value):
    """Identify YouTube Music's account-bound Liked Music shelf (list=LM)."""
    if not is_youtube_music_url(value):
        return False
    try:
        parsed = urllib.parse.urlparse(str(value or "").strip())
        query = urllib.parse.parse_qs(parsed.query)
        return (query.get("list") or [""])[0] == "LM" and not (query.get("v") or [""])[0]
    except Exception:
        return False


def is_youtube_url(value):
    host = get_url_host(value)
    return host in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "www.music.youtube.com",
        "youtu.be",
    }


def is_playlist_url(value):
    """Identify an actual playlist URL, not a video opened from a playlist."""
    try:
        parsed = urllib.parse.urlparse(str(value or "").strip())
        host = (parsed.netloc or "").lower().split(":")[0]
        path = parsed.path.rstrip("/").lower()
        query = urllib.parse.parse_qs(parsed.query)

        if host not in {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "www.music.youtube.com",
        }:
            return False

        # A URL with a video id is a SINGLE VIDEO even when it also carries
        # list=... because YouTube commonly appends the playlist context to
        # watch URLs. Those must receive the single-video quality menu.
        if query.get("v"):
            return False

        # Only the canonical playlist route is treated as a playlist.
        return path == "/playlist" and bool(query.get("list"))
    except Exception:
        return False


def extract_youtube_video_id(value):
    """Return the YouTube video id for normal, short, embed, and music links."""
    try:
        parsed = urllib.parse.urlparse(str(value or "").strip())
        host = (parsed.netloc or "").lower().split(":")[0]
        path = parsed.path.strip("/")

        if host == "youtu.be":
            return path.split("/", 1)[0] or None

        query = urllib.parse.parse_qs(parsed.query)
        if query.get("v"):
            return query["v"][0] or None

        parts = path.split("/")
        if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
            return parts[1] or None
    except Exception:
        pass

    return None


def youtube_thumbnail_candidates(value):
    """Return ordered direct YouTube thumbnail candidates from largest to fallback."""
    video_id = extract_youtube_video_id(value)
    if not video_id:
        return []

    return [
        f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/sddefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/hq720.jpg",
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/default.jpg",
    ]


VIDEO_QUALITY_LABELS = {
    4320: " 8K UHD (4320p)",
    2160: " 4K UHD (2160p)",
    1440: " 2K QHD (1440p)",
    1080: " 1080P FHD",
    720: " 720P HD",
    576: " 576P",
    480: " 480P SD",
    360: " 360P",
    240: " 240P",
    144: " 144P",
}

AUDIO_DOWNLOAD_OPTIONS = [
    (" MP3 320kbps", {"kind": "audio", "audio_format": "mp3", "quality": "320K"}),
    (" MP3 256kbps", {"kind": "audio", "audio_format": "mp3", "quality": "256K"}),
    (" M4A / AAC", {"kind": "audio", "audio_format": "m4a", "quality": "0"}),
    (" FLAC Lossless", {"kind": "audio", "audio_format": "flac", "quality": "0"}),
]

def detected_video_heights(formats):
    """Return distinct usable video heights, excluding DRM and storyboard formats."""
    heights = set()

    for fmt in formats or []:
        if not isinstance(fmt, dict) or fmt.get("has_drm"):
            continue

        vcodec = str(fmt.get("vcodec") or "").strip().lower()
        if not vcodec or vcodec == "none":
            continue
        if "mhtml" in str(fmt.get("protocol") or "").lower():
            continue

        try:
            height = int(fmt.get("height") or 0)
        except (TypeError, ValueError):
            height = 0

        if height > 0:
            heights.add(height)

    return sorted(heights, reverse=True)


def build_video_quality_options(formats):
    """Return unique video-resolution choices actually exposed by yt-dlp."""
    ordered = detected_video_heights(formats)
    if not ordered:
        return []

    highest = ordered[0]
    options = [(
        f" Best Quality — {highest}p",
        {"kind": "video", "height": highest, "best": True},
    )]

    for height in ordered[1:]:
        options.append((
            VIDEO_QUALITY_LABELS.get(height, f" {height}P"),
            {"kind": "video", "height": height, "best": False},
        ))

    return options


def build_playlist_quality_options(video_formats_by_video=None):
    """Build playlist choices only from resolutions found on its individual videos.

    Resolution counts show how many inspected playlist videos expose that exact
    height. Selecting a height downloads each item at its best available height
    at or below that ceiling. Best Quality Separate chooses each item's maximum.
    """
    video_formats_by_video = list(video_formats_by_video or [])
    height_counts = {}
    for formats in video_formats_by_video:
        for height in set(detected_video_heights(formats)):
            height_counts[height] = height_counts.get(height, 0) + 1

    options = [(
        "Best Quality Separate",
        {"kind": "video", "best_per_item": True},
    )]

    for height in sorted(height_counts, reverse=True):
        count = height_counts[height]
        label = VIDEO_QUALITY_LABELS.get(height, f" {height}P")
        if video_formats_by_video:
            label = f"{label} · {count}/{len(video_formats_by_video)} videos"
        options.append((
            label,
            {"kind": "video", "height": height, "best": False},
        ))

    options.extend(AUDIO_DOWNLOAD_OPTIONS.copy())
    return options


def combine_quality_options(formats):
    """Build inspected video choices plus the persistent audio choices."""
    return build_video_quality_options(formats) + AUDIO_DOWNLOAD_OPTIONS.copy()


def select_best_video_quality_spec(quality_options, maximum_height=None):
    """Pick the highest inspected video spec, optionally under a height ceiling."""
    candidates = []
    for _label, spec in quality_options or []:
        if not isinstance(spec, dict) or spec.get("kind") != "video":
            continue
        try:
            height = int(spec.get("height") or 0)
        except (TypeError, ValueError):
            continue
        if height <= 0:
            continue
        if maximum_height is not None and height > int(maximum_height):
            continue
        candidates.append((height, spec))

    if not candidates:
        return None
    return dict(max(candidates, key=lambda item: item[0])[1])


LIKED_MUSIC_EXTRACTOR_ARG = "youtube:player_client=web_embedded,web_safari"


def youtube_format_extractor_arg_sets():
    """Use the normal default client set for regular YouTube URLs."""
    return ["youtube:player_client=default,web_embedded"]


def youtube_extractor_args_list(strategy):
    # Use the supported fallback consistently for metadata inspection and
    # final media transfers, including audio-only and playlist items.
    strategy = strategy or "youtube:player_client=default,web_embedded"
    return ["--extractor-args", strategy]


def max_video_height(formats):
    heights = detected_video_heights(formats)
    return heights[0] if heights else 0


# Human-readable language labels for YouTube alternate-audio tracks.
# yt-dlp exposes a machine-readable ``language`` field when the extractor
# provides it, while some YouTube responses also describe the language in
# ``format_note`` (for example, "English original (default), medium").
AUDIO_LANGUAGE_NAMES = {
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
}


def _format_is_audio_only(fmt):
    if not isinstance(fmt, dict):
        return False
    acodec = str(fmt.get("acodec") or "").strip().lower()
    vcodec = str(fmt.get("vcodec") or "").strip().lower()
    if not acodec or acodec == "none":
        return False
    return not vcodec or vcodec == "none"


def _audio_track_is_default(fmt):
    text = " ".join(
        str(fmt.get(key) or "")
        for key in ("format_note", "format", "format_id")
    ).lower()
    return bool(re.search(r"(?:\(\s*default\s*\)|\bdefault\b)", text))


def _audio_track_is_original(fmt):
    text = " ".join(
        str(fmt.get(key) or "")
        for key in ("format_note", "format", "format_id")
    ).lower()
    return bool(re.search(r"(?:\(\s*original\s*\)|\boriginal\b)", text))


def _audio_language_name(fmt):
    code = str(fmt.get("language") or "").strip().lower()
    code_base = code.split("-")[0].split("_")[0]
    if code_base in AUDIO_LANGUAGE_NAMES:
        return AUDIO_LANGUAGE_NAMES[code_base]

    note = str(fmt.get("format_note") or "").strip()
    prefix = note.split(",", 1)[0].strip()
    prefix = re.sub(r"\([^)]*\)", "", prefix).strip()
    prefix = re.sub(r"\b(?:audio|track|original|default)\b", " ", prefix, flags=re.I)
    prefix = re.sub(r"\s+", " ", prefix).strip(" -:")

    if prefix and len(prefix) <= 60:
        return prefix.title()

    if code:
        return code.upper()

    return "Unknown"


def _audio_track_variant(fmt):
    if _audio_track_is_default(fmt):
        return "default"
    if _audio_track_is_original(fmt):
        return "original"

    note = str(fmt.get("format_note") or "").strip().lower()
    prefix = note.split(",", 1)[0].strip()
    prefix = re.sub(r"\([^)]*\)", "", prefix)
    prefix = re.sub(r"\b(?:medium|low|high|audio|track)\b", " ", prefix)
    prefix = re.sub(r"[^a-z0-9]+", " ", prefix).strip()
    return prefix or "standard"


def _audio_track_sort_key(fmt):
    def number(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def integer(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    codec = str(fmt.get("acodec") or "").lower()
    codec_rank = {
        "opus": 6,
        "vorbis": 5,
        "flac": 10,
        "alac": 10,
        "aac": 4,
        "mp4a": 4,
        "m4a": 4,
        "ac3": 3,
        "eac3": 3,
        "mp3": 2,
    }.get(codec, 1)

    # DRC (dynamic-range-compressed) streams can appear alongside the
    # normal stream with otherwise equivalent metadata. Prefer the normal one.
    format_id = str(fmt.get("format_id") or "").lower()
    format_note = str(fmt.get("format_note") or "").lower()
    is_drc = format_id.endswith("-drc") or any(
        part.strip() == "drc" for part in format_note.split(",")
    )

    return (
        0 if is_drc else 1,
        number(fmt.get("abr")),
        integer(fmt.get("asr")),
        number(fmt.get("quality")),
        number(fmt.get("tbr")),
        integer(fmt.get("filesize") or fmt.get("filesize_approx")),
        codec_rank,
    )


def build_audio_track_options(formats):
    """Return one best audio format per distinct YouTube language/variant track."""
    grouped = {}

    for fmt in formats or []:
        if not _format_is_audio_only(fmt):
            continue
        if fmt.get("has_drm"):
            continue

        format_id = str(fmt.get("format_id") or "").strip()
        if not format_id:
            continue

        language_code = str(fmt.get("language") or "").strip().lower()
        language_name = _audio_language_name(fmt)
        variant = _audio_track_variant(fmt)
        key = (language_code or language_name.lower(), variant)

        current = grouped.get(key)
        if current is None or _audio_track_sort_key(fmt) > _audio_track_sort_key(current):
            grouped[key] = fmt

    tracks = []
    used_labels = set()

    for fmt in grouped.values():
        language_code = str(fmt.get("language") or "").strip().lower() or "und"
        language_name = _audio_language_name(fmt)
        is_default = _audio_track_is_default(fmt)
        is_original = _audio_track_is_original(fmt)

        label_parts = [language_name]
        if is_default:
            label_parts.append("Default")
        elif is_original:
            label_parts.append("Original")

        label = " ".join(label_parts).strip()
        base_label = label
        counter = 2
        while label.lower() in used_labels:
            label = f"{base_label} {counter}"
            counter += 1
        used_labels.add(label.lower())

        tracks.append({
            "format_id": str(fmt.get("format_id") or ""),
            "language_code": language_code,
            "language": language_name,
            "label": label,
            "is_default": is_default,
            "is_original": is_original,
            "abr": fmt.get("abr"),
            "asr": fmt.get("asr"),
            "acodec": fmt.get("acodec"),
        })

    tracks.sort(
        key=lambda track: (
            0 if track.get("is_default") else 1,
            0 if track.get("is_original") else 1,
            str(track.get("language") or "").lower(),
        )
    )

    return tracks

_INSPECT_CACHE = {}
_INSPECT_CACHE_TTL = 600  # seconds

# Cookie-file authentication (no browser scanning or browser cookie extraction)
COOKIE_FILE_ENV = "YTM_MUSIC_TOOLKIT_COOKIES"
COOKIE_FILE_NAME = "cookies.txt"


class BrowserSessionError(RuntimeError):
    """The required Netscape-format cookies.txt file is missing or unavailable."""


_BROWSER_SESSION_LISTENER = None


def set_browser_session_listener(callback):
    """Register a callback used by the existing status label."""
    global _BROWSER_SESSION_LISTENER
    _BROWSER_SESSION_LISTENER = callback


def _notify_browser_session(label, reason=""):
    callback = _BROWSER_SESSION_LISTENER
    if callback:
        try:
            callback(label, reason)
        except Exception:
            pass


def _saved_cookie_file_path():
    """Read the user-selected cookie path from the existing app config."""
    try:
        config_path = Path(CONFIG_FILE)
        if config_path.is_file():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return str(data.get("cookie_file_path") or "").strip()
    except Exception:
        pass
    return ""


def _cookie_file_candidates():
    """Return explicit file locations; never inspect browser profiles."""
    candidates = []

    # The file selected in the GUI always takes priority.
    selected = _saved_cookie_file_path()
    if selected:
        candidates.append(Path(os.path.expandvars(os.path.expanduser(selected))))

    override = os.environ.get(COOKIE_FILE_ENV, "").strip().strip('"')
    if override:
        candidates.append(Path(os.path.expandvars(os.path.expanduser(override))))

    if getattr(sys, "frozen", False):
        app_dir = Path(sys.executable).resolve().parent
    else:
        app_dir = Path(__file__).resolve().parent

    candidates.extend([
        app_dir / COOKIE_FILE_NAME,
        Path.home() / "Documents" / "YTDLP" / COOKIE_FILE_NAME,
        Path.home() / COOKIE_FILE_NAME,
    ])

    result = []
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            key = os.path.normcase(str(resolved))
            if key not in seen:
                seen.add(key)
                result.append(resolved)
        except Exception:
            continue
    return result


def _is_valid_cookie_file(candidate):
    """Check the Netscape cookie-file signature without logging cookie values."""
    try:
        candidate = Path(candidate)
        if not candidate.is_file() or not os.access(str(candidate), os.R_OK):
            return False
        with candidate.open("r", encoding="utf-8-sig", errors="replace") as handle:
            first_line = handle.readline().strip()
        return first_line in ("# HTTP Cookie File", "# Netscape HTTP Cookie File")
    except (OSError, UnicodeError):
        return False


def _save_selected_cookie_file(path):
    """Persist the chosen path without discarding other toolkit settings."""
    config_path = Path(CONFIG_FILE)
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Toolkit configuration is not a JSON object.")
    else:
        data = {}
    data["cookie_file_path"] = str(Path(path).resolve())
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = config_path.with_name(config_path.name + ".tmp")
    temp_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(str(temp_path), str(config_path))


def get_cookie_file_path():
    """Return the first readable Netscape-format cookies.txt file."""
    for candidate in _cookie_file_candidates():
        if _is_valid_cookie_file(candidate):
            try:
                return str(candidate.resolve())
            except Exception:
                return str(candidate)
    return ""


def _create_temporary_ytmusic_auth_from_cookie_file(cookie_path):
    """Convert the selected Netscape cookie jar to short-lived ytmusicapi browser auth.

    This keeps Liked Music setup automatic: no manually copied request headers
    or persistent second credentials file are required.
    """
    cookie_path = Path(cookie_path)
    jar = http.cookiejar.MozillaCookieJar(str(cookie_path))
    try:
        jar.load(ignore_discard=True, ignore_expires=False)
    except Exception as exc:
        raise RuntimeError(
            f"Could not read the selected cookies.txt file: {type(exc).__name__}: {exc}"
        ) from exc

    # Build the Cookie header for the actual InnerTube API request path,
    # not the public /browse webpage. Netscape cookies can be path-scoped; using
    # the wrong path can silently omit cookies that the API endpoint should get.
    request = urllib.request.Request(
        "https://music.youtube.com/youtubei/v1/browse",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    jar.add_cookie_header(request)
    cookie_header = request.get_header("Cookie") or ""
    if not cookie_header:
        raise RuntimeError(
            "The selected cookies.txt file contains no active cookies for music.youtube.com. "
            "Choose a fresh Netscape-format export from your signed-in YouTube session."
        )

    if not re.search(r"(?:^|;\s*)__Secure-3PAPISID=", cookie_header, re.IGNORECASE):
        raise RuntimeError(
            "The selected cookies.txt file does not include an active __Secure-3PAPISID "
            "cookie for YouTube Music. Export a fresh cookies.txt from your signed-in "
            "YouTube session, making sure cookies for .youtube.com are included."
        )

    parsed_cookies = http.cookies.SimpleCookie()
    try:
        parsed_cookies.load(cookie_header.replace('"', ""))
        sapisid = parsed_cookies["__Secure-3PAPISID"].value
    except Exception as exc:
        raise RuntimeError(
            "Could not read the __Secure-3PAPISID value from cookies.txt. "
            "Export a fresh cookies.txt from your signed-in YouTube session."
        ) from exc

    timestamp = str(int(time.time()))
    digest = hashlib.sha1(
        f"{timestamp} {sapisid} https://music.youtube.com".encode("utf-8")
    ).hexdigest()
    authorization = f"SAPISIDHASH {timestamp}_{digest}"

    # Match ytmusicapi's initialize_headers() defaults. When a JSON auth file
    # is passed directly, YTMusic uses its headers as-is instead of merging these.
    auth_headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "Authorization": authorization,
        "Content-Encoding": "gzip",
        "Content-Type": "application/json",
        "Origin": "https://music.youtube.com",
        "X-Goog-AuthUser": "0",
        "x-origin": "https://music.youtube.com",
        "Cookie": cookie_header,
        "User-Agent": YTMUSICAPI_USER_AGENT,
    }

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=".ytmusic-auth-",
            suffix=".json",
            dir=str(ensure_failure_log_dir()),
            delete=False,
        ) as handle:
            json.dump(auth_headers, handle, ensure_ascii=False)
            temp_path = Path(handle.name)
        return temp_path
    except Exception:
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
        raise


def _no_session_message():
    return (
        "Cookie file not found. Put a Netscape-format cookies.txt next to "
        "YTM Music Toolkit or at Documents\\YTDLP\\cookies.txt. "
        "You can also set the YTM_MUSIC_TOOLKIT_COOKIES environment variable "
        "to the full file path. The app no longer reads cookies from browsers."
    )


def ytdlp_retry_on_cookie_failure(url, attempt):
    """Run once using the configured cookies file; never switch browsers."""
    cookie_args = get_browser_cookie_args(url)
    return attempt(cookie_args)


def get_browser_cookie_args(url="", force=False, exclude_sources=None):
    """Compatibility wrapper returning yt-dlp's file-based --cookies argument."""
    cookie_path = get_cookie_file_path()
    if not cookie_path:
        _notify_browser_session(None, _no_session_message())
        raise BrowserSessionError(_no_session_message())

    _notify_browser_session(COOKIE_FILE_NAME, cookie_path)
    return ["--cookies", cookie_path]


def _run_ytdlp_info(url, strategy, timeout):
    return ytdlp_retry_on_cookie_failure(
        url,
        lambda cookie_args: _run_ytdlp_info_once(url, strategy, cookie_args, timeout),
    )


def _run_ytdlp_info_once(url, strategy, cookie_args, timeout):
    command = [
        get_ytdlp_command(),
        *get_ytdlp_runtime_args(),
        "--dump-single-json",
        "--skip-download",
        "--no-playlist",
        "--no-warnings",
        "--socket-timeout", "10",
        *youtube_extractor_args_list(strategy),
        *cookie_args,
        "--",
        url,
    ]
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        **get_hidden_subprocess_kwargs(),
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"yt-dlp exited with code {proc.returncode}: {proc.stderr.strip()}"
        )
    raw = proc.stdout.strip()
    if not raw:
        raise RuntimeError("yt-dlp returned no metadata")
    return json.loads(raw)


def inspect_youtube_info(url, timeout=30, preferred_strategy=None):
    """Inspect metadata and formats with the normal or item-specific client set."""
    cache_key = (url, preferred_strategy or "")
    cached = _INSPECT_CACHE.get(cache_key)
    if cached and (time.time() - cached[0]) < _INSPECT_CACHE_TTL:
        return cached[1]

    strategies = (
        [preferred_strategy]
        if preferred_strategy
        else youtube_format_extractor_arg_sets()
    )
    primary_data = None
    primary_error = None

    try:
        primary_data = _run_ytdlp_info(url, strategies[0], timeout)
    except Exception as exc:
        if isinstance(exc, (BrowserSessionError, FileNotFoundError)):
            raise
        primary_error = exc

    primary_formats = (primary_data or {}).get("formats") or []
    best = (primary_data, primary_formats, strategies[0]) if primary_data else None
    best_height = max_video_height(primary_formats) if primary_data else 0

    # A strong default result is enough. If it errors or exposes only low
    # resolution, try the alternate clients concurrently rather than giving up.
    if best is not None and best_height > 360:
        _INSPECT_CACHE[cache_key] = (time.time(), best)
        return best

    fallback_strategies = strategies[1:]
    outcomes = {}
    errors = {}

    def worker(strategy):
        return _run_ytdlp_info(url, strategy, timeout)

    if fallback_strategies:
        with ThreadPoolExecutor(max_workers=len(fallback_strategies)) as pool:
            futures = {
                pool.submit(worker, strategy): strategy
                for strategy in fallback_strategies
            }
            for future in as_completed(futures):
                strategy = futures[future]
                try:
                    outcomes[strategy] = future.result()
                except Exception as exc:
                    errors[strategy or "default"] = str(exc)

    if best is None:
        successful = []
        for strategy in fallback_strategies:
            info = outcomes.get(strategy)
            if info:
                fmts = info.get("formats") or []
                successful.append((info, fmts, strategy))
        if successful:
            best = max(
                successful,
                key=lambda item: max_video_height(item[1]),
            )
            best_height = max_video_height(best[1])
        else:
            failures = []
            if primary_error:
                failures.append(f"default client: {primary_error}")
            failures.extend(
                f"{strategy or 'default'}: {error}"
                for strategy, error in errors.items()
            )
            details = "; ".join(failures) or "No extractor strategy returned metadata"
            raise RuntimeError(
                "YouTube preview/format inspection failed for every client. " + details
            ) from primary_error
    else:
        for strategy in fallback_strategies:
            info = outcomes.get(strategy)
            if not info:
                continue
            fmts = info.get("formats") or []
            height = max_video_height(fmts)
            if height > best_height:
                # Keep the default title/artwork but use the successful client's
                # formats and the matching client strategy for later downloads.
                best = (primary_data, fmts, strategy)
                best_height = height

    _INSPECT_CACHE[cache_key] = (time.time(), best)
    return best


def fetch_youtube_data(url, timeout=30):
    """Metadata-only fetch that shares the preview's cookie handling and cache.

    Reuses an already-inspected result when the preview step ran first, and
    otherwise does ONE extraction through the same cookie-retry / anonymous
    fallback path the quality inspection uses.
    """
    cached = _INSPECT_CACHE.get((url, ""))
    if cached and (time.time() - cached[0]) < _INSPECT_CACHE_TTL:
        return cached[1][0]
    return _run_ytdlp_info(url, None, timeout)


def inspect_youtube_formats(url, timeout=30, preferred_strategy=None):
    """Return formats and the exact extractor strategy used for inspection."""
    _data, formats, strategy = inspect_youtube_info(
        url,
        timeout,
        preferred_strategy=preferred_strategy,
    )
    return formats, strategy


# ============================================================
# IMAGE HELPERS
# ============================================================

def canonicalize_thumbnail_url(url):
    if not url:
        return None

    url = re.sub(r"=w\d+(?:-h\d+[^&]*)?$", "=s0", url)
    url = re.sub(r"=w\d+-h\d+.*$", "=s0", url)
    url = re.sub(r"=s\d+.*$", "=s0", url)

    return url


def inspect_image_from_url(url):
    if not url:
        return None, 0, 0

    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        image_data = response.content
        image = Image.open(BytesIO(image_data))
        width, height = image.size

        return image_data, width, width * height
    except Exception:
        return None, 0, 0


def normalize_cover_to_jpeg(image_bytes):
    try:
        image = Image.open(BytesIO(image_bytes))
        image = ImageOps.exif_transpose(image)

        if image.mode != "RGB":
            image = image.convert("RGB")

        buffer = BytesIO()
        image.save(
            buffer,
            format="JPEG",
            quality=100,
            subsampling=0,
        )
        return buffer.getvalue()
    except Exception:
        return None


def make_picture(image_bytes):
    picture = Picture()
    picture.type = 3
    picture.mime = "image/jpeg"
    picture.desc = "Front Cover"
    picture.data = image_bytes
    return picture


# ============================================================
# YOUTUBE / YOUTUBE MUSIC RESOLVER
# ============================================================

class YTMResolver:
    def __init__(self):
        self.yt = YTMusic()
        self.year_cache = {}

    def _artist_names_from_item(self, item):
        names = []

        for artist in item.get("artists", []) or []:
            if isinstance(artist, dict):
                name = artist.get("name", "")
            else:
                name = str(artist)

            if name:
                names.append(name)

        # Some yt-dlp-like structures may surface "artist" instead.
        if not names:
            fallback = item.get("artist") or item.get("author")
            if fallback:
                names = [str(fallback)]

        return names

    def _album_name_from_item(self, item):
        album = item.get("album")

        if isinstance(album, dict):
            return album.get("name", "") or ""

        return str(album or "")

    def _thumbnail_url_from_item(self, item):
        thumbnails = item.get("thumbnails", []) or []

        ranked = sorted(
            thumbnails,
            key=lambda x: (
                int(x.get("width", 0) or 0)
                * int(x.get("height", 0) or 0)
            ),
            reverse=True,
        )

        for thumbnail in ranked:
            url = thumbnail.get("url")
            if url:
                return canonicalize_thumbnail_url(url)

        return None

    def _result_score(self, wanted_artist, wanted_album, wanted_title, item):
        artists = self._artist_names_from_item(item)
        album = self._album_name_from_item(item)
        title = item.get("title", "")

        score = title_score(wanted_title, title)

        if wanted_artist and exact_artist_name_match(wanted_artist, artists):
            score += 500

        if wanted_album:
            w = clean_text(wanted_album)
            r = clean_text(album)

            if w and r:
                if w == r:
                    score += 100
                elif w in r or r in w:
                    score += 45

        return score

    def _build_result(self, item, source, fallback=False):
        artists = self._artist_names_from_item(item)
        album = self._album_name_from_item(item)

        thumbnail_candidates = []
        thumbnails = item.get("thumbnails", []) or []
        ranked = sorted(
            [t for t in thumbnails if isinstance(t, dict)],
            key=lambda x: (
                int(x.get("width", 0) or 0)
                * int(x.get("height", 0) or 0)
            ),
            reverse=True,
        )
        for thumbnail in ranked:
            candidate = canonicalize_thumbnail_url(thumbnail.get("url") or "")
            if candidate and candidate not in thumbnail_candidates:
                thumbnail_candidates.append(candidate)

        cover_url = self._thumbnail_url_from_item(item)
        if cover_url and cover_url not in thumbnail_candidates:
            thumbnail_candidates.insert(0, cover_url)

        return {
            "video_id": item.get("videoId", ""),
            "title": item.get("title", ""),
            "artist_names": artists,
            "artist": ", ".join(artists),
            "album": album,
            "album_id": (
                item.get("album", {}).get("id")
                if isinstance(item.get("album"), dict)
                else None
            ),
            "year": "",
            "cover_url": cover_url,
            "thumbnail_candidates": thumbnail_candidates,
            "source": source,
            "is_fallback": fallback,
        }

    def _get_year(self, result):
        album_id = result.get("album_id")

        if not album_id:
            return ""

        if album_id in self.year_cache:
            return self.year_cache[album_id]

        year = ""

        try:
            details = self.yt.get_album(album_id)
            year = str(details.get("year", "") or "")
        except Exception:
            year = ""

        self.year_cache[album_id] = year
        return year

    def search(self, artist, title, album=""):
        artist = str(artist or "").strip()
        title = str(title or "").strip()
        album = str(album or "").strip()

        query = f"{artist} {title}".strip() if artist else title

        if not query:
            return None

        # ----------------------------------------------------
        # STEP 1: YT MUSIC SONGS FILTER
        # ----------------------------------------------------
        try:
            songs = self.yt.search(
                query,
                filter="songs",
                limit=15,
                ignore_spelling=False,
            )
        except Exception as exc:
            songs = []
            print(f"[YTM songs] {exc}")
            write_failure_log("ytm_songs_search", exc, details=f"Query: {query}")

        exact_artist_candidates = []

        for item in songs:
            artists = self._artist_names_from_item(item)

            if not artist or exact_artist_name_match(artist, artists):
                exact_artist_candidates.append(item)

        if exact_artist_candidates:
            best = max(
                exact_artist_candidates,
                key=lambda item: self._result_score(
                    artist,
                    album,
                    title,
                    item,
                ),
            )

            result = self._build_result(
                best,
                source="YouTube Music Songs",
                fallback=False,
            )
            result["year"] = self._get_year(result)
            return result

        # No exact artist in songs -> explicit videos fallback.
        # This is intentionally NOT a generic unrestricted search.
        # It uses the YT Music videos category.
        try:
            videos = self.yt.search(
                query,
                filter="videos",
                limit=15,
                ignore_spelling=False,
            )
        except Exception as exc:
            videos = []
            print(f"[YTM videos] {exc}")
            write_failure_log("ytm_videos_search", exc, details=f"Query: {query}")

        if not videos:
            return None

        exact_video_candidates = []

        for item in videos:
            artists = self._artist_names_from_item(item)

            if not artist or exact_artist_name_match(artist, artists):
                exact_video_candidates.append(item)

        pool = exact_video_candidates or videos

        best = max(
            pool,
            key=lambda item: self._result_score(
                artist,
                album,
                title,
                item,
            ),
        )

        result = self._build_result(
            best,
            source="YouTube Music Videos (Fallback)",
            fallback=True,
        )
        result["year"] = self._get_year(result)
        return result

    @staticmethod
    def preview_from_url(url):
        """Silently inspect preview art/title plus source-specific video qualities."""
        url = str(url or "").strip()

        def run_json(command, timeout=30):
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                **get_hidden_subprocess_kwargs(),
            )

            if proc.returncode != 0:
                raise RuntimeError(
                    f"yt-dlp exited with code {proc.returncode}: {proc.stderr.strip()}"
                )

            raw = proc.stdout.strip()
            if not raw:
                raise RuntimeError("yt-dlp returned no preview metadata")

            return json.loads(raw)

        try:
            # Liked Music is an account-bound shelf, not a normal yt-dlp playlist.
            # Do not send list=LM to yt-dlp or run a costly 300-track quality scan
            # during preview. The downloader resolves the actual track list later.
            if is_youtube_music_liked_url(url):
                return {
                    "title": "YouTube Music Liked Music",
                    "cover_url": "",
                    "thumbnail_candidates": [],
                    "quality_options": build_playlist_quality_options([]),
                    "quality_summary": "Liked Music · tracks are resolved when download starts",
                    "quality_inventory": [],
                    "is_playlist": True,
                    "playlist_url": url,
                    "first_video_url": "",
                }

            # Playlist preview: fetch the playlist title and item IDs only. Actual
            # format inspection is delayed until each item is about to download.
            if is_playlist_url(url):
                def _playlist_attempt(cookie_args):
                    return run_json([
                        get_ytdlp_command(),
                        *get_ytdlp_runtime_args(),
                        "--dump-single-json",
                        "--flat-playlist",
                        "--skip-download",
                        "--no-warnings",
                        "--ignore-errors",
                        *cookie_args,
                        "--",
                        url,
                    ], timeout=180)

                data = ytdlp_retry_on_cookie_failure(url, _playlist_attempt)

                title = str(data.get("title") or "YouTube Playlist").strip()
                thumbnail = str(data.get("thumbnail") or "").strip()
                thumbnail_candidates = []
                if thumbnail:
                    thumbnail_candidates.append(canonicalize_thumbnail_url(thumbnail))

                for thumb in data.get("thumbnails", []) or []:
                    if isinstance(thumb, dict):
                        candidate = canonicalize_thumbnail_url(thumb.get("url") or "")
                        if candidate and candidate not in thumbnail_candidates:
                            thumbnail_candidates.append(candidate)

                entries = data.get("entries") or []
                video_entries = []
                seen_video_ids = set()
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    video_id = str(entry.get("id") or entry.get("videoId") or "").strip()
                    entry_url = str(entry.get("webpage_url") or entry.get("url") or "").strip()
                    if not video_id:
                        video_id = extract_youtube_video_id(entry_url) or ""
                    if not video_id or video_id in seen_video_ids:
                        continue
                    seen_video_ids.add(video_id)
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    video_entries.append({
                        "video_id": video_id,
                        "title": str(entry.get("title") or video_id).strip(),
                        "url": video_url,
                        "thumbnail": str(entry.get("thumbnail") or "").strip(),
                    })

                if video_entries:
                    first_entry_thumb = video_entries[0].get("thumbnail") or ""
                    if first_entry_thumb:
                        candidate = canonicalize_thumbnail_url(first_entry_thumb)
                        if candidate and candidate not in thumbnail_candidates:
                            thumbnail_candidates.append(candidate)
                    for candidate in youtube_thumbnail_candidates(video_entries[0]["url"]):
                        if candidate not in thumbnail_candidates:
                            thumbnail_candidates.append(candidate)

                # Keep preview metadata lightweight. Inspecting formats for every
                # playlist item here made large playlists sit in "Preparing" for ages.
                # The actual download worker inspects each item only when it is about
                # to be downloaded, so the selected quality ceiling is still enforced.
                quality_summary = (
                    f"Playlist ready: {len(video_entries)} videos · "
                    "qualities checked as each download starts"
                )

                return {
                    "title": title,
                    "cover_url": thumbnail_candidates[0] if thumbnail_candidates else "",
                    "thumbnail_candidates": thumbnail_candidates,
                    "quality_options": build_playlist_quality_options([]),
                    "quality_summary": quality_summary,
                    "quality_inventory": [],
                    "is_playlist": True,
                    "playlist_url": url,
                    "first_video_url": video_entries[0]["url"] if video_entries else "",
                }

            # ONE extraction gives title, thumbnail and formats.
            data, formats, extractor_arg = inspect_youtube_info(
                url,
                timeout=30,
            )

            title = str(data.get("title") or "Unknown YouTube Video").strip()
            thumbnail = str(data.get("thumbnail") or "").strip()
            candidates = []
            if thumbnail:
                candidates.append(canonicalize_thumbnail_url(thumbnail))
            for candidate in youtube_thumbnail_candidates(url):
                if candidate not in candidates:
                    candidates.append(candidate)

            return {
                "title": title,
                "cover_url": candidates[0] if candidates else "",
                "thumbnail_candidates": candidates,
                "quality_options": combine_quality_options(formats),
                "youtube_extractor_arg": extractor_arg,
                "is_playlist": False,
            }
        except Exception as exc:
            write_failure_log(
                "silent_preview",
                exc,
                details=f"URL: {url}",
            )
            return None



    def metadata_from_url(self, url):
        try:
            data = fetch_youtube_data(url, timeout=30)
            if not data:
                write_failure_log(
                    "youtube_metadata_empty",
                    RuntimeError("yt-dlp returned no metadata"),
                    details=f"URL: {url}",
                )
                return None

            artist = (
                data.get("artist")
                or data.get("creator")
                or data.get("uploader")
                or data.get("channel")
                or ""
            )
            title = data.get("track") or data.get("title") or ""
            album = data.get("album") or ""

            upload_date = str(data.get("upload_date") or "")
            year = upload_date[:4] if len(upload_date) >= 4 else ""

            video_id = str(data.get("id") or "").strip()
            if not video_id:
                parsed = urllib.parse.urlparse(url)
                query = urllib.parse.parse_qs(parsed.query)
                video_id = (query.get("v") or [""])[0].strip()

            thumbnail = data.get("thumbnail") or ""
            thumbnail_candidates = []

            direct_thumbnail = canonicalize_thumbnail_url(thumbnail)
            if direct_thumbnail:
                thumbnail_candidates.append(direct_thumbnail)

            for thumb in data.get("thumbnails", []) or []:
                if isinstance(thumb, dict):
                    candidate = canonicalize_thumbnail_url(thumb.get("url") or "")
                    if candidate and candidate not in thumbnail_candidates:
                        thumbnail_candidates.append(candidate)

            for candidate in youtube_thumbnail_candidates(url):
                if candidate not in thumbnail_candidates:
                    thumbnail_candidates.append(candidate)

            return {
                "artist": artist,
                "title": title,
                "album": album,
                "year": year,
                "video_id": video_id,
                "thumbnail": direct_thumbnail,
                "thumbnail_candidates": thumbnail_candidates,
                "source_title": data.get("title") or "",
                "source_url": url,
            }
        except BrowserSessionError:
            raise
        except Exception as exc:
            write_failure_log(
                "youtube_metadata", 
                exc,
                details=f"URL: {url}",
            )
            return None


    def direct_result_from_metadata(self, meta):
        """Build a download result directly from YouTube metadata without YTM search."""
        if not meta or not meta.get("video_id"):
            return None

        artist = str(meta.get("artist") or "").strip()
        title = str(meta.get("title") or meta.get("source_title") or "").strip()

        if not title:
            return None

        artist_names = [artist] if artist else ["YouTube"]

        return {
            "video_id": meta.get("video_id", ""),
            "title": title,
            "artist_names": artist_names,
            "artist": artist or "YouTube",
            "album": str(meta.get("album") or ""),
            "album_id": None,
            "year": str(meta.get("year") or ""),
            "cover_url": meta.get("thumbnail"),
            "thumbnail_candidates": meta.get("thumbnail_candidates") or [],
            "source_thumbnail_url": meta.get("thumbnail"),
            "source": "YouTube Direct (YTM matching skipped)",
            "source_url": meta.get("source_url", ""),
            "is_fallback": False,
            "ytm_matched": False,
            "input_type": "url",
            "requested_artist": artist,
            "requested_title": title,
        }

    def metadata_from_playlist_entry(self, entry, source_url):
        """Build usable per-track metadata from yt-dlp's flat playlist entry.

        A playlist listing already contains the video ID and title. Reuse that
        information instead of running a second metadata extraction for every
        track, which can fail independently and cause the worker to skip items.
        """
        if not isinstance(entry, dict):
            return None

        video_id = str(entry.get("video_id") or entry.get("id") or entry.get("videoId") or "").strip()
        title = str(entry.get("track") or entry.get("title") or entry.get("fulltitle") or "").strip()
        if not video_id or not title:
            return None

        artist_value = entry.get("artist") or entry.get("creator") or entry.get("uploader") or entry.get("channel") or ""
        if isinstance(artist_value, (list, tuple)):
            artist = ", ".join(str(value).strip() for value in artist_value if str(value).strip())
        else:
            artist = str(artist_value or "").strip()

        if not artist:
            artists_value = entry.get("artists") or []
            if isinstance(artists_value, list):
                artist_names = [
                    str(item.get("name") if isinstance(item, dict) else item).strip()
                    for item in artists_value
                    if str(item.get("name") if isinstance(item, dict) else item).strip()
                ]
                artist = ", ".join(artist_names)

        album_value = entry.get("album") or ""
        if isinstance(album_value, dict):
            album = str(album_value.get("name") or "").strip()
        else:
            album = str(album_value or "").strip()

        upload_date = str(entry.get("upload_date") or "")
        year = upload_date[:4] if len(upload_date) >= 4 else str(entry.get("release_year") or "")

        thumbs = entry.get("thumbnails") or []
        ranked_thumbnails = sorted(
            [item for item in thumbs if isinstance(item, dict) and item.get("url")],
            key=lambda item: (
                int(item.get("width") or 0) * int(item.get("height") or 0)
            ),
            reverse=True,
        )
        thumbnail = str(entry.get("thumbnail") or "")
        if not thumbnail and ranked_thumbnails:
            thumbnail = str(ranked_thumbnails[0].get("url") or "")

        thumbnail_candidates = []
        direct_thumbnail = canonicalize_thumbnail_url(thumbnail)
        if direct_thumbnail:
            thumbnail_candidates.append(direct_thumbnail)
        for item in ranked_thumbnails:
            candidate = canonicalize_thumbnail_url(item.get("url") or "")
            if candidate and candidate not in thumbnail_candidates:
                thumbnail_candidates.append(candidate)
        for candidate in youtube_thumbnail_candidates(source_url):
            if candidate and candidate not in thumbnail_candidates:
                thumbnail_candidates.append(candidate)

        return {
            "artist": artist,
            "title": title,
            "album": album,
            "year": year,
            "video_id": video_id,
            "thumbnail": direct_thumbnail,
            "thumbnail_candidates": thumbnail_candidates,
            "source_thumbnail_url": direct_thumbnail,
            "source_title": title,
            "source_url": source_url,
        }

    def resolve_input(self, user_input):
        user_input = str(user_input or "").strip()

        if not user_input:
            return None, "Empty input"

        if is_youtube_url(user_input):
            meta = self.metadata_from_url(
                user_input,
            )

            if not meta:
                return None, "Could not read YouTube metadata from the link"

            # A supplied YouTube Music URL already identifies the exact video.
            # Search YT Music only to enrich metadata; never fail the download or
            # silently switch to a different video ID if search returns nothing
            # or selects a different version (cover, live, remaster, etc.).
            if is_youtube_music_url(user_input):
                direct_result = self.direct_result_from_metadata(meta)
                if not direct_result:
                    return None, "Could not build a direct result from the YouTube Music URL"

                source_video_id = str(direct_result.get("video_id") or "").strip()
                result = None
                try:
                    candidate = self.search(
                        meta["artist"],
                        meta["title"],
                        meta["album"],
                    )
                    candidate_video_id = str((candidate or {}).get("video_id") or "").strip()
                    if source_video_id and candidate_video_id == source_video_id:
                        result = candidate
                except Exception as exc:
                    write_failure_log(
                        "ytm_url_metadata_match",
                        exc,
                        details=f"URL: {user_input}",
                    )

                if result:
                    result["input_type"] = "url"
                    result["ytm_matched"] = True
                    result["requested_artist"] = meta["artist"]
                    result["requested_title"] = meta["title"]
                    # Keep the exact source URL supplied by the user.
                    result["source_url"] = meta.get("source_url") or user_input
                    return result, ""

                # Fallback is safe because this metadata came from the exact
                # user-supplied YouTube Music video. Do not substitute a search
                # result with a different video ID.
                direct_result["source"] = "YouTube Music URL (exact source preserved)"
                direct_result["input_type"] = "url"
                direct_result["ytm_matched"] = False
                direct_result["requested_artist"] = meta["artist"]
                direct_result["requested_title"] = meta["title"]
                return direct_result, ""

            direct_result = self.direct_result_from_metadata(meta)
            if not direct_result:
                return None, "Could not build a direct YouTube download result"

            return direct_result, ""

        artist, title = split_artist_title(user_input)

        result = self.search(
            artist,
            title,
            "",
        )

        if not result:
            return None, "No YouTube Music result found"

        result["input_type"] = "search"
        result["ytm_matched"] = True
        result["requested_artist"] = artist
        result["requested_title"] = title
        return result, ""

    def _resolve_liked_music_entries(self, auth_path=None, cookie_path=None):
        """Resolve the account-bound Liked Music shelf through authenticated ytmusicapi.

        Prefer a user-supplied ytmusicapi browser-auth file when one exists.
        Otherwise, derive temporary browser headers from the toolkit's existing
        cookies.txt, then delete that temporary file immediately after loading
        the authenticated API client.
        """
        temporary_auth_path = None
        if auth_path is None:
            cookie_path = cookie_path or get_cookie_file_path()
            if not cookie_path:
                raise RuntimeError(
                    "No usable cookies.txt file was found. Select your existing YouTube "
                    "cookies file in the toolkit, then retry Liked Music."
                )
            temporary_auth_path = _create_temporary_ytmusic_auth_from_cookie_file(cookie_path)
            auth_path = temporary_auth_path

        try:
            auth_client = YTMusic(str(auth_path))
        finally:
            if temporary_auth_path is not None:
                try:
                    temporary_auth_path.unlink(missing_ok=True)
                except Exception:
                    pass

        try:
            payload = auth_client.get_liked_songs(limit=5000)
        except KeyError as exc:
            error_text = str(exc)
            if (
                "twoColumnBrowseResultsRenderer" in error_text
                or "Looking for what you've liked" in error_text
                or "Looking for what you’ve liked" in error_text
            ):
                # Provide only safe authentication diagnostics. Never log cookie
                # values or the Authorization hash; cookie names are sufficient
                # to tell whether the export contains a plausible YouTube session.
                auth_diagnostics = "unavailable"
                try:
                    headers = auth_client.base_headers
                    cookie_header = str(headers.get("cookie") or "")
                    cookie_names = sorted(set(
                        name
                        for name in re.findall(r"(?:^|;\s*)([^=;\s]+)=", cookie_header)
                    ))
                    auth_type = getattr(
                        auth_client.auth_type,
                        "name",
                        str(auth_client.auth_type),
                    )
                    auth_user = str(headers.get("x-goog-authuser") or "<missing>")
                    origin = str(
                        headers.get("origin")
                        or headers.get("x-origin")
                        or "<missing>"
                    )
                    authorization = str(headers.get("authorization") or "")
                    auth_scheme = authorization.split(" ", 1)[0] if authorization else "<missing>"
                    auth_diagnostics = (
                        f"auth_type={auth_type}; x-goog-authuser={auth_user}; "
                        f"origin={origin}; authorization_scheme={auth_scheme}; "
                        f"cookie_count={len(cookie_names)}; "
                        f"cookie_names={','.join(cookie_names) or '<none>'}"
                    )
                except Exception as diagnostic_exc:
                    auth_diagnostics = (
                        "diagnostics_error="
                        + type(diagnostic_exc).__name__
                    )

                raise RuntimeError(
                    "YouTube Music returned its signed-out Liked Music screen. "
                    "The selected cookies.txt was readable, but YouTube Music did not "
                    "accept the resulting authenticated API request. The toolkit now "
                    "builds the cookie header for the actual /youtubei/v1/browse API path. "
                    "Do not send cookie values or Authorization hashes. "
                    "Safe authentication diagnostics: "
                    + auth_diagnostics
                    + ". No separate ytmusicapi_browser.json file is needed."
                ) from exc
            raise

        tracks = payload.get("tracks") if isinstance(payload, dict) else None
        if not isinstance(tracks, list):
            tracks = []

        results = []
        for track in tracks:
            if not isinstance(track, dict):
                continue
            video_id = str(track.get("videoId") or track.get("video_id") or "").strip()
            title = str(track.get("title") or track.get("track") or "").strip()
            if not video_id or not title:
                continue

            entry = dict(track)
            entry["id"] = video_id
            entry["video_id"] = video_id
            entry["track"] = title
            entry["title"] = title
            # Use YouTube Music only to enumerate the authenticated shelf.
            # A normal YouTube watch URL avoids auto-selecting the web_music
            # client, whose GVS formats now require a PO Token.
            entry["source_url"] = f"https://www.youtube.com/watch?v={video_id}"
            entry["ytmusic_liked_entry"] = True
            results.append(entry)

        if not results:
            raise RuntimeError(
                "The authenticated YouTube Music API returned no usable Liked Music tracks. "
                "Confirm the browser-auth file belongs to the account that owns these likes."
            )
        return results


    def resolve_playlist_urls(self, playlist_url):
        parsed_url = urllib.parse.urlparse(playlist_url)
        parsed_query = urllib.parse.parse_qs(parsed_url.query)
        playlist_id = (parsed_query.get("list") or [""])[0]
        is_liked_music = is_youtube_music_liked_url(playlist_url)

        def _attempt(cookie_args):
            proc = subprocess.run(
                [
                    get_ytdlp_command(),
                    *get_ytdlp_runtime_args(),
                    "--dump-single-json",
                    "--flat-playlist",
                    "--skip-download",
                    "--ignore-errors",
                    *cookie_args,
                    "--",
                    playlist_url,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=90,
                **get_hidden_subprocess_kwargs(),
            )
            raw = proc.stdout.strip()
            stderr_text = (proc.stderr or "").strip()
            # --ignore-errors exits non-zero when a single entry is
            # unavailable but still prints the full playlist JSON.
            if not raw:
                raise RuntimeError(
                    f"yt-dlp returned no JSON (exit code {proc.returncode}). "
                    f"Details: {stderr_text[-1800:] or 'no stderr output'}"
                )

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"yt-dlp returned invalid playlist JSON (exit code {proc.returncode}). "
                    f"Output starts with {raw[:180]!r}. "
                    f"Details: {stderr_text[-1200:] or 'no stderr output'}"
                ) from exc

            if not isinstance(payload, dict):
                parsed = urllib.parse.urlparse(playlist_url)
                list_id = (urllib.parse.parse_qs(parsed.query).get("list") or [""])[0]
                if list_id == "LM":
                    raise RuntimeError(
                        "yt-dlp returned JSON null for YouTube Music's Liked Music playlist (list=LM). "
                        "This playlist is tied to your signed-in account, but yt-dlp did not receive its "
                        "track list. The configured cookies.txt may be expired, incomplete, or not accepted "
                        "for youtube.com. Re-authenticate and update the cookies file, then retry. "
                        f"yt-dlp details: {stderr_text[-1400:] or 'no stderr output'}"
                    )
                raise RuntimeError(
                    f"yt-dlp returned {type(payload).__name__} instead of a playlist object "
                    f"(exit code {proc.returncode}). "
                    f"Details: {stderr_text[-1400:] or 'no stderr output'}"
                )
            return payload

        try:
            if is_liked_music:
                auth_candidates = []
                env_auth = os.environ.get("YTM_MUSIC_TOOLKIT_YTMUSIC_AUTH_FILE", "").strip()
                if env_auth:
                    auth_candidates.append(Path(env_auth).expanduser())
                documents_dir = Path(os.path.expanduser("~")) / "Documents" / "YTDLP"
                auth_candidates.extend([
                    documents_dir / "ytmusicapi_browser.json",
                    documents_dir / "browser.json",
                    Path(RESOURCE_DIR) / "ytmusicapi_browser.json",
                ])
                auth_path = next((candidate for candidate in auth_candidates if candidate.is_file()), None)

                auth_errors = []
                if auth_path is not None:
                    try:
                        return self._resolve_liked_music_entries(auth_path)
                    except Exception as exc:
                        auth_errors.append(
                            f"browser-auth file ({auth_path.name}): {type(exc).__name__}: {exc}"
                        )

                cookie_path = get_cookie_file_path()
                if cookie_path:
                    try:
                        return self._resolve_liked_music_entries(None, cookie_path)
                    except Exception as exc:
                        auth_errors.append(
                            f"cookies.txt ({Path(cookie_path).name}): {type(exc).__name__}: {exc}"
                        )

                if not cookie_path and auth_path is None:
                    auth_errors.append(
                        "No cookies.txt file is configured. Select the YouTube cookies file "
                        "you already use for downloads in the toolkit."
                    )

                # Last-resort fallback: enumerate Liked Music with yt-dlp itself.
                # This can still work when ytmusicapi's browser-header emulation is
                # rejected, and it reuses the configured cookies.txt without exposing
                # cookie values or creating another credentials file.
                try:
                    data = ytdlp_retry_on_cookie_failure(playlist_url, _attempt)
                    yt_entries = data.get("entries") or []
                    yt_results = []

                    for entry in yt_entries:
                        if not isinstance(entry, dict):
                            continue
                        video_id = str(
                            entry.get("id") or entry.get("videoId") or ""
                        ).strip()
                        if not video_id:
                            continue

                        exact_url = (
                            entry.get("webpage_url")
                            or entry.get("webpage_url_basename")
                            or entry.get("url")
                            or ""
                        )
                        if isinstance(exact_url, str) and exact_url.startswith("http"):
                            source_url = exact_url
                        else:
                            source_url = f"https://www.youtube.com/watch?v={video_id}"

                        playlist_item = dict(entry)
                        playlist_item["video_id"] = video_id
                        playlist_item["source_url"] = source_url
                        yt_results.append(playlist_item)

                    if yt_results:
                        return yt_results

                    auth_errors.append(
                        "yt-dlp cookies fallback: Liked Music returned no usable entries"
                    )
                except Exception as exc:
                    auth_errors.append(
                        f"yt-dlp cookies fallback: {type(exc).__name__}: {exc}"
                    )

                raise RuntimeError(
                    "Could not read YouTube Music Liked Music. The toolkit tried the existing "
                    "ytmusicapi auth file, temporary headers built from cookies.txt, and a final "
                    "yt-dlp playlist fallback. "
                    + " | ".join(auth_errors)
                )

            data = ytdlp_retry_on_cookie_failure(playlist_url, _attempt)
            entries = data.get("entries") or []
            results = []

            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                video_id = str(entry.get("id") or entry.get("videoId") or "").strip()
                if not video_id:
                    continue

                # Prefer yt-dlp's exact webpage URL when present; otherwise
                # construct the canonical YouTube watch URL from the entry ID.
                exact_url = (
                    entry.get("webpage_url")
                    or entry.get("webpage_url_basename")
                    or entry.get("url")
                    or ""
                )
                if isinstance(exact_url, str) and exact_url.startswith("http"):
                    source_url = exact_url
                else:
                    source_url = f"https://www.youtube.com/watch?v={video_id}"

                # Preserve the flat playlist metadata as well as the exact URL.
                # The worker can use the listing's ID/title immediately and does
                # not need a separate metadata extraction for every playlist item.
                playlist_item = dict(entry)
                playlist_item["video_id"] = video_id
                playlist_item["source_url"] = source_url
                results.append(playlist_item)

            if not results and playlist_id == "LM":
                raise RuntimeError(
                    "yt-dlp returned a playlist object but no entries for YouTube Music's Liked Music playlist (list=LM). "
                    "This usually means the account-bound playlist was not exposed to yt-dlp; check that the configured "
                    "cookies.txt contains a current signed-in YouTube session."
                )
            return results
        except BrowserSessionError:
            raise
        except Exception as exc:
            log_path = write_failure_log(
                "playlist_resolve",
                exc,
                details=f"Playlist: {playlist_url}",
            )
            message = f"Could not read playlist entries: {exc}"
            if log_path:
                message += f"\nDiagnostic log: {log_path}"
            raise RuntimeError(message) from exc



# ============================================================
# METADATA / ARTWORK OPERATIONS
# ============================================================

def remove_album_artist_tags(flac):
    targets = {
        "albumartist",
        "album artist",
        "album_artist",
    }

    for key in list(flac.keys()):
        normalized = str(key).strip().lower().replace("-", " ")
        if normalized in targets:
            try:
                del flac[key]
            except Exception:
                pass


def rewrite_flac_metadata_only(file_path, result):
    """Rewrite descriptive FLAC metadata without changing the embedded album cover.

    This is the Metadata Rewriter's dedicated entry point. It snapshots all existing
    picture payloads, performs the strict metadata rewrite without replacement artwork,
    and then verifies every picture payload is byte-for-byte identical.
    """
    before = FLAC(file_path)
    before_covers = [bytes(p.data or b"") for p in list(before.pictures or [])]

    rewrite_flac_metadata_strict(
        file_path,
        result,
        replacement_cover_bytes=None,
    )

    after = FLAC(file_path)
    after_covers = [bytes(p.data or b"") for p in list(after.pictures or [])]
    if after_covers != before_covers:
        raise RuntimeError("Metadata Rewriter changed embedded album cover art")


def rewrite_flac_metadata_strict(
    file_path,
    result,
    replacement_cover_bytes=None,
):
    """Rewrite FLAC descriptive metadata to ARTIST, ALBUM, DATE.

    STREAMINFO is retained. Existing picture blocks are preserved when no
    replacement_cover_bytes are supplied; only an explicit replacement is allowed
    to change artwork. The Metadata Rewriter uses rewrite_flac_metadata_only().
    """
    flac = FLAC(file_path)

    streaminfo_blocks = [
        block
        for block in flac.metadata_blocks
        if getattr(block, "code", None) == StreamInfo.code
    ]

    if not streaminfo_blocks:
        raise RuntimeError("FLAC STREAMINFO block could not be found")

    preserved_pictures = []
    for picture in list(flac.pictures or []):
        preserved = Picture()
        preserved.type = picture.type
        preserved.mime = picture.mime
        preserved.desc = picture.desc
        preserved.width = picture.width
        preserved.height = picture.height
        preserved.depth = picture.depth
        preserved.colors = picture.colors
        preserved.data = picture.data
        preserved_pictures.append(preserved)

    flac.metadata_blocks = [streaminfo_blocks[0]]
    flac.tags = None
    flac.cuesheet = None
    flac.seektable = None
    flac.add_tags()

    artists = [
        str(name).strip()
        for name in (result.get("artist_names") or [])
        if str(name).strip()
    ]
    album = str(result.get("album") or "").strip()
    year = str(result.get("year") or "").strip()

    if artists:
        flac["ARTIST"] = artists
    if album:
        flac["ALBUM"] = album
    if year:
        flac["DATE"] = year

    if replacement_cover_bytes:
        normalized = normalize_cover_to_jpeg(replacement_cover_bytes)
        cover_picture = make_picture(normalized or replacement_cover_bytes)
        preserved_pictures = [cover_picture]

    flac.clear_pictures()
    for picture in preserved_pictures:
        flac.add_picture(picture)

    flac.save()


def write_flac_metadata(
    file_path,
    result,
    cover_bytes=None,
    wipe_tags=True,
):
    flac = FLAC(file_path)

    old_cover = flac.pictures[0].data if flac.pictures else None

    if wipe_tags:
        flac.delete()
        flac = FLAC(file_path)

    remove_album_artist_tags(flac)

    artists = result.get("artist_names") or []
    if artists:
        flac["ARTIST"] = artists

    album = result.get("album") or ""
    title = result.get("title") or ""
    year = result.get("year") or ""

    if album:
        flac["ALBUM"] = album

    if title:
        flac["TITLE"] = title

    if year:
        flac["DATE"] = year

    if cover_bytes is None:
        cover_bytes = old_cover

    if cover_bytes:
        normalized = normalize_cover_to_jpeg(cover_bytes)

        if normalized:
            cover_bytes = normalized

        flac.clear_pictures()
        flac.add_picture(make_picture(cover_bytes))

    flac.save()


def write_generic_audio_metadata(
    file_path,
    result,
    cover_bytes=None,
):
    suffix = Path(file_path).suffix.lower()
    artist = ", ".join(result.get("artist_names") or [])
    album = result.get("album") or ""
    title = result.get("title") or ""
    year = result.get("year") or ""

    try:
        if suffix == ".mp3":
            audio = ID3(file_path)

            audio.delall("TPE1")
            audio.delall("TALB")
            audio.delall("TIT2")
            audio.delall("TDRC")
            audio.delall("TPE2")
            audio.delall("APIC")

            if artist:
                audio.add(TPE1(encoding=3, text=artist))

            if album:
                audio.add(TALB(encoding=3, text=album))

            if title:
                audio.add(TIT2(encoding=3, text=title))

            if year:
                audio.add(TDRC(encoding=3, text=year))

            if cover_bytes:
                image = normalize_cover_to_jpeg(cover_bytes) or cover_bytes
                audio.add(
                    APIC(
                        encoding=3,
                        mime="image/jpeg",
                        type=3,
                        desc="Front Cover",
                        data=image,
                    )
                )

            audio.save(file_path)
            return True

        if suffix in {".m4a", ".mp4", ".aac"}:
            audio = MP4(file_path)

            if artist:
                audio["\xa9ART"] = [artist]

            if album:
                audio["\xa9alb"] = [album]

            if title:
                audio["\xa9nam"] = [title]

            if year:
                audio["\xa9day"] = [year]

            audio.pop("aART", None)

            if cover_bytes:
                image = normalize_cover_to_jpeg(cover_bytes) or cover_bytes
                audio["covr"] = [
                    MP4Cover(image, imageformat=MP4Cover.FORMAT_JPEG)
                ]

            audio.save()
            return True

        return False

    except Exception as exc:
        raise RuntimeError(
            f"Could not rewrite metadata for {file_path}: {exc}"
        ) from exc


def crop_flac_cover(file_path):
    flac = FLAC(file_path)

    if not flac.pictures:
        return False, "No cover art"

    existing = flac.pictures[0]
    image = Image.open(BytesIO(existing.data))
    image = ImageOps.exif_transpose(image)

    width, height = image.size

    if width == height:
        return True, f"Already 1:1 ({width}x{height})"

    minimum = min(width, height)

    left = (width - minimum) // 2
    top = (height - minimum) // 2

    cropped = image.crop(
        (
            left,
            top,
            left + minimum,
            top + minimum,
        )
    )

    if cropped.mode != "RGB":
        cropped = cropped.convert("RGB")

    buffer = BytesIO()
    cropped.save(
        buffer,
        format="JPEG",
        quality=100,
        subsampling=0,
    )

    flac.clear_pictures()
    flac.add_picture(make_picture(buffer.getvalue()))
    flac.save()

    return True, f"Cropped {width}x{height} -> {minimum}x{minimum}"


# ============================================================
# BASE GUI
# ============================================================

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
try:
    ctk.set_widget_scaling(0.95)
except Exception:
    pass


class DownloadCancelled(Exception):
    """Raised when the user intentionally stops an active download."""


class YTMMusicToolkit(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(APP_NAME)
        self.geometry("1080x920")
        self.minsize(860, 760)
        self.configure(fg_color=APPLE_ROOT_BG)

        self._startup_alpha_enabled = False
        self._window_restore_pending = False
        self._window_intro_started = False
        try:
            self.attributes("-alpha", 0.0)
            self._startup_alpha_enabled = True
        except Exception:
            pass

        icon_path = os.path.join(RESOURCE_DIR, "app.ico")

        if os.path.exists(icon_path):
            try:
                self.iconbitmap(default=icon_path)
            except Exception:
                pass

        self.custom_path = os.path.join(
            os.path.expanduser("~"),
            "Downloads",
        )

        self.active_process = None
        self.is_paused = False
        self.download_running = False
        self.stop_requested = False
        self._selected_download_format = " FLAC Lossless"
        self._selected_download_subtitles = False
        self.appearance_mode = "dark"

        # Silent, pre-download link preview state.
        self._dl_preview_job = None
        self._dl_preview_token = 0
        self._dl_preview_source = ""
        self._dl_preview_pil = None
        self._dl_preview_target_size = (96, 96)
        self._dl_preview_loading_job = None
        self._dl_preview_quality_options = []
        self._dl_preview_quality_source = ""
        self._dl_preview_mode = "none"
        self._dl_preview_is_playlist = False
        self._dl_playlist_cover_bytes = None
        self._dl_youtube_extractor_arg = None
        self._last_quality_extractor_arg = None
        self._dl_quality_visible = False

        self.cover_preview_image = None
        self.resolver = None

        self.paths = {
            "downloader": self.custom_path,
            "metadata": self.custom_path,
            "cover": self.custom_path,
            "crop": self.custom_path,
            "pipeline": self.custom_path,
        }

        self.load_config()

        ensure_failure_log_dir()

        self.taskbar_progress = WindowsTaskbarProgress(self)

        # A restrained native dark window with a single rounded application surface.
        self.main_container = ctk.CTkFrame(
            self,
            fg_color=APPLE_WINDOW_BG,
            corner_radius=26,
            border_width=1,
            border_color=APPLE_SEPARATOR,
        )
        self.main_container.pack(
            fill="both",
            expand=True,
            padx=12,
            pady=12,
        )

        self._animation_jobs = {}
        self._header_pulse_on = False
        self._header_pulse_job = None

        self.build_header()
        self.build_tabs()

        # Prepare the final theme and interaction bindings before the first
        # visible frame, then run one clean entrance animation.
        self.after_idle(self.finish_ui_startup)

        if pyi_splash and pyi_splash.is_alive():
            try:
                pyi_splash.close()
            except Exception:
                pass

    # --------------------------------------------------------
    # CONFIG
    # --------------------------------------------------------

    def load_config(self):
        try:
            if not os.path.exists(CONFIG_FILE):
                return

            with open(
                CONFIG_FILE,
                "r",
                encoding="utf-8",
            ) as handle:
                data = json.load(handle)

            saved_paths = data.get("paths", {})
            if isinstance(saved_paths, dict):
                for key in self.paths:
                    value = saved_paths.get(key)
                    if value and os.path.isdir(value):
                        self.paths[key] = value

        except Exception:
            pass

    def save_config(self):
        try:
            payload = {
                "paths": self.paths,
            }
            # Preserve the cookie path selected from the GUI when saving any
            # other settings through the legacy config wrappers.
            saved_cookie_path = _saved_cookie_file_path()
            if saved_cookie_path:
                payload["cookie_file_path"] = saved_cookie_path

            with open(
                CONFIG_FILE,
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(payload, handle, indent=2)
        except Exception:
            pass


    # --------------------------------------------------------
    # COMMON UI
    # --------------------------------------------------------

    def build_header(self):
        header = ctk.CTkFrame(
            self.main_container,
            fg_color=APPLE_SURFACE,
            corner_radius=20,
            border_width=1,
            border_color=APPLE_SEPARATOR,
        )
        self.header_card = header
        header.pack(
            fill="x",
            padx=8,
            pady=(8, 10),
        )

        accent = ctk.CTkFrame(
            header,
            height=3,
            fg_color=APPLE_BLUE,
            corner_radius=3,
        )
        self.brand_accent = accent
        accent.pack(
            fill="x",
            padx=20,
            pady=(12, 0),
        )

        body = ctk.CTkFrame(
            header,
            fg_color="transparent",
        )
        body.pack(
            fill="x",
            padx=20,
            pady=(10, 14),
        )

        brand = ctk.CTkFrame(
            body,
            fg_color="transparent",
        )
        brand.pack(
            side="left",
            fill="x",
            expand=True,
        )

        brand_badge = ctk.CTkFrame(
            brand,
            width=48,
            height=48,
            fg_color="#223956",
            corner_radius=15,
            border_width=1,
            border_color="#365B86",
        )
        self.brand_badge = brand_badge
        brand_badge.pack(
            side="left",
            padx=(0, 12),
        )
        brand_badge.pack_propagate(False)

        ctk.CTkLabel(
            brand_badge,
            text="♫",
            font=(APP_FONT, 24, "bold"),
            text_color=APPLE_TEXT,
        ).pack(
            expand=True,
        )

        title_stack = ctk.CTkFrame(
            brand,
            fg_color="transparent",
        )
        title_stack.pack(
            side="left",
            fill="x",
            expand=True,
        )

        ctk.CTkLabel(
            title_stack,
            text="YTM Music Toolkit",
            font=(APP_FONT, 21, "bold"),
            text_color="#ffffff",
            anchor="w",
        ).pack(
            anchor="w",
        )

        ctk.CTkLabel(
            title_stack,
            text="Music downloads, metadata & artwork — in one place",
            font=(APP_FONT, 12),
            text_color=APPLE_MUTED,
            anchor="w",
        ).pack(
            anchor="w",
            pady=(1, 0),
        )

        meta = ctk.CTkFrame(
            body,
            fg_color="transparent",
        )
        meta.pack(
            side="right",
        )

        self.header_status = ctk.CTkLabel(
            meta,
            text="● READY",
            font=(APP_FONT, 10, "bold"),
            text_color="#67e8f9",
        )
        self.header_status.pack(
            side="right",
            padx=(8, 0),
        )

        self.cookie_status = ctk.CTkLabel(
            meta,
            text=" Cookie file: checking...",
            font=(APP_FONT, 10),
            text_color="#64748b",
        )
        self.cookie_status.pack(
            side="right",
            padx=(0, 8),
        )

        self.cookie_browse_button = ctk.CTkButton(
            meta,
            text=" Browse",
            width=78,
            height=28,
            font=(APP_FONT, 10, "bold"),
            fg_color=APPLE_SURFACE_ELEVATED,
            hover_color=APPLE_SEPARATOR_HOVER,
            text_color=APPLE_TEXT,
            border_width=1,
            border_color=APPLE_SEPARATOR,
            corner_radius=10,
            command=self.browse_cookie_file,
        )
        self.cookie_browse_button.pack(
            side="right",
            padx=(0, 8),
        )

        self.theme_toggle_button = ctk.CTkButton(
            meta,
            text="☀",
            width=38,
            height=28,
            font=(APP_FONT, 17, "bold"),
            fg_color=APPLE_SURFACE_ELEVATED,
            hover_color=APPLE_SEPARATOR_HOVER,
            text_color=APPLE_TEXT,
            border_width=1,
            border_color=APPLE_SEPARATOR,
            corner_radius=10,
            command=self.toggle_appearance_mode,
        )
        self.theme_toggle_button.pack(
            side="right",
            padx=(0, 8),
        )
        self.update_theme_toggle_button()

        def _on_cookie_file_status(label, details=""):
            def apply():
                try:
                    palette = APPLE_THEME_PALETTES.get(
                        getattr(self, "appearance_mode", "dark"),
                        APPLE_THEME_PALETTES["dark"],
                    )
                    if label:
                        self.cookie_status.configure(
                            text=f" Cookies: {label}",
                            text_color=palette["green"],
                        )
                    else:
                        self.cookie_status.configure(
                            text=" Missing cookies.txt",
                            text_color=palette["red"],
                        )
                except Exception:
                    pass
            try:
                self.after(0, apply)
            except Exception:
                pass

        set_browser_session_listener(_on_cookie_file_status)
        cookie_path = get_cookie_file_path()
        if cookie_path:
            _on_cookie_file_status(Path(cookie_path).name, cookie_path)
        else:
            _on_cookie_file_status(None, _no_session_message())

    def browse_cookie_file(self):
        """Open a file picker and remember the selected Netscape cookies file."""
        current = get_cookie_file_path()
        initial_dir = str(Path(current).parent) if current else str(Path.home() / "Documents")
        selected = filedialog.askopenfilename(
            title="Select YouTube cookies.txt",
            initialdir=initial_dir,
            filetypes=[
                ("Netscape cookie files", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return

        candidate = Path(selected)
        if not _is_valid_cookie_file(candidate):
            messagebox.showerror(
                "Invalid cookie file",
                "Please select a Netscape-format cookies.txt file.\n\n"
                "The file should start with '# Netscape HTTP Cookie File' "
                "or '# HTTP Cookie File'.",
                parent=self,
            )
            return

        try:
            _save_selected_cookie_file(candidate)
        except Exception as exc:
            write_failure_log("cookie_file_save", exc, details=f"Selected path: {candidate}")
            messagebox.showerror(
                "Could not save cookie selection",
                f"The cookie file was selected, but its path could not be saved.\n\n{exc}",
                parent=self,
            )
            return

        _notify_browser_session(candidate.name, str(candidate.resolve()))

    def build_tabs(self):
        self.tabs = ctk.CTkTabview(
            self.main_container,
            fg_color=APPLE_WINDOW_BG,
            segmented_button_fg_color=APPLE_SURFACE,
            segmented_button_selected_color=APPLE_BLUE,
            segmented_button_selected_hover_color=APPLE_BLUE_HOVER,
            segmented_button_unselected_color=APPLE_SURFACE,
            segmented_button_unselected_hover_color=APPLE_SURFACE_ELEVATED,
            text_color=APPLE_TEXT,
            corner_radius=20,
            border_width=1,
            border_color=APPLE_SEPARATOR,
        )
        self.tabs.pack(
            fill="both",
            expand=True,
            padx=8,
            pady=(0, 7),
        )

        tab_downloader = self.tabs.add("Downloader")
        tab_queue = self.tabs.add("Queue")
        tab_metadata = self.tabs.add("Metadata")
        tab_cover = self.tabs.add("Cover Art")
        tab_crop = self.tabs.add("Crop Art")
        tab_pipeline = self.tabs.add("Library Overhaul")
        self._apple_tab_pages = [
            tab_downloader,
            tab_queue,
            tab_metadata,
            tab_cover,
            tab_crop,
            tab_pipeline,
        ]

        self.build_downloader_tab(tab_downloader)
        self.build_queue_tab(tab_queue)
        self.build_metadata_tab(tab_metadata)
        self.build_cover_tab(tab_cover)
        self.build_crop_tab(tab_crop)
        self.build_pipeline_tab(tab_pipeline)

        try:
            seg = self.tabs._segmented_button
            seg.configure(
                corner_radius=13,
                border_width=0,
                border_color=APPLE_SEPARATOR,
                font=(APP_FONT, 12, "bold"),
            )
        except Exception:
            pass

        footer = ctk.CTkFrame(
            self.main_container,
            height=22,
            fg_color="transparent",
        )
        footer.pack(
            fill="x",
            padx=18,
            pady=(0, 3),
        )

        ctk.CTkLabel(
            footer,
            text="YOUTUBE MUSIC  ·  LOSSLESS AUDIO  ·  ARTWORK  ·  LIBRARY",
            font=(APP_FONT, 9, "bold"),
            text_color=APPLE_MUTED,
        ).pack(
            anchor="center",
        )

    def make_path_row(self, parent, path_key):
        row = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )
        row.grid_columnconfigure(0, weight=1)

        label = ctk.CTkLabel(
            row,
            text=f" Save To: {self.paths[path_key]}",
            font=(APP_FONT, 12),
            text_color="#ffffff",
            anchor="w",
        )
        label.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 8),
        )

        button = ctk.CTkButton(
            row,
            text=" Browse",
            width=88,
            height=31,
            font=(APP_FONT, 12, "bold"),
            fg_color="#050505",
            hover_color="#1e293b",
            text_color="#ffffff",
            corner_radius=8,
            command=lambda: self.select_directory(
                path_key,
                label,
            ),
        )
        button.grid(
            row=0,
            column=1,
        )

        return row, label

    def select_directory(self, path_key, label=None):
        directory = filedialog.askdirectory(
            initialdir=self.paths.get(
                path_key,
                self.custom_path,
            ),
        )

        if not directory:
            return

        self.paths[path_key] = directory
        self.save_config()

        if label is not None:
            self.set_label(
                label,
                f" Save To: {directory}",
            )

    def append_log(self, textbox, message):
        if textbox is None:
            return

        def write_log():
            try:
                textbox.configure(state="normal")
                textbox.insert("end", message.rstrip() + "\n")
                textbox.see("end")
                textbox.configure(state="disabled")
            except Exception:
                pass

        try:
            self.after(0, write_log)
        except Exception:
            pass

    def make_operation_meter(self, parent, prefix, initial_message="Waiting for operation..."):
        """Create a hidden operation meter that is revealed when work starts."""
        meter = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )
        meter.pack(
            fill="x",
            padx=22,
            pady=(0, 14),
        )

        bar = ctk.CTkProgressBar(
            meter,
            height=11,
            corner_radius=6,
            fg_color="#050505",
            progress_color="#38bdf8",
        )
        bar.pack(fill="x")
        bar.set(0)

        info = ctk.CTkFrame(
            meter,
            fg_color="transparent",
        )
        info.pack(
            fill="x",
            pady=(6, 0),
        )
        info.grid_columnconfigure(0, weight=1)

        message = ctk.CTkLabel(
            info,
            text=initial_message,
            font=(APP_FONT, 10, "bold"),
            text_color="#94a3b8",
            anchor="w",
        )
        message.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        percent = ctk.CTkLabel(
            info,
            text="0%",
            font=(APP_FONT, 10, "bold"),
            text_color="#64748b",
            anchor="e",
        )
        percent.grid(
            row=0,
            column=1,
            sticky="e",
            padx=(10, 0),
        )

        setattr(self, f"{prefix}_progress", bar)
        setattr(self, f"{prefix}_progress_message", message)
        setattr(self, f"{prefix}_progress_percent", percent)
        setattr(self, f"{prefix}_progress_meter", meter)

        meter.pack_forget()
        return meter

    def show_operation_meter(self, prefix):
        """Reveal a hidden operation meter with a small slide/fade-style entrance."""
        meter = getattr(self, f"{prefix}_progress_meter", None)
        if meter is None:
            return

        try:
            meter.pack(
                fill="x",
                padx=22,
                pady=(0, 0),
            )
        except Exception:
            return

        def update(amount):
            try:
                meter.pack_configure(
                    pady=(0, round(14 * amount)),
                )
            except Exception:
                pass

        def done():
            try:
                meter.pack_configure(pady=(0, 14))
            except Exception:
                pass

        self._animate(
            f"operation-meter-in:{prefix}",
            280,
            update,
            done,
        )


    def show_activity_console(self, prefix):
        """Reveal a terminal-style activity panel for the active operation."""
        panel = getattr(self, f"{prefix}_console_panel", None)
        tab = getattr(self, f"{prefix}_console_tab", None)
        row = getattr(self, f"{prefix}_console_row", None)

        if panel is None or tab is None or row is None:
            return

        palette = (
            getattr(self, "_apple_theme_transition_palette", None)
            or APPLE_THEME_PALETTES.get(
                getattr(self, "appearance_mode", "dark"),
                APPLE_THEME_PALETTES["dark"],
            )
        )

        try:
            tab.grid_rowconfigure(row, weight=1)
            panel.grid(
                row=row,
                column=0,
                padx=18,
                pady=7,
                sticky="nsew",
            )
            panel.update_idletasks()
            target_height = max(1, int(panel.winfo_reqheight()))

            panel.configure(
                height=1,
                border_color=palette["separator"],
            )
            panel.grid_propagate(False)

            def update(amount):
                try:
                    panel.configure(
                        height=max(1, round(1 + (target_height - 1) * amount)),
                        border_color=self._blend_colors(
                            palette["separator"],
                            palette["separator_hover"],
                            amount,
                        ),
                    )
                except Exception:
                    pass

            def done():
                try:
                    panel.grid_propagate(True)
                    panel.configure(
                        border_color=palette["separator"],
                    )
                except Exception:
                    pass

            self._animate(
                f"activity-console-in:{prefix}",
                340,
                update,
                done,
            )
        except Exception:
            pass


    def hide_activity_console(self, prefix):
        """Collapse a terminal-style activity panel while the tab is inactive."""
        panel = getattr(self, f"{prefix}_console_panel", None)
        tab = getattr(self, f"{prefix}_console_tab", None)
        row = getattr(self, f"{prefix}_console_row", None)

        if panel is None or tab is None or row is None:
            return

        try:
            panel.grid_remove()
            tab.grid_rowconfigure(row, weight=0)
            panel.grid_propagate(True)
        except Exception:
            pass


    def set_operation_progress(self, prefix, percent, message, taskbar=False):
        """Update a complete operation meter safely from worker threads."""
        value = max(0.0, min(100.0, float(percent)))

        # While one playlist item is being processed, treat incoming download
        # progress as that item's local 0–100% and map it to the entire playlist.
        # This keeps nested download, audio-track, thumbnail, and mux stages from
        # resetting the visible percentage back to the current item's percentage.
        playlist_context = getattr(self, "_dl_playlist_progress_context", None)
        if prefix == "dl" and playlist_context:
            try:
                item_index, item_total = playlist_context
                item_total = max(1, int(item_total))
                item_index = max(1, min(item_total, int(item_index)))
                value = ((item_index - 1) + (value / 100.0)) / item_total * 100.0
                value = max(0.0, min(100.0, value))
            except Exception:
                pass

        bar = getattr(self, f"{prefix}_progress", None)
        message_label = getattr(self, f"{prefix}_progress_message", None)
        percent_label = getattr(self, f"{prefix}_progress_percent", None)
        status_label = getattr(self, f"{prefix}_status", None)

        def update():
            try:
                if bar is not None:
                    bar.set(value / 100.0)
                if message_label is not None:
                    new_message = str(message)
                    if str(message_label.cget("text")) != new_message:
                        self.animate_text_change(
                            message_label,
                            new_message,
                            final_color="#94a3b8",
                            duration_out=450,
                            duration_in=550,
                            key=f"operation-message:{prefix}",
                        )
                # The percentage updates frequently, so it remains crisp
                # instead of launching a fade animation on every tick.
                if percent_label is not None:
                    percent_label.configure(text=f"{value:.0f}%")
                if status_label is not None:
                    status_text = f"Status: {message}"
                    if str(status_label.cget("text")) != status_text:
                        self.animate_text_change(
                            status_label,
                            status_text,
                            final_color="#ffffff",
                            duration_out=450,
                            duration_in=550,
                            key=f"operation-status:{prefix}",
                        )
                if taskbar:
                    self.taskbar_progress.set_progress(value, 100)
            except Exception:
                pass

        try:
            self.after(0, update)
        except Exception:
            pass

    def set_collection_progress(
        self,
        prefix,
        index,
        total,
        local_fraction,
        message,
        taskbar=False,
    ):
        total = max(1, int(total))
        local = max(0.0, min(1.0, float(local_fraction)))
        overall = ((index - 1) + local) / total * 100.0
        self.set_operation_progress(
            prefix,
            overall,
            message,
            taskbar=taskbar,
        )

    def animate_text_change(
        self,
        widget,
        text,
        final_color=None,
        duration_out=450,
        duration_in=550,
        key=None,
    ):
        """Fade label text out, swap it, then fade it back in.

        This deliberately does not touch the preview's Loading Preview...
        animation, which has its own dedicated timing loop.
        """
        if widget is None:
            return

        key = key or f"text:{id(widget)}"

        try:
            current_color = self._animation_color(
                widget.cget("text_color"),
                "#ffffff",
            )
        except Exception:
            current_color = "#ffffff"

        target_color = self._animation_color(
            final_color if final_color is not None else current_color,
            current_color,
        )
        fade_color = self._blend_colors(
            target_color,
            "#000000",
            0.90,
        )

        def fade_out_done():
            try:
                widget.configure(
                    text=text,
                    text_color=fade_color,
                )
            except Exception:
                return

            self._animate(
                f"{key}:in",
                duration_in,
                lambda amount: widget.configure(
                    text_color=self._blend_colors(
                        fade_color,
                        target_color,
                        amount,
                    )
                ),
                lambda: widget.configure(
                    text=text,
                    text_color=target_color,
                ),
            )

        self._animate(
            f"{key}:out",
            duration_out,
            lambda amount: widget.configure(
                text_color=self._blend_colors(
                    current_color,
                    fade_color,
                    amount,
                )
            ),
            fade_out_done,
        )

    def set_label(self, label, text):
        """Set label text with a slow 1-second fade only when the text changes."""
        def update():
            try:
                new_text = str(text)
                if str(label.cget("text")) == new_text:
                    return
                self.animate_text_change(
                    label,
                    new_text,
                    duration_out=450,
                    duration_in=550,
                    key=f"label:{id(label)}",
                )
            except Exception:
                pass

        try:
            self.after(0, update)
        except Exception:
            pass


    def ensure_resolver(self):
        if self.resolver is None:
            self.resolver = YTMResolver()
        return self.resolver

    def set_header_status(self, text="● READY", busy=False):
        def update_status():
            try:
                self._header_pulse_on = bool(busy)
                self.animate_text_change(
                    self.header_status,
                    text,
                    final_color=(
                        APPLE_THEME_PALETTES.get(
                            getattr(self, "appearance_mode", "dark"),
                            APPLE_THEME_PALETTES["dark"],
                        )["orange" if busy else "green"]
                    ),
                    key="header-status-text",
                )
            except Exception:
                pass

        try:
            self.after(0, update_status)
        except Exception:
            pass

    def pulse_header_status(self):
        try:
            if not hasattr(self, "header_status"):
                return

            busy = self._header_pulse_on
            palette = APPLE_THEME_PALETTES.get(
                getattr(self, "appearance_mode", "dark"),
                APPLE_THEME_PALETTES["dark"],
            )
            if busy:
                colors = (palette["orange"], palette["orange_pulse"])
            else:
                colors = (palette["green"], palette["green_pulse"])

            current = self.header_status.cget("text_color")
            next_color = colors[1] if current == colors[0] else colors[0]
            self.header_status.configure(text_color=next_color)
            self._header_pulse_job = self.after(700, self.pulse_header_status)
        except Exception:
            pass

    # --------------------------------------------------------
    # UI TRANSITIONS
    # --------------------------------------------------------

    @staticmethod
    def _animation_color(color, transparent_fallback="#000000"):
        if isinstance(color, (tuple, list)):
            if len(color) >= 2:
                color = color[1] if ctk.get_appearance_mode().lower() == "dark" else color[0]
            elif color:
                color = color[0]

        color = str(color or transparent_fallback)

        if color.lower() == "transparent":
            return transparent_fallback

        named = {
            "white": "#ffffff",
            "black": "#000000",
            "red": "#ff0000",
            "blue": "#0000ff",
            "gray": "#808080",
            "grey": "#808080",
        }
        color = named.get(color.lower(), color)

        if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            return color.lower()

        return transparent_fallback

    @staticmethod
    def _blend_colors(start, end, amount):
        def parse(value):
            value = value.lstrip("#")
            return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))

        a = parse(start)
        b = parse(end)
        mixed = tuple(
            int(a[i] + (b[i] - a[i]) * amount)
            for i in range(3)
        )
        return "#{:02x}{:02x}{:02x}".format(*mixed)

    def _animate(self, key, duration_ms, update, on_done=None):
        old_job = self._animation_jobs.get(key)
        if old_job:
            try:
                self.after_cancel(old_job)
            except Exception:
                pass

        started = time.perf_counter()
        duration = max(1, duration_ms) / 1000.0

        def tick():
            elapsed = time.perf_counter() - started
            t = min(1.0, elapsed / duration)
            eased = 1.0 - (1.0 - t) ** 3

            try:
                update(eased)
            except Exception:
                self._animation_jobs.pop(key, None)
                return

            if t < 1.0:
                self._animation_jobs[key] = self.after(16, tick)
            else:
                self._animation_jobs.pop(key, None)
                if on_done:
                    try:
                        on_done()
                    except Exception:
                        pass

        tick()

    def finish_ui_startup(self):
        try:
            self.install_transitions()
            self.update_idletasks()
        except Exception as exc:
            write_failure_log("ui_startup_prepare", exc)
        self.animate_window_in()


    def animate_window_in(self):
        if getattr(self, "_window_intro_started", False):
            return
        self._window_intro_started = True

        try:
            if not getattr(self, "_startup_alpha_enabled", False):
                self.attributes("-alpha", 0.0)
            self.update_idletasks()
        except Exception:
            return

        def update(amount):
            try:
                self.attributes("-alpha", amount)
            except Exception:
                pass

        def done():
            try:
                self.attributes("-alpha", 1.0)
            except Exception:
                pass

        self._animate("window_alpha", 360, update, done)


    def remember_window_minimize(self, event=None):
        if event is not None and getattr(event, "widget", self) is not self:
            return

        def check_state():
            try:
                if str(self.state()).lower() == "iconic":
                    self._window_restore_pending = True
            except Exception:
                pass

        try:
            self.after_idle(check_state)
        except Exception:
            check_state()


    def animate_window_restore(self, event=None):
        if event is not None and getattr(event, "widget", self) is not self:
            return
        if not getattr(self, "_window_restore_pending", False):
            return

        self._window_restore_pending = False

        try:
            if str(self.state()).lower() == "iconic":
                self._window_restore_pending = True
                return
            self.attributes("-alpha", 0.86)
        except Exception:
            return

        def update(amount):
            try:
                self.attributes("-alpha", 0.86 + (0.14 * amount))
            except Exception:
                pass

        def done():
            try:
                self.attributes("-alpha", 1.0)
            except Exception:
                pass

        self._animate("window_restore", 190, update, done)

    def animate_widget_color(
        self,
        widget,
        option,
        start_color,
        end_color,
        duration=140,
        final_color=None,
    ):
        start = self._animation_color(start_color)
        end = self._animation_color(end_color)
        key = f"color:{id(widget)}:{option}"

        def update(amount):
            widget.configure(
                **{option: self._blend_colors(start, end, amount)}
            )

        def done():
            if final_color is not None:
                try:
                    widget.configure(**{option: final_color})
                except Exception:
                    pass

        self._animate(key, duration, update, done)

    def bind_smooth_button(self, button):
        if getattr(button, "_apple_smooth_bound", False):
            return
        button._apple_smooth_bound = True

        def palette():
            return APPLE_THEME_PALETTES.get(
                getattr(self, "appearance_mode", "dark"),
                APPLE_THEME_PALETTES["dark"],
            )

        def on_enter(_event=None):
            try:
                target = getattr(button, "_apple_theme_hover_fg", palette()["surface_elevated"])
                self.animate_widget_color(
                    button, "fg_color", button.cget("fg_color"),
                    target, 125,
                )
            except Exception:
                pass

        def on_leave(_event=None):
            try:
                target = getattr(button, "_apple_theme_base_fg", palette()["surface_elevated"])
                self.animate_widget_color(
                    button, "fg_color", button.cget("fg_color"),
                    target, 150, target,
                )
            except Exception:
                pass

        def on_press(_event=None):
            try:
                base = self._animation_color(getattr(button, "_apple_theme_base_fg", palette()["surface_elevated"]))
                hover = self._animation_color(getattr(button, "_apple_theme_hover_fg", palette()["surface_elevated"]))
                target = self._blend_colors(base, hover, 0.72)
                self.animate_widget_color(button, "fg_color", button.cget("fg_color"), target, 65)
            except Exception:
                pass

        def on_release(_event=None):
            on_enter()

        button.configure(hover=False)
        button.bind("<Enter>", on_enter, add="+")
        button.bind("<Leave>", on_leave, add="+")
        button.bind("<ButtonPress-1>", on_press, add="+")
        button.bind("<ButtonRelease-1>", on_release, add="+")


    def bind_card_glow(self, card):
        if getattr(card, "_apple_card_bound", False):
            return
        try:
            if int(card.cget("border_width")) <= 0:
                return
        except Exception:
            return
        card._apple_card_bound = True

        def on_enter(_event=None):
            try:
                palette = APPLE_THEME_PALETTES.get(
                    getattr(self, "appearance_mode", "dark"),
                    APPLE_THEME_PALETTES["dark"],
                )
                self.animate_widget_color(
                    card, "border_color", card.cget("border_color"),
                    palette["separator_hover"], 160,
                )
            except Exception:
                pass

        def on_leave(_event=None):
            try:
                target = getattr(card, "_apple_theme_base_border", None)
                if target is None:
                    target = APPLE_THEME_PALETTES.get(
                        getattr(self, "appearance_mode", "dark"),
                        APPLE_THEME_PALETTES["dark"],
                    )["separator"]
                self.animate_widget_color(
                    card, "border_color", card.cget("border_color"),
                    target, 180, target,
                )
            except Exception:
                pass

        card.bind("<Enter>", on_enter, add="+")
        card.bind("<Leave>", on_leave, add="+")


    def bind_focus_glow(self, widget):
        if getattr(widget, "_apple_focus_bound", False):
            return
        widget._apple_focus_bound = True

        def on_focus_in(_event=None):
            try:
                palette = APPLE_THEME_PALETTES.get(
                    getattr(self, "appearance_mode", "dark"),
                    APPLE_THEME_PALETTES["dark"],
                )
                self.animate_widget_color(
                    widget, "border_color", widget.cget("border_color"),
                    palette["blue"], 140,
                )
            except Exception:
                pass

        def on_focus_out(_event=None):
            try:
                target = getattr(widget, "_apple_theme_base_border", None)
                if target is None:
                    target = APPLE_THEME_PALETTES.get(
                        getattr(self, "appearance_mode", "dark"),
                        APPLE_THEME_PALETTES["dark"],
                    )["separator"]
                self.animate_widget_color(
                    widget, "border_color", widget.cget("border_color"),
                    target, 180, target,
                )
            except Exception:
                pass

        widget.bind("<FocusIn>", on_focus_in, add="+")
        widget.bind("<FocusOut>", on_focus_out, add="+")


    @staticmethod
    def _tab_grid_pady_pair(widget):
        # Preserve the real layout margins on the first animation pass.
        # Otherwise each tab visit would use the previous animation's smaller
        # padding as its new baseline, gradually squeezing the layout.
        saved = getattr(widget, "_apple_tab_original_pady", None)
        if saved is not None:
            return saved

        info = widget.grid_info()
        if not info:
            return None

        raw = info.get("pady", 0)
        if isinstance(raw, str):
            parts = raw.split()
            if len(parts) >= 2:
                pair = (int(float(parts[0])), int(float(parts[1])))
            elif len(parts) == 1:
                value = int(float(parts[0]))
                pair = (value, value)
            else:
                pair = (0, 0)
        elif isinstance(raw, (tuple, list)):
            if len(raw) >= 2:
                pair = (int(raw[0]), int(raw[1]))
            else:
                value = int(raw[0]) if raw else 0
                pair = (value, value)
        else:
            value = int(raw or 0)
            pair = (value, value)

        try:
            widget._apple_tab_original_pady = pair
        except Exception:
            pass
        return pair


    def animate_tab_in(self, tab_name):
        """Stagger visible panels into place so tabs feel like one coherent interface."""
        try:
            tab = self.tabs.tab(tab_name)
            children = list(tab.winfo_children())
        except Exception:
            return

        records = []
        for index, widget in enumerate(children):
            try:
                pair = self._tab_grid_pady_pair(widget)
                if pair is None:
                    continue
                final_top, final_bottom = pair
                start_top = final_top + 13 + min(index, 4) * 3
                start_bottom = final_bottom + 4
                widget.grid_configure(pady=(start_top, start_bottom))
                records.append((
                    widget, index, start_top, start_bottom,
                    final_top, final_bottom,
                ))
            except Exception:
                pass

        if not records:
            return

        def update(amount):
            for widget, index, start_top, start_bottom, final_top, final_bottom in records:
                try:
                    delay = min(0.28, index * 0.075)
                    local = max(0.0, min(1.0, (amount - delay) / (1.0 - delay)))
                    local = 1.0 - ((1.0 - local) ** 3)
                    top = round(start_top + (final_top - start_top) * local)
                    bottom = round(start_bottom + (final_bottom - start_bottom) * local)
                    widget.grid_configure(pady=(top, bottom))
                except Exception:
                    pass

        self._animate(f"tab_in:{tab_name}", 300, update)


    def animate_tab_out(self, tab_name, on_done=None):
        """Nudge the current panels out before the next page is mapped."""
        try:
            tab = self.tabs.tab(tab_name)
            children = list(tab.winfo_children())
        except Exception:
            if on_done:
                on_done()
            return

        records = []
        for index, widget in enumerate(children):
            try:
                pair = self._tab_grid_pady_pair(widget)
                if pair is None:
                    continue
                start_top, start_bottom = pair
                end_top = max(0, start_top - 8 - min(index, 4) * 2)
                end_bottom = max(0, start_bottom - 3)
                records.append((widget, index, start_top, start_bottom, end_top, end_bottom))
            except Exception:
                pass

        if not records:
            if on_done:
                on_done()
            return

        def update(amount):
            for widget, index, start_top, start_bottom, end_top, end_bottom in records:
                try:
                    delay = min(0.18, index * 0.045)
                    local = max(0.0, min(1.0, (amount - delay) / (1.0 - delay)))
                    local = 1.0 - ((1.0 - local) ** 2)
                    top = round(start_top + (end_top - start_top) * local)
                    bottom = round(start_bottom + (end_bottom - start_bottom) * local)
                    widget.grid_configure(pady=(top, bottom))
                except Exception:
                    pass

        self._animate(f"tab_out:{tab_name}", 145, update, on_done)


    def animate_tab_indicator(self, source_tab, target_tab):
        """Move the selected pill through adjacent segment colors instead of snapping."""
        try:
            seg = self.tabs._segmented_button
            buttons = getattr(seg, "_buttons_dict", {})
            names = list(buttons.keys())
            start_index = names.index(source_tab)
            end_index = names.index(target_tab)
        except Exception:
            return

        palette = (
            getattr(self, "_apple_theme_transition_palette", None)
            or APPLE_THEME_PALETTES.get(
                getattr(self, "appearance_mode", "dark"),
                APPLE_THEME_PALETTES["dark"],
            )
        )
        base_color = palette["surface"]
        selected_color = palette["blue"]
        source_position = float(start_index)
        target_position = float(end_index)

        def update(amount):
            position = source_position + (target_position - source_position) * amount
            for index, name in enumerate(names):
                try:
                    distance = abs(float(index) - position)
                    strength = max(0.0, 1.0 - (distance / 1.25))
                    fill = self._blend_colors(base_color, selected_color, strength)
                    buttons[name].configure(
                        fg_color=fill,
                        hover_color=palette["surface_elevated"],
                    )
                except Exception:
                    pass

        def done():
            try:
                seg.set(target_tab)
            except Exception:
                pass

        self._animate("tab_indicator_move", 285, update, done)


    def on_tab_changed(self, tab_name):
        # Fallback callback for programmatic/custom tab changes.
        try:
            self._current_tab_name = tab_name
        except Exception:
            pass
        self.after(10, lambda name=tab_name: self.animate_tab_in(name))

    def _tab_content_geometry(self, tab_name):
        tab = self.tabs.tab(tab_name)
        tab.update_idletasks()
        return (
            tab.winfo_rootx(),
            tab.winfo_rooty(),
            max(1, tab.winfo_width()),
            max(1, tab.winfo_height()),
        )

    def _create_tab_fade_overlay(self, tab_name):
        try:
            x, y, width, height = self._tab_content_geometry(tab_name)
            overlay = ctk.CTkToplevel(self)
            overlay.overrideredirect(True)
            overlay.configure(fg_color="#000000")
            overlay.geometry(f"{width}x{height}+{x}+{y}")
            overlay.attributes("-topmost", True)
            overlay.attributes("-alpha", 0.0)
            overlay.withdraw()
            overlay.deiconify()
            overlay.lift()
            return overlay
        except Exception:
            return None

    def _destroy_tab_fade_overlay(self, overlay):
        if overlay is None:
            return
        try:
            overlay.destroy()
        except Exception:
            pass

    def _request_tab_transition(self, target_tab):
        target_tab = str(target_tab)

        try:
            current_tab = str(self._current_tab_name)
        except AttributeError:
            current_tab = self.tabs.get()
            self._current_tab_name = current_tab

        names = list(self.tabs._tab_dict.keys())
        if target_tab not in names or target_tab == current_tab:
            return

        if getattr(self, "_tab_transition_running", False):
            self._queued_tab_target = target_tab
            return

        self._tab_transition_running = True
        self._queued_tab_target = None
        self.animate_tab_indicator(current_tab, target_tab)

        def finish_transition():
            try:
                original_set = getattr(self, "_tab_transition_original_set", None)
                if original_set:
                    original_set(target_tab)
                else:
                    self.tabs.set(target_tab)

                self._current_tab_name = target_tab

                # CTkTabview schedules its old-page cleanup 100 ms later. Hide
                # every non-current page immediately so the outgoing tab cannot
                # remain layered underneath the new one for a frame.
                try:
                    self.tabs._grid_forget_all_tabs(exclude_name=target_tab)
                except Exception:
                    for page_name, page in getattr(self.tabs, "_tab_dict", {}).items():
                        if page_name != target_tab:
                            try:
                                page.grid_forget()
                            except Exception:
                                pass

                # Flush Tk's geometry/drawing queue between hiding the old page
                # and starting the new page's entrance; this prevents stale-frame bleed.
                self.tabs.update_idletasks()
                self.update_idletasks()
                self.animate_tab_in(target_tab)
            except Exception as exc:
                write_failure_log("tab_transition_switch", exc)

            def unlock():
                self._tab_transition_running = False
                pending = getattr(self, "_queued_tab_target", None)
                self._queued_tab_target = None
                if pending and pending != self._current_tab_name:
                    self._request_tab_transition(pending)

            self._animate("tab_transition_unlock", 300, lambda _amount: None, unlock)

        self.animate_tab_out(current_tab, finish_transition)


    def install_tab_transitions(self):
        """Install a routed tab setter and smooth, moving segmented selection."""
        try:
            self._current_tab_name = self.tabs.get()
            self._tab_transition_running = False
            self._tab_transition_id = 0
            self._tab_transition_overlay = None
            self._queued_tab_target = None

            seg = self.tabs._segmented_button
            buttons = getattr(seg, "_buttons_dict", {})
            if not buttons:
                raise RuntimeError("Segmented button internals unavailable")

            if not hasattr(self, "_tab_transition_original_set"):
                self._tab_transition_original_set = self.tabs.set

            def routed_set(name):
                if not getattr(self, "_tab_transitions_ready", False):
                    return self._tab_transition_original_set(name)
                self._request_tab_transition(name)

            self.tabs.set = routed_set

            for name, button in buttons.items():
                button.configure(
                    command=lambda _value=None, tab_name=name: self._request_tab_transition(tab_name)
                )

            self._tab_transitions_ready = True
        except Exception as exc:
            write_failure_log("tab_transition_install", exc)
            try:
                self.tabs.configure(command=self.on_tab_changed)
            except Exception:
                pass

    @staticmethod
    def _apple_text_tone(color, palette):
        """Map the original widget text color to a semantic role for the active theme."""
        if isinstance(color, (tuple, list)):
            color = color[-1] if color else palette["text"]
        value = str(color or "").strip().lower()
        if not value.startswith("#"):
            return palette["text"]

        value = value[1:]
        if len(value) == 3:
            value = "".join(character * 2 for character in value)
        if len(value) != 6:
            return palette["text"]

        try:
            red = int(value[0:2], 16)
            green = int(value[2:4], 16)
            blue = int(value[4:6], 16)
        except ValueError:
            return palette["text"]

        high = max(red, green, blue)
        low = min(red, green, blue)
        average = (red + green + blue) / 3.0
        if high - low < 48:
            return palette["text"] if average >= 175 else palette["muted"]
        if red > green * 1.28 and red > blue * 1.28:
            return palette["red"]
        if red > 145 and green > 85 and blue < 135 and red > blue * 1.35:
            return palette["orange"]
        if green > red * 1.18 and green > blue * 1.08:
            return palette["green"]
        if blue > red * 1.10 and blue >= green * 0.94:
            return palette["blue"]
        return palette["muted"]


    def update_theme_toggle_button(self):
        button = getattr(self, "theme_toggle_button", None)
        if button is None:
            return
        mode = getattr(self, "appearance_mode", "dark")
        palette = (
            getattr(self, "_apple_theme_transition_palette", None)
            or APPLE_THEME_PALETTES.get(mode, APPLE_THEME_PALETTES["dark"])
        )
        try:
            # The icon shows the mode the user can switch TO.
            button.configure(
                text="☀" if mode == "dark" else "☾",
                fg_color=palette["surface_elevated"],
                hover_color=palette["separator_hover"],
                text_color=palette["text"],
            )
        except Exception:
            pass


    def toggle_appearance_mode(self):
        current = str(getattr(self, "appearance_mode", "dark")).lower()
        target = "light" if current != "light" else "dark"
        self.appearance_mode = target

        try:
            self.save_config()
        except Exception as exc:
            write_failure_log("appearance_mode_save", exc)

        if not self.start_theme_circle_reveal(current, target):
            self.appearance_mode = target
            self.animate_apple_theme_transition(current, target)


    def start_theme_circle_reveal(self, start_mode, target_mode):
        """Reveal a screenshot of the new palette in a circle expanding from the theme button."""
        overlay = None

        try:
            self.update_idletasks()
            origin_x = int(self.winfo_rootx())
            origin_y = int(self.winfo_rooty())
            window_width = max(1, int(self.winfo_width()))
            window_height = max(1, int(self.winfo_height()))
            old_image = ImageGrab.grab(
                bbox=(
                    origin_x,
                    origin_y,
                    origin_x + window_width,
                    origin_y + window_height,
                )
            ).convert("RGB")

            # Keep a still frame above the live window before changing the theme.
            # This prevents the underlying theme swap from flashing on screen.
            overlay = Toplevel(self)
            overlay.overrideredirect(True)
            overlay.geometry(
                f"{old_image.width}x{old_image.height}+{origin_x}+{origin_y}"
            )
            overlay.attributes("-topmost", True)
            canvas = Canvas(
                overlay,
                width=old_image.width,
                height=old_image.height,
                highlightthickness=0,
                bd=0,
                relief="flat",
            )
            canvas.pack(fill="both", expand=True)
            old_photo = ImageTk.PhotoImage(old_image)
            image_item = canvas.create_image(0, 0, anchor="nw", image=old_photo)
            canvas._theme_reveal_photo = old_photo
            overlay._theme_reveal_canvas = canvas
            overlay.lift()
            overlay.update_idletasks()

            self._apple_theme_transition_palette = None
            self.appearance_mode = target_mode
            self.apply_apple_dark_theme()
            self.update_idletasks()

            # The window-specific capture reads the app beneath our still-frame overlay.
            # Pillow versions without this Windows capture API fall back to the color tween.
            target_image = ImageGrab.grab(window=int(self.winfo_id())).convert("RGB")
            if target_image.size != old_image.size:
                target_image = target_image.resize(
                    old_image.size,
                    Image.Resampling.LANCZOS,
                )

            if target_image.getpixel((1, 1)) == old_image.getpixel((1, 1)):
                # A capture of the overlay instead of the real window is not usable.
                raise RuntimeError("Could not capture the updated window independently of the overlay.")

            button = getattr(self, "theme_toggle_button", None)
            if button is not None:
                center_x = (
                    float(button.winfo_rootx())
                    + float(button.winfo_width()) / 2.0
                    - origin_x
                )
                center_y = (
                    float(button.winfo_rooty())
                    + float(button.winfo_height()) / 2.0
                    - origin_y
                )
            else:
                center_x, center_y = old_image.width * 0.5, 24.0

            width, height = old_image.size
            max_radius = max(
                (center_x ** 2 + center_y ** 2) ** 0.5,
                ((width - center_x) ** 2 + center_y ** 2) ** 0.5,
                (center_x ** 2 + (height - center_y) ** 2) ** 0.5,
                ((width - center_x) ** 2 + (height - center_y) ** 2) ** 0.5,
            )

            def render_circle(amount):
                radius = max(1.0, max_radius * amount)
                scale = 2
                mask_hi = Image.new("L", (width * scale, height * scale), 0)
                draw = ImageDraw.Draw(mask_hi)
                draw.ellipse(
                    (
                        round((center_x - radius) * scale),
                        round((center_y - radius) * scale),
                        round((center_x + radius) * scale),
                        round((center_y + radius) * scale),
                    ),
                    fill=255,
                )
                mask = mask_hi.resize(
                    (width, height),
                    Image.Resampling.LANCZOS,
                )
                frame = old_image.copy()
                frame.paste(target_image, (0, 0), mask)
                photo = ImageTk.PhotoImage(frame)
                canvas.itemconfigure(image_item, image=photo)
                canvas._theme_reveal_photo = photo

            def done():
                try:
                    overlay.destroy()
                except Exception:
                    pass
                if getattr(self, "_theme_reveal_overlay", None) is overlay:
                    self._theme_reveal_overlay = None

            self._theme_reveal_overlay = overlay
            self._animate("theme_circle_reveal", 1000, render_circle, done)
            return True

        except Exception as exc:
            if overlay is not None:
                try:
                    overlay.destroy()
                except Exception:
                    pass
            self._theme_reveal_overlay = None
            self.appearance_mode = start_mode
            self._apple_theme_transition_palette = None
            try:
                self.apply_apple_dark_theme()
            except Exception:
                pass
            write_failure_log("theme_circle_reveal_fallback", exc)
            return False


    def animate_apple_theme_transition(self, start_mode, target_mode):
        """Crossfade the full app palette instead of changing themes in one frame."""
        start_palette = dict(
            getattr(self, "_apple_theme_transition_palette", None)
            or APPLE_THEME_PALETTES.get(start_mode, APPLE_THEME_PALETTES["dark"])
        )
        target_palette = APPLE_THEME_PALETTES.get(
            target_mode, APPLE_THEME_PALETTES["dark"]
        )

        def update(amount):
            interpolated = {}
            for key, end_color in target_palette.items():
                start_color = start_palette.get(key, end_color)
                try:
                    interpolated[key] = self._blend_colors(
                        start_color, end_color, amount
                    )
                except Exception:
                    interpolated[key] = end_color
            self._apple_theme_transition_palette = interpolated
            self.apply_apple_dark_theme()

        def done():
            self._apple_theme_transition_palette = None
            self.apply_apple_dark_theme()

        self._animate("apple_theme_transition", 1000, update, done)


    def apply_apple_dark_theme(self):
        """Apply the selected Apple-style light or dark palette across all tabs."""
        mode = str(getattr(self, "appearance_mode", "dark")).strip().lower()
        if mode not in {"dark", "light"}:
            mode = "dark"
            self.appearance_mode = mode
        palette = (
            getattr(self, "_apple_theme_transition_palette", None)
            or APPLE_THEME_PALETTES[mode]
        )

        try:
            requested_ctk_mode = "Light" if mode == "light" else "Dark"
            if str(ctk.get_appearance_mode()).lower() != requested_ctk_mode.lower():
                ctk.set_appearance_mode(requested_ctk_mode)
        except Exception:
            try:
                ctk.set_appearance_mode("Light" if mode == "light" else "Dark")
            except Exception:
                pass

        self.configure(fg_color=palette["root_bg"])
        pages = {id(page) for page in getattr(self, "_apple_tab_pages", [])}

        def walk(widget):
            yield widget
            try:
                children = widget.winfo_children()
            except Exception:
                return
            for child in children:
                yield from walk(child)

        for widget in walk(self):
            try:
                if isinstance(widget, ctk.CTkTabview):
                    widget.configure(
                        fg_color=palette["window_bg"],
                        segmented_button_fg_color=palette["surface"],
                        segmented_button_selected_color=palette["blue"],
                        segmented_button_selected_hover_color=palette["blue_hover"],
                        segmented_button_unselected_color=palette["surface"],
                        segmented_button_unselected_hover_color=palette["surface_elevated"],
                        text_color=palette["text"],
                        corner_radius=20,
                        border_width=1,
                        border_color=palette["separator"],
                    )
                    continue

                if isinstance(widget, ctk.CTkScrollableFrame):
                    widget.configure(
                        fg_color=palette["window_bg"],
                        corner_radius=20,
                        border_width=1,
                        border_color=palette["separator"],
                        scrollbar_button_color=palette["separator_hover"],
                        scrollbar_button_hover_color=palette["muted"],
                    )
                    continue

                if isinstance(widget, ctk.CTkFrame):
                    if not hasattr(widget, "_apple_original_fg_color"):
                        try:
                            widget._apple_original_fg_color = widget.cget("fg_color")
                        except Exception:
                            widget._apple_original_fg_color = "transparent"
                    original_fg = widget._apple_original_fg_color

                    if widget is self.main_container:
                        widget.configure(
                            fg_color=palette["window_bg"],
                            corner_radius=26,
                            border_width=1,
                            border_color=palette["separator"],
                        )
                    elif id(widget) in pages:
                        widget.configure(
                            fg_color=palette["window_bg"],
                            corner_radius=0,
                            border_width=0,
                        )
                    elif widget is getattr(self, "header_card", None):
                        widget.configure(
                            fg_color=palette["surface"],
                            corner_radius=20,
                            border_width=1,
                            border_color=palette["separator"],
                        )
                    elif widget is getattr(self, "brand_badge", None):
                        widget.configure(
                            fg_color=palette["badge_bg"],
                            corner_radius=15,
                            border_width=1,
                            border_color=palette["badge_border"],
                        )
                    elif widget is getattr(self, "brand_accent", None):
                        widget.configure(fg_color=palette["blue"], corner_radius=3)
                    elif str(original_fg).lower() == "transparent":
                        widget.configure(fg_color="transparent")
                    else:
                        try:
                            radius = int(widget.cget("corner_radius"))
                        except Exception:
                            radius = 16
                        widget.configure(
                            fg_color=palette["surface"],
                            corner_radius=22 if radius > 8 else radius,
                        )

                    try:
                        if int(widget.cget("border_width")) > 0:
                            widget.configure(border_color=palette["separator"])
                        widget._apple_theme_base_border = palette["separator"]
                    except Exception:
                        pass

                elif isinstance(widget, ctk.CTkButton):
                    label = str(widget.cget("text") or "").strip().lower()
                    is_theme_button = widget is getattr(self, "theme_toggle_button", None)
                    is_destructive = any(
                        word in label for word in ("stop", "cancel", "delete", "remove")
                    )
                    is_primary = any(
                        word in label for word in (
                            "start", "download", "rewrite", "upgrade", "overhaul",
                            "crop", "apply", "save changes", "process queue", "add playlist",
                        )
                    )

                    if is_theme_button:
                        base, hover = palette["surface_elevated"], palette["separator_hover"]
                        widget.configure(
                            fg_color=base,
                            hover_color=hover,
                            text_color=palette["text"],
                            border_width=1,
                            border_color=palette["separator"],
                            corner_radius=10,
                        )
                    elif is_destructive:
                        base, hover = palette["red"], palette["red_hover"]
                        widget.configure(
                            fg_color=base,
                            hover_color=hover,
                            text_color="#FFFFFF",
                            border_width=0,
                            corner_radius=12,
                        )
                    elif is_primary:
                        base, hover = palette["blue"], palette["blue_hover"]
                        widget.configure(
                            fg_color=base,
                            hover_color=hover,
                            text_color="#FFFFFF",
                            border_width=0,
                            corner_radius=12,
                        )
                    else:
                        base, hover = palette["surface_elevated"], palette["separator_hover"]
                        widget.configure(
                            fg_color=base,
                            hover_color=hover,
                            text_color=palette["text"],
                            border_width=1,
                            border_color=palette["separator"],
                            corner_radius=12,
                        )

                    widget._apple_theme_base_fg = base
                    widget._apple_theme_hover_fg = hover

                elif isinstance(widget, ctk.CTkEntry):
                    widget.configure(
                        fg_color=palette["input_bg"],
                        text_color=palette["text"],
                        placeholder_text_color=palette["muted"],
                        border_width=1,
                        border_color=palette["separator"],
                        corner_radius=12,
                    )
                    widget._apple_theme_base_border = palette["separator"]

                elif isinstance(widget, ctk.CTkComboBox):
                    widget.configure(
                        fg_color=palette["input_bg"],
                        text_color=palette["text"],
                        button_color=palette["surface_elevated"],
                        button_hover_color=palette["separator_hover"],
                        dropdown_fg_color=palette["surface"],
                        dropdown_text_color=palette["text"],
                        border_width=1,
                        border_color=palette["separator"],
                        corner_radius=12,
                    )
                    widget._apple_theme_base_border = palette["separator"]

                elif isinstance(widget, ctk.CTkTextbox):
                    widget.configure(
                        fg_color=palette["console_bg"],
                        text_color=palette["text"],
                        border_width=1,
                        border_color=palette["separator"],
                        corner_radius=14,
                    )
                    widget._apple_theme_base_border = palette["separator"]

                elif isinstance(widget, ctk.CTkProgressBar):
                    widget.configure(
                        fg_color=palette["surface_elevated"],
                        progress_color=palette["blue"],
                        corner_radius=5,
                        height=8,
                    )

                elif isinstance(widget, ctk.CTkCheckBox):
                    widget.configure(
                        text_color=palette["text"],
                        fg_color=palette["blue"],
                        hover_color=palette["blue_hover"],
                        border_color=palette["separator_hover"],
                        checkmark_color="#FFFFFF",
                        corner_radius=5,
                    )

                elif isinstance(widget, ctk.CTkRadioButton):
                    widget.configure(
                        text_color=palette["text"],
                        fg_color=palette["blue"],
                        hover_color=palette["blue_hover"],
                        border_color=palette["separator_hover"],
                    )

                elif isinstance(widget, ctk.CTkSwitch):
                    widget.configure(
                        text_color=palette["text"],
                        progress_color=palette["blue"],
                        button_color=palette["text"],
                        button_hover_color=palette["text"],
                    )

                elif isinstance(widget, ctk.CTkSlider):
                    widget.configure(
                        fg_color=palette["surface_elevated"],
                        progress_color=palette["blue"],
                        button_color=palette["text"],
                        button_hover_color=palette["text"],
                    )

                elif isinstance(widget, ctk.CTkOptionMenu):
                    widget.configure(
                        fg_color=palette["surface_elevated"],
                        button_color=palette["separator_hover"],
                        button_hover_color=palette["separator_hover"],
                        text_color=palette["text"],
                        dropdown_fg_color=palette["surface"],
                        dropdown_text_color=palette["text"],
                    )

                elif isinstance(widget, ctk.CTkLabel):
                    if not hasattr(widget, "_apple_original_text_color"):
                        try:
                            widget._apple_original_text_color = widget.cget("text_color")
                        except Exception:
                            widget._apple_original_text_color = palette["text"]
                    widget.configure(
                        text_color=self._apple_text_tone(
                            widget._apple_original_text_color,
                            palette,
                        )
                    )
                    try:
                        original_fg = getattr(
                            widget,
                            "_apple_original_fg_color",
                            widget.cget("fg_color"),
                        )
                        if not hasattr(widget, "_apple_original_fg_color"):
                            widget._apple_original_fg_color = original_fg
                        if str(original_fg).lower() != "transparent":
                            widget.configure(fg_color=palette["surface_elevated"])
                    except Exception:
                        pass
            except Exception:
                # Theme rendering must never stop an otherwise healthy download.
                pass

        try:
            segmented = self.tabs._segmented_button
            segmented.configure(
                fg_color=palette["surface"],
                selected_color=palette["blue"],
                selected_hover_color=palette["blue_hover"],
                unselected_color=palette["surface"],
                unselected_hover_color=palette["surface_elevated"],
                text_color=palette["text"],
                corner_radius=13,
                border_width=0,
                font=(APP_FONT, 12, "bold"),
            )
        except Exception:
            pass

        self.update_theme_toggle_button()

    def install_transitions(self):
        self.install_tab_transitions()
        self.apply_apple_dark_theme()

        def walk(widget):
            try:
                children = widget.winfo_children()
            except Exception:
                return
            for child in children:
                yield child
                yield from walk(child)

        for widget in walk(self):
            try:
                if isinstance(widget, ctk.CTkButton):
                    self.bind_smooth_button(widget)
                elif isinstance(widget, ctk.CTkFrame):
                    self.bind_card_glow(widget)

                if isinstance(widget, (ctk.CTkEntry, ctk.CTkComboBox, ctk.CTkTextbox)):
                    self.bind_focus_glow(widget)
            except Exception:
                pass

        # The first launch uses the window entrance animation. Tab content
        # motion begins only when the user actually changes tabs.
        try:
            self.bind("<Unmap>", self.remember_window_minimize, add="+")
            self.bind("<Map>", self.animate_window_restore, add="+")
        except Exception:
            pass

        self.set_header_status("● READY", busy=False)
        self.pulse_header_status()

    # --------------------------------------------------------
    # DOWNLOADER TAB
    # --------------------------------------------------------

    def build_downloader_tab(self, tab):
        # The downloader tab is entirely grid-managed. Build it directly
        # so no temporary pack-managed widgets are created and destroyed.
        self._build_downloader_tab_grid(tab)

    def _build_downloader_tab_grid(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(4, weight=0)

        target = ctk.CTkFrame(
            tab,
            fg_color="#000000",
            corner_radius=24,
            border_width=1,
            border_color=APPLE_THEME_PALETTES.get(
                getattr(self, "appearance_mode", "dark"),
                APPLE_THEME_PALETTES["dark"],
            )["separator"],
        )
        target.grid(
            row=0,
            column=0,
            padx=18,
            pady=7,
            sticky="ew",
        )
        target.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            target,
            text=" Target URL",
            font=(APP_FONT, 15, "bold"),
            text_color="#ffffff",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=22,
            pady=(16, 2),
        )

        self.dl_input_var = StringVar(value="")
        self.dl_input_var.trace_add("write", self.on_downloader_target_changed)

        self.dl_input = ctk.CTkEntry(
            target,
            placeholder_text="Paste Target URL Here...",
            height=44,
            font=(APP_FONT, 14),
            fg_color="#050505",
            text_color="#ffffff",
            placeholder_text_color="#777777",
            border_width=0,
            corner_radius=8,
            textvariable=self.dl_input_var,
        )
        self.dl_input.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 16),
        )
        options = ctk.CTkFrame(
            tab,
            fg_color="#000000",
            corner_radius=24,
            border_width=1,
            border_color=APPLE_THEME_PALETTES.get(
                getattr(self, "appearance_mode", "dark"),
                APPLE_THEME_PALETTES["dark"],
            )["separator"],
        )
        options.grid(
            row=1,
            column=0,
            padx=18,
            pady=7,
            sticky="ew",
        )
        options.grid_columnconfigure(0, weight=1)

        self.dl_quality_label = ctk.CTkLabel(
            options,
            text=" Download Quality",
            font=(APP_FONT, 15, "bold"),
            text_color="#ffffff",
        )

        self.dl_format = ctk.CTkComboBox(
            options,
            values=[label for label, _spec in AUDIO_DOWNLOAD_OPTIONS],
            state="readonly",
            fg_color="#050505",
            text_color="#ffffff",
            button_color="#1e293b",
            button_hover_color="#334155",
            dropdown_fg_color="#000000",
            dropdown_text_color="#ffffff",
            corner_radius=8,
            font=(APP_FONT, 14),
            dropdown_font=(APP_FONT, 14),
            height=42,
        )
        self.dl_format.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 8),
        )
        self.hide_download_quality_selector()

        checks = ctk.CTkFrame(
            options,
            fg_color="transparent",
        )
        checks.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 8),
        )
        checks.grid_columnconfigure(0, weight=1)

        self.dl_subs = ctk.BooleanVar(value=False)

        ctk.CTkCheckBox(
            checks,
            text="Embed Subtitles EN / AR",
            variable=self.dl_subs,
            font=(APP_FONT, 12),
            text_color="#ffffff",
            border_width=1,
            corner_radius=4,
        ).grid(
            row=0,
            column=0,
            sticky="w",
        )

        ctk.CTkLabel(
            checks,
            text="",
            font=(APP_FONT, 11),
            text_color="#94a3b8",
        ).grid(
            row=0,
            column=1,
            sticky="e",
        )


        self.dl_path_row, self.dl_path_label = self.make_path_row(
            options,
            "downloader",
        )
        self.dl_path_row.grid(
            row=5,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 14),
        )

        preview = ctk.CTkFrame(
            tab,
            fg_color="#000000",
            corner_radius=24,
            border_width=1,
            border_color=APPLE_THEME_PALETTES.get(
                getattr(self, "appearance_mode", "dark"),
                APPLE_THEME_PALETTES["dark"],
            )["separator"],
        )
        preview.grid(
            row=2,
            column=0,
            padx=18,
            pady=7,
            sticky="ew",
        )
        preview.grid_propagate(False)
        preview.grid_columnconfigure(1, weight=1)
        self.dl_preview_card = preview

        self.dl_cover = ctk.CTkLabel(
            preview,
            text="NO\nCOVER",
            width=96,
            height=96,
            fg_color="#050505",
            corner_radius=10,
            font=(APP_FONT, 10, "bold"),
            text_color="#4b5563",
        )
        self.dl_cover.grid(
            row=0,
            column=0,
            rowspan=3,
            padx=16,
            pady=16,
        )

        self.dl_title = ctk.CTkLabel(
            preview,
            text="Waiting For Target URL...",
            font=(APP_FONT, 15, "bold"),
            text_color="#ffffff",
            anchor="w",
        )
        self.dl_title.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(0, 16),
            pady=(18, 4),
        )

        self.dl_artist = ctk.CTkLabel(
            preview,
            text="",
            font=(APP_FONT, 11),
            text_color="#9ca3af",
            anchor="w",
        )
        self.dl_artist.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(0, 16),
        )

        self.dl_status = ctk.CTkLabel(
            preview,
            text="Status: Inactive",
            font=(APP_FONT, 12),
            text_color="#ffffff",
            anchor="w",
        )
        self.dl_status.grid(
            row=2,
            column=1,
            sticky="ew",
            padx=(0, 16),
            pady=(4, 18),
        )

        self.dl_progress = ctk.CTkProgressBar(
            preview,
            height=12,
            corner_radius=6,
            fg_color="#050505",
            progress_color="#ffffff",
        )
        self.dl_progress.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(0, 16),
        )
        self.dl_progress.set(0)

        progress_info = ctk.CTkFrame(
            preview,
            fg_color="transparent",
        )
        progress_info.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(0, 12),
        )
        progress_info.grid_columnconfigure(0, weight=1)

        self.dl_progress_message = ctk.CTkLabel(
            progress_info,
            text="Waiting for download...",
            font=(APP_FONT, 10, "bold"),
            text_color="#94a3b8",
            anchor="w",
        )
        self.dl_progress_message.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        self.dl_progress_percent = ctk.CTkLabel(
            progress_info,
            text="0%",
            font=(APP_FONT, 10, "bold"),
            text_color="#64748b",
            anchor="e",
        )
        self.dl_progress_percent.grid(
            row=0,
            column=1,
            padx=(10, 0),
        )

        self.dl_progress_info = progress_info
        self.dl_progress.grid_remove()
        self.dl_progress_info.grid_remove()

        controls = ctk.CTkFrame(
            tab,
            fg_color="transparent",
        )
        controls.grid(
            row=3,
            column=0,
            padx=18,
            pady=(7, 4),
            sticky="ew",
        )
        controls.grid_columnconfigure(
            (0, 1, 2),
            weight=1,
        )

        self.dl_start = ctk.CTkButton(
            controls,
            text=" Start Download",
            command=self.start_download,
            fg_color="transparent",
            hover_color="#1e293b",
            text_color="#ffffff",
            font=(APP_FONT, 14, "bold"),
            height=42,
            corner_radius=8,
        )
        self.dl_start.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
        )

        self.dl_pause = ctk.CTkButton(
            controls,
            text=" Pause",
            command=self.toggle_pause,
            fg_color="transparent",
            hover_color="#1e293b",
            text_color="#ffffff",
            font=(APP_FONT, 13, "bold"),
            height=42,
            corner_radius=8,
            state="disabled",
        )
        self.dl_pause.grid_remove()

        self.dl_resume = ctk.CTkButton(
            controls,
            text=" Resume",
            command=self.toggle_pause,
            fg_color="transparent",
            hover_color="#1e293b",
            text_color="#ffffff",
            font=(APP_FONT, 13, "bold"),
            height=42,
            corner_radius=8,
            state="disabled",
        )

        self.dl_stop = ctk.CTkButton(
            controls,
            text=" Stop",
            command=self.stop_active_process,
            fg_color="transparent",
            hover_color="#1e293b",
            text_color="#ffffff",
            font=(APP_FONT, 13, "bold"),
            height=42,
            corner_radius=8,
            state="disabled",
        )
        self.dl_stop.grid_remove()

        # Downloader deliberately has no visible terminal/activity console.
        # Internal log calls use this null sink; permanent failure diagnostics
        # are still written to Documents\YTDLP.
        self.dl_log = None

    # --------------------------------------------------------
    # DOWNLOADER LOGIC
    # --------------------------------------------------------

    def downloader_quality_mode_for_source(self, source):
        """Return an explicit quality-menu mode derived only from the current URL."""
        source = str(source or "").strip()
        if not source or not is_youtube_url(source):
            return "none"
        return "playlist" if is_playlist_url(source) else "single"

    @staticmethod
    def sanitize_quality_options_for_mode(quality_options, mode):
        """Prevent playlist-only quality specs from ever leaking into single-video mode."""
        options = []
        seen = set()

        for label, spec in list(quality_options or []):
            if not isinstance(spec, dict):
                continue

            if mode == "single" and spec.get("best_per_item"):
                continue

            if mode == "single" and str(label).strip() == "Best Quality Separate":
                continue

            key = str(label)
            if key in seen:
                continue
            seen.add(key)
            options.append((key, dict(spec)))

        return options

    def hide_download_quality_selector(self):
        self._dl_quality_visible = False
        self._dl_preview_quality_options = []
        self._dl_preview_quality_source = ""
        self._dl_preview_mode = "none"
        self._dl_preview_is_playlist = False
        self._selected_download_format = ""
        self._dl_youtube_extractor_arg = None
        try:
            self.dl_quality_label.grid_remove()
            self.dl_format.grid_remove()
            self.dl_format.configure(values=[])
            self.dl_format.set("")
        except Exception:
            pass

    def show_download_quality_selector(self, quality_options, animated=True, source_value="", source_mode=None):
        """Reveal only qualities valid for the exact current source mode."""
        source_value = str(source_value or self._dl_preview_source or "").strip()
        detected_mode = self.downloader_quality_mode_for_source(source_value)

        # The URL itself is the single source of truth. Never allow a stale
        # playlist mode passed by an older callback/state to override it.
        mode = detected_mode
        if source_mode and source_mode != detected_mode:
            mode = detected_mode

        if mode == "playlist":
            # Keep only playlist resolutions gathered from its per-video scan.
            options = self.sanitize_quality_options_for_mode(quality_options, "playlist")
        elif mode == "single":
            options = self.sanitize_quality_options_for_mode(quality_options, "single")
        else:
            options = []

        if not options:
            self.hide_download_quality_selector()
            return

        self._dl_preview_mode = mode
        self._dl_preview_is_playlist = mode == "playlist"
        self._dl_preview_quality_options = options
        self._dl_preview_quality_source = source_value

        values = [label for label, _spec in options]
        if not values:
            self.hide_download_quality_selector()
            return

        best_value = values[0]

        try:
            self.dl_format.configure(values=values)
            self.dl_quality_label.grid(
                row=0,
                column=0,
                sticky="w",
                padx=22,
                pady=(14, 4),
            )
            self.dl_format.grid(
                row=1,
                column=0,
                sticky="ew",
                padx=22,
                pady=(0, 8),
            )
            self.dl_format.set(best_value)
            self._dl_quality_visible = True
        except Exception:
            return

        if not animated:
            return

        try:
            self.dl_quality_label.configure(text_color="#334155")
            self.dl_format.configure(
                text_color="#334155",
                button_color="#0b1220",
                button_hover_color="#0b1220",
            )
        except Exception:
            pass

        def update(amount):
            try:
                bright = self._blend_colors("#334155", "#ffffff", amount)
                self.dl_quality_label.configure(text_color=bright)
                combo_text = self._blend_colors("#334155", "#ffffff", amount)
                combo_button = self._blend_colors("#0b1220", "#1e293b", amount)
                self.dl_format.configure(
                    text_color=combo_text,
                    button_color=combo_button,
                    button_hover_color=combo_button,
                )
            except Exception:
                pass

        def done():
            try:
                self.dl_quality_label.configure(text_color="#ffffff")
                self.dl_format.configure(
                    text_color="#ffffff",
                    button_color="#1e293b",
                    button_hover_color="#334155",
                )
            except Exception:
                pass

        self._animate(
            "download-quality-selector-in",
            360,
            update,
            done,
        )

    def show_downloader_activity_ui(self):
        """Reveal the download meter and running controls; hide Start Download."""
        try:
            self.dl_start.grid_remove()
            self.dl_progress.grid(
                row=3,
                column=0,
                columnspan=2,
                sticky="ew",
                padx=16,
                pady=(0, 16),
            )
            self.dl_progress_info.grid(
                row=4,
                column=0,
                columnspan=2,
                sticky="ew",
                padx=16,
                pady=(0, 12),
            )
            self.dl_pause.grid(
                row=0,
                column=1,
                sticky="ew",
                padx=4,
            )
            self.dl_stop.grid(
                row=0,
                column=2,
                sticky="ew",
                padx=(4, 0),
            )

            self.dl_pause.configure(
                state="normal",
                text_color="#334155",
            )
            self.dl_stop.configure(
                state="normal",
                text_color="#334155",
            )

            def update(amount):
                color = self._blend_colors("#334155", "#ffffff", amount)
                try:
                    self.dl_pause.configure(text_color=color)
                    self.dl_stop.configure(text_color=color)
                    self.dl_progress.configure(
                        progress_color=self._blend_colors("#0b1220", "#38bdf8", amount)
                    )
                except Exception:
                    pass

            def done():
                try:
                    self.dl_pause.configure(text_color="#ffffff")
                    self.dl_stop.configure(text_color="#ffffff")
                    self.dl_progress.configure(progress_color="#38bdf8")
                except Exception:
                    pass

            self._animate(
                "downloader-activity-in",
                360,
                update,
                done,
            )
        except Exception:
            pass

    def hide_downloader_running_controls(self):
        try:
            self.dl_pause.grid_remove()
            self.dl_resume.grid_remove()
            self.dl_stop.grid_remove()
            self.dl_start.grid(
                row=0,
                column=0,
                columnspan=3,
                sticky="ew",
            )
        except Exception:
            pass

    def selected_quality_spec(self, selected_format):
        if isinstance(selected_format, dict):
            return dict(selected_format)

        for label, spec in self._dl_preview_quality_options or []:
            if label == selected_format:
                return dict(spec)
        return {}

    def on_downloader_target_changed(self, *_args):
        """Invalidate everything on every character change and silently rebuild the source preview."""
        try:
            current_value = self.dl_input.get()
            self._dl_preview_token += 1
            token = self._dl_preview_token

            if self._dl_preview_job:
                try:
                    self.after_cancel(self._dl_preview_job)
                except Exception:
                    pass
                self._dl_preview_job = None

            self._stop_loading_preview()
            self._dl_preview_source = current_value
            self._selected_download_format = ""
            self.hide_download_quality_selector()
            self._dl_preview_mode = self.downloader_quality_mode_for_source(current_value)
            self._clear_downloader_preview_visuals()

            if not self.download_running:
                try:
                    self.dl_progress.grid_remove()
                    self.dl_progress_info.grid_remove()
                except Exception:
                    pass

            value = current_value.strip()
            if not is_youtube_url(value):
                return

            self._dl_preview_job = self.after(
                180,
                lambda: self._start_silent_link_preview(token),
            )
        except Exception:
            pass

    def on_downloader_paste_preview(self, _event=None):
        """Backward-compatible wrapper for older bindings."""
        self.on_downloader_target_changed()

    def _clear_downloader_preview_visuals(self):
        try:
            self._dl_preview_pil = None
            self._dl_preview_target_size = (96, 96)
            self._dl_preview_mode = "none"
            self._dl_preview_is_playlist = False
            self._dl_playlist_cover_bytes = None
            self._dl_youtube_extractor_arg = None
            self.cover_preview_image = None

            self.dl_cover.configure(
                image="",
                text="NO\nCOVER",
                width=96,
                height=96,
            )
            self.dl_title.configure(
                text="Waiting For Target URL...",
                text_color="#ffffff",
            )
            self.dl_artist.configure(
                text="",
                text_color="#9ca3af",
            )
        except Exception:
            pass





    def _animate_loading_preview(self, token, frame=0):
        if token != self._dl_preview_token or self.download_running:
            return

        states = (
            "Loading Preview...",
            "Loading Preview..",
            "Loading Preview.",
            "Loading Preview..",
        )

        try:
            self.dl_title.configure(
                text=states[frame % len(states)],
                text_color="#ffffff",
            )
            self.dl_artist.configure(text="", text_color="#475569")
            self.dl_status.configure(text_color="#475569")
        except Exception:
            return

        self._dl_preview_loading_job = self.after(260, lambda: self._animate_loading_preview(token, frame + 1))

    def _stop_loading_preview(self):
        if self._dl_preview_loading_job:
            try:
                self.after_cancel(self._dl_preview_loading_job)
            except Exception:
                pass
        self._dl_preview_loading_job = None

    def _start_silent_link_preview(self, token):
        self._dl_preview_job = None

        if token != self._dl_preview_token or self.download_running:
            return

        user_input = self.dl_input.get().strip()
        if not is_youtube_url(user_input):
            self._stop_loading_preview()
            return

        self._dl_preview_source = user_input
        self.hide_download_quality_selector()
        self._dl_preview_mode = self.downloader_quality_mode_for_source(user_input)
        self._stop_loading_preview()
        self._animate_loading_preview(token, 0)

        threading.Thread(
            target=self._silent_link_preview_worker,
            args=(user_input, token),
            daemon=True,
        ).start()


    def _silent_link_preview_worker(self, user_input, token):
        preview = YTMResolver.preview_from_url(
            user_input,
        )

        if not preview:
            def preview_failed():
                if token != self._dl_preview_token or self.download_running:
                    return
                self._stop_loading_preview()
                self.hide_download_quality_selector()
                self.dl_title.configure(
                    text="Preview Unavailable",
                    text_color="#ffffff",
                )
                self.dl_artist.configure(
                    text="Check Documents\\YTDLP for the preview error log.",
                    text_color="#9ca3af",
                )
                self.dl_status.configure(
                    text="Status: Preview failed — see the latest silent_preview log."
                )
                self._dl_preview_pil = None
                self._dl_preview_target_size = (96, 96)
                self.dl_cover.configure(
                    image="",
                    text="NO\nCOVER",
                    width=96,
                    height=96,
                )

            self.after(0, preview_failed)
            return

        cover_bytes = None
        cover_url = preview.get("cover_url") or ""
        candidates = []

        if cover_url:
            candidates.append(cover_url)

        for candidate in preview.get("thumbnail_candidates", []) or []:
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        for candidate in candidates:
            cover_bytes, _, _ = inspect_image_from_url(candidate)
            if cover_bytes:
                preview["cover_url"] = candidate
                break

        preview["cover_bytes"] = cover_bytes

        def apply_preview():
            try:
                if token != self._dl_preview_token:
                    return
                if self.download_running:
                    return
                if self.dl_input.get().strip() != user_input:
                    return

                self.apply_silent_link_preview(preview)
            except Exception as exc:
                write_failure_log(
                    "apply_preview",
                    exc,
                    details=f"URL: {user_input}",
                )

        self.after(0, apply_preview)


    def apply_silent_link_preview(self, preview):
        self._stop_loading_preview()

        title = preview.get("title") or "Unknown YouTube Video"
        cover_bytes = preview.get("cover_bytes")
        source = self._dl_preview_source.strip()
        mode = self.downloader_quality_mode_for_source(source)
        self._dl_preview_mode = mode
        self._dl_preview_is_playlist = mode == "playlist"
        self._dl_playlist_cover_bytes = cover_bytes if self._dl_preview_is_playlist else None
        self._dl_preview_quality_source = source
        self._dl_youtube_extractor_arg = preview.get("youtube_extractor_arg")

        display_title = title
        if len(display_title) > 64:
            display_title = display_title[:61] + "..."

        self.dl_title.configure(
            text=display_title,
        )
        self.dl_artist.configure(
            text="",
            text_color="#9ca3af",
        )

        if cover_bytes:
            self._prepare_preview_image(cover_bytes)
        else:
            self._dl_preview_pil = None
            self._dl_preview_target_size = (96, 96)
            self.dl_cover.configure(
                image="",
                text="NO\nCOVER",
                width=96,
                height=96,
            )

        quality_options = preview.get("quality_options") or []
        if mode == "playlist":
            self.dl_status.configure(
                text=f"Status: {preview.get('quality_summary') or 'Playlist quality scan complete'}"
            )
        elif mode == "single":
            quality_options = self.sanitize_quality_options_for_mode(quality_options, "single")

        if quality_options and mode in {"playlist", "single"}:
            self.show_download_quality_selector(
                quality_options,
                animated=True,
                source_value=source,
                source_mode=mode,
            )
        else:
            self.hide_download_quality_selector()

        self._animate_downloader_preview_reveal()


    def _prepare_preview_image(self, image_bytes):
        """Prepare artwork/thumbnail at its natural aspect ratio.

        Square album artwork stays square, while normal YouTube thumbnails
        keep their wide 16:9 (or other source) shape instead of being forced
        into a square. The displayed image is bounded so the preview card
        remains compact regardless of the source dimensions.
        """
        try:
            image = Image.open(BytesIO(image_bytes))
            image = ImageOps.exif_transpose(image).convert("RGB")

            width, height = image.size
            if width <= 0 or height <= 0:
                raise ValueError("Invalid preview image dimensions")

            self._dl_preview_pil = image.copy()

            # Dynamic display bounds. These preserve the original aspect
            # ratio while keeping the preview compact inside the card.
            max_width = 180
            max_height = 120

            scale = min(
                max_width / width,
                max_height / height,
                1.0,
            )

            target_width = max(1, round(width * scale))
            target_height = max(1, round(height * scale))

            self._dl_preview_target_size = (
                target_width,
                target_height,
            )

            preview_image = image.copy()
            preview_image.thumbnail(
                (target_width, target_height),
                Image.Resampling.LANCZOS,
            )

            preview = ctk.CTkImage(
                light_image=preview_image,
                dark_image=preview_image,
                size=(target_width, target_height),
            )

            self.cover_preview_image = preview
            self.dl_cover.configure(
                image=preview,
                text="",
                width=target_width,
                height=target_height,
            )
        except Exception:
            self._dl_preview_pil = None
            self._dl_preview_target_size = (96, 96)
            self.dl_cover.configure(
                image="",
                text="NO\nCOVER",
                width=96,
                height=96,
            )

    def _animate_downloader_preview_reveal(self):
        """Drop the preview content in while fading its text toward full contrast."""
        title = self.dl_title
        artist = self.dl_artist
        status = self.dl_status
        cover = self.dl_cover
        card = self.dl_preview_card
        base_image = self._dl_preview_pil.copy() if self._dl_preview_pil is not None else None
        target_width, target_height = self._dl_preview_target_size

        # Start slightly above the final position and nearly transparent.
        title.configure(text_color="#334155")
        artist.configure(text_color="#334155")
        status.configure(text_color="#334155")
        title.grid_configure(pady=(0, 4))
        artist.grid_configure(pady=(0, 0))
        status.grid_configure(pady=(0, 4))
        cover.grid_configure(pady=(0, 16))

        def update(amount):
            title.configure(
                text_color=self._blend_colors("#334155", "#ffffff", amount)
            )
            artist.configure(
                text_color=self._blend_colors("#334155", "#9ca3af", amount)
            )
            status.configure(
                text_color=self._blend_colors("#334155", "#ffffff", amount)
            )

            top_title = round(0 + (18 * amount))
            title.grid_configure(pady=(top_title, 4))
            cover_top = round(0 + (16 * amount))
            cover.grid_configure(pady=(cover_top, 16))
            status_top = round(0 + (4 * amount))
            status.grid_configure(pady=(status_top, 18))

            if base_image is not None:
                # Animate toward the dynamically calculated target size
                # while preserving the source aspect ratio.
                start_width = max(1, round(target_width * 0.55))
                start_height = max(1, round(target_height * 0.55))
                current_width = max(1, round(start_width + ((target_width - start_width) * amount)))
                current_height = max(1, round(start_height + ((target_height - start_height) * amount)))

                image = base_image.copy()
                image.thumbnail(
                    (current_width, current_height),
                    Image.Resampling.LANCZOS,
                )

                frame = ctk.CTkImage(
                    light_image=image,
                    dark_image=image,
                    size=(current_width, current_height),
                )
                self.cover_preview_image = frame
                cover.configure(
                    image=frame,
                    text="",
                    width=current_width,
                    height=current_height,
                )

        def done():
            try:
                title.configure(text_color="#ffffff")
                artist.configure(text_color="#9ca3af")
                status.configure(text_color="#ffffff")
                title.grid_configure(pady=(18, 4))
                status.grid_configure(pady=(4, 18))
                cover.grid_configure(pady=16)
                cover.configure(
                    width=target_width,
                    height=target_height,
                )
                card.configure(
                    border_color=APPLE_THEME_PALETTES.get(
                        getattr(self, "appearance_mode", "dark"),
                        APPLE_THEME_PALETTES["dark"],
                    )["separator"]
                )
            except Exception:
                pass

        try:
            self.animate_widget_color(
                card,
                "border_color",
                card.cget("border_color"),
                "#1e4f73",
                220,
                APPLE_THEME_PALETTES.get(
                    getattr(self, "appearance_mode", "dark"),
                    APPLE_THEME_PALETTES["dark"],
                )["separator"],
            )
        except Exception:
            pass

        self._animate(
            "downloader_preview_reveal",
            360,
            update,
            done,
        )

    def update_downloader_preview(self, result):
        artist = result.get("artist") or "[Unknown Artist]"
        title = result.get("title") or "[Unknown Title]"
        album = result.get("album") or ""

        display_title = title
        if len(display_title) > 48:
            display_title = display_title[:45] + "..."

        self.dl_title.configure(
            text=display_title,
        )
        self.dl_artist.configure(
            text=f"{artist}  •  {album}" if album else artist,
        )

        cover_url = result.get("cover_url") or ""
        thumbnail_candidates = result.get("thumbnail_candidates") or []

        if cover_url:
            self.after(
                0,
                lambda url=cover_url: self.load_downloader_cover(url),
            )
        elif thumbnail_candidates:
            self.after(
                0,
                lambda url=thumbnail_candidates[0]: self.load_downloader_cover(url),
            )
        elif self._dl_preview_is_playlist and self._dl_playlist_cover_bytes:
            self.after(
                0,
                lambda data=self._dl_playlist_cover_bytes: (
                    self._prepare_preview_image(data),
                    self._animate_downloader_preview_reveal(),
                ),
            )
        else:
            # No artwork to load, so still reveal the matched metadata.
            self.after(0, self._animate_downloader_preview_reveal)

    def load_downloader_cover(self, url):
        try:
            data, _, _ = inspect_image_from_url(url)

            if not data:
                return

            self._prepare_preview_image(data)
            self._animate_downloader_preview_reveal()
        except Exception:
            self.dl_cover.configure(
                image="",
                text="NO\nCOVER",
            )

    def start_download(self):
        if self.download_running:
            return

        user_input = self.dl_input.get().strip()

        if not user_input:
            messagebox.showerror(
                "Error",
                "Enter a search query or YouTube / YT Music link.",
            )
            return

        if user_input.startswith("http") and not is_youtube_url(user_input):
            messagebox.showerror(
                "Error",
                "Only YouTube and YouTube Music links are supported.",
            )
            return

        current_source = user_input.strip()
        source_mode = self.downloader_quality_mode_for_source(current_source)
        quality_matches_source = (
            self._dl_quality_visible
            and self._dl_preview_quality_source == current_source
            and self._dl_preview_mode == source_mode
        )
        selected = self.dl_format.get().strip() if quality_matches_source else ""

        if source_mode == "single" and selected == "Best Quality Separate":
            selected = ""

        if source_mode == "single" and selected:
            valid_labels = {label for label, _spec in self.sanitize_quality_options_for_mode(self._dl_preview_quality_options, "single")}
            if selected not in valid_labels:
                selected = ""

        if not selected:
            # The worker will inspect the exact current single-video source and choose its first option.
            # For playlists, this is the special per-item mode.
            selected = "Best Quality Separate" if source_mode == "playlist" else " Best Quality"

        self._selected_download_format = selected
        self._selected_download_subtitles = bool(self.dl_subs.get())

        self.prepare_downloader_ui()
        self.show_downloader_activity_ui()
        self.set_operation_progress(
            "dl",
            0,
            "Preparing download...",
            taskbar=True,
        )
        self.set_header_status("● DOWNLOADING", busy=True)
        self.download_running = True
        self.stop_requested = False

        threading.Thread(
            target=self.run_download_worker,
            args=(user_input,),
            daemon=True,
        ).start()


    def prepare_downloader_ui(self):
        self.dl_start.configure(
            state="disabled",
            text=" Processing...",
        )

        self.dl_progress.set(0)
        self.dl_progress_percent.configure(text="0%")
        self.set_operation_progress(
            "dl",
            0,
            "Preparing download...",
            taskbar=True,
        )

        user_input = self.dl_input.get().strip()
        uses_ytm_matching = (
            not is_youtube_url(user_input)
            or is_youtube_music_url(user_input)
        )

        self.set_label(
            self.dl_title,
            (
                "Resolving YouTube Music result..."
                if uses_ytm_matching
                else "Reading YouTube source..."
            ),
        )
        self.set_label(self.dl_artist, "")
        self.set_label(
            self.dl_status,
            (
                "Status: Songs filter → exact artist match"
                if uses_ytm_matching
                else "Status: Direct YouTube download — YTM matching skipped"
            ),
        )

        self.append_log(
            self.dl_log,
            "============================================================",
        )
        self.append_log(
            self.dl_log,
            f"INPUT: {self.dl_input.get().strip()}",
        )


    def resolve_quality_options_for_result(self, result):
        """Inspect a resolved source, retrying YouTube clients when capped at 360p."""
        video_id = result.get("video_id") if result else ""
        if not video_id:
            return []

        source_url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            preferred_strategy = (
                LIKED_MUSIC_EXTRACTOR_ARG
                if result.get("ytmusic_liked_entry")
                else None
            )
            formats, extractor_arg = inspect_youtube_formats(
                source_url,
                timeout=30,
                preferred_strategy=preferred_strategy,
            )
            self._last_quality_extractor_arg = extractor_arg
            return combine_quality_options(formats)
        except Exception as exc:
            self._last_quality_extractor_arg = None
            write_failure_log(
                "download_quality_inspection",
                exc,
                details=f"Source: {source_url}",
            )
            return []


    def resolve_for_download(self, user_input):
        resolver = self.ensure_resolver()

        if is_youtube_url(user_input):
            if is_playlist_url(user_input):
                urls = resolver.resolve_playlist_urls(
                    user_input,
                )
                return "playlist", (
                    urls,
                    is_youtube_music_url(user_input),
                )

            result, error = resolver.resolve_input(
                user_input,
            )
            return "single", (result, error)

        result, error = resolver.resolve_input(
            user_input,
        )
        return "single", (result, error)

    def is_lossless_video_mode(self, selected_format):
        spec = self.selected_quality_spec(selected_format)
        if not spec or spec.get("kind") != "video":
            return False

        try:
            return int(spec.get("height") or 0) >= 1080
        except (TypeError, ValueError):
            return False


    def run_ytdlp_logged(
        self,
        command,
        stage_name,
        output_dir,
        progress_start=0.0,
        progress_end=1.0,
    ):
        if self.stop_requested:
            raise DownloadCancelled("Download stopped by user.")

        self.set_operation_progress(
            "dl",
            progress_start * 100.0,
            f"{stage_name.title()} — preparing...",
            taskbar=True,
        )
        self.append_log(
            self.dl_log,
            f"[{stage_name}] starting...",
        )

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **get_hidden_subprocess_kwargs(),
            )
            self.active_process = process
        except Exception as exc:
            self.active_process = None
            log_path = write_failure_log(
                f"download_{stage_name}",
                exc,
                details="Failed to start yt-dlp subprocess.",
            )
            raise RuntimeError(
                f"Could not start {stage_name}. Failure log: {log_path or FAILURE_LOG_DIR}"
            ) from exc

        output_lines = []
        output_queue = Queue()

        def read_process_output():
            try:
                for output_line in process.stdout:
                    output_queue.put(output_line)
            except Exception as reader_exc:
                output_queue.put(f"[toolkit output reader warning] {reader_exc}\n")
            finally:
                output_queue.put(None)

        reader_thread = threading.Thread(
            target=read_process_output,
            daemon=True,
        )
        reader_thread.start()

        output_finished = False
        terminate_requested_at = None
        kill_sent = False
        last_logged_progress = None

        while not output_finished:
            if self.stop_requested and process.poll() is None:
                if terminate_requested_at is None:
                    terminate_requested_at = time.monotonic()
                    try:
                        process.terminate()
                    except Exception:
                        pass
                elif (
                    not kill_sent
                    and time.monotonic() - terminate_requested_at >= 2.0
                ):
                    kill_sent = True
                    try:
                        process.kill()
                    except Exception:
                        pass

            try:
                line = output_queue.get(timeout=0.2)
            except Empty:
                if process.poll() is not None and not reader_thread.is_alive():
                    break
                continue

            if line is None:
                output_finished = True
                continue

            clean_line = line.strip()
            if not clean_line:
                continue

            output_lines.append(clean_line)
            lower_line = clean_line.lower()
            should_log_line = len(output_lines) <= 20

            match = re.search(r"(\d+(?:\.\d+)?)%", clean_line)
            if match:
                percent = max(0.0, min(100.0, float(match.group(1))))
                overall = progress_start + (progress_end - progress_start) * (percent / 100.0)
                self.set_operation_progress(
                    "dl",
                    overall * 100.0,
                    f"{stage_name.title()} — downloading...",
                    taskbar=True,
                )
                if (
                    last_logged_progress is None
                    or percent >= last_logged_progress + 1.0
                    or percent >= 100.0
                ):
                    should_log_line = True
                    last_logged_progress = percent

            if any(marker in lower_line for marker in (
                "error", "warning", "retry", "403", "429", "forbidden",
                "timed out", "timeout", "http error", "traceback",
            )):
                should_log_line = True

            if should_log_line:
                self.append_log(self.dl_log, clean_line)

        return_code = process.wait()
        self.active_process = None

        if self.stop_requested:
            raise DownloadCancelled("Download stopped by user.")

        if return_code != 0:
            aria2_failed = any("aria2c" in line.lower() for line in output_lines)
            fallback_command = (
                build_native_ytdlp_fallback_command(
                    command,
                    getattr(self, "performance_mode", "aggressive"),
                )
                if aria2_failed
                else None
            )

            if fallback_command:
                self.append_log(
                    self.dl_log,
                    "[speed fallback] aria2c failed; retrying once with yt-dlp's native downloader...",
                )
                return self.run_ytdlp_logged(
                    fallback_command,
                    f"{stage_name} (native fallback)",
                    output_dir,
                    progress_start=progress_start,
                    progress_end=progress_end,
                )

            log_path = write_failure_log(
                f"download_{stage_name}",
                RuntimeError(f"yt-dlp exit code {return_code}"),
                details="\n".join(output_lines),
            )
            raise RuntimeError(
                f"{stage_name} failed. Failure log: {log_path or FAILURE_LOG_DIR}"
            )

        self.set_operation_progress(
            "dl",
            progress_end * 100.0,
            f"{stage_name.title()} complete",
            taskbar=True,
        )
        return output_lines


    def strip_audio_from_video(self, video_path, silent_output_path, progress_start=0.0, progress_end=1.0):
        """Copy only the video stream into a new container, guaranteeing no audio remains."""
        if self.stop_requested:
            raise DownloadCancelled("Download stopped by user.")

        ffmpeg = get_ffmpeg_command()
        input_path = Path(video_path)
        output_path = Path(silent_output_path)

        if not input_path.exists():
            raise RuntimeError(f"Temporary video was not found: {input_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        command = [
            ffmpeg,
            "-y",
            "-i",
            str(input_path),
            "-map",
            "0:v:0",
            "-an",
            "-c:v",
            "copy",
            "-map_metadata",
            "-1",
            str(output_path),
        ]

        self.set_operation_progress(
            "dl",
            progress_start * 100.0,
            "Removing temporary video audio track...",
            taskbar=True,
        )

        try:
            process=subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **get_hidden_subprocess_kwargs(),
            )
            self.active_process=process
        except Exception as exc:
            log_path=write_failure_log(
                "download_strip_video_audio_start",
                exc,
                details=f"Input: {input_path}\nOutput: {output_path}",
            )
            raise RuntimeError(
                f"Could not start video audio stripping. Failure log: {log_path or FAILURE_LOG_DIR}"
            ) from exc

        output_lines=[]
        while True:
            if self.stop_requested and process.poll() is None:
                try:
                    process.terminate()
                except Exception:
                    pass

            line=process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if not line:
                continue
            output_lines.append(line.strip())

        code=process.poll()
        self.active_process=None

        if self.stop_requested:
            raise DownloadCancelled("Download stopped by user.")

        if code != 0:
            log_path=write_failure_log(
                "download_strip_video_audio",
                RuntimeError(f"FFmpeg exit code {code}"),
                details="\n".join(output_lines),
            )
            raise RuntimeError(
                f"Could not make a silent video. Failure log: {log_path or FAILURE_LOG_DIR}"
            )

        if not output_path.exists():
            exc=RuntimeError("FFmpeg completed but the silent video was not created.")
            log_path=write_failure_log(
                "download_strip_video_audio_output",
                exc,
                details=f"Expected output: {output_path}",
            )
            raise RuntimeError(
                f"{exc} Failure log: {log_path or FAILURE_LOG_DIR}"
            )

        self.set_operation_progress(
            "dl",
            progress_end * 100.0,
            "Video-only stream prepared...",
            taskbar=True,
        )
        return output_path


    def prepare_mkv_cover_attachments(self, cover_path, temp_dir):
        """Prepare JPEG cover attachments using Matroska's standard names.

        The full-resolution artwork is preserved without cropping. We always
        create cover.jpg, and for landscape artwork we also create
        cover_land.jpg so Explorer thumbnail handlers that honor Matroska's
        landscape naming convention can choose the intended 16:9 artwork.
        """
        if not cover_path:
            return []

        source = Path(cover_path)
        if not source.exists():
            return []

        target_dir = Path(temp_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            raw = source.read_bytes()
            with Image.open(BytesIO(raw)) as image:
                image = ImageOps.exif_transpose(image)
                if image.mode != "RGB":
                    image = image.convert("RGB")
                width, height = image.size

                buffer = BytesIO()
                image.save(
                    buffer,
                    format="JPEG",
                    quality=100,
                    subsampling=0,
                )
                normalized = buffer.getvalue()
        except Exception as exc:
            raise RuntimeError(
                f"Could not prepare the MKV cover attachment: {exc}"
            ) from exc

        attachments = []

        cover = target_dir / "cover.jpg"
        cover.write_bytes(normalized)
        attachments.append(cover)

        if width > height:
            landscape = target_dir / "cover_land.jpg"
            landscape.write_bytes(normalized)
            attachments.append(landscape)

        return attachments


    def verify_mkv_cover_attachment(self, file_path):
        """Return True only when the MKV contains a real JPEG cover attachment."""
        try:
            ffprobe = find_executable("ffprobe") or "ffprobe"
            if ffprobe == "ffprobe" and not find_executable("ffprobe"):
                return False

            command = [
                ffprobe,
                "-v",
                "error",
                "-show_streams",
                "-show_entries",
                "stream=codec_type,codec_name,disposition:stream_tags",
                "-of",
                "json",
                str(file_path),
            ]

            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                **get_hidden_subprocess_kwargs(),
            )

            if proc.returncode != 0 or not proc.stdout.strip():
                return False

            data = json.loads(proc.stdout)

            for stream in data.get("streams", []) or []:
                disposition = stream.get("disposition") or {}
                tags = stream.get("tags") or {}
                if (
                    stream.get("codec_name") in {"mjpeg", "png", "jpeg"}
                    and int(disposition.get("attached_pic", 0) or 0) == 1
                    and str(tags.get("mimetype", "")).lower() == "image/jpeg"
                ):
                    return True

                # FFmpeg may expose a Matroska image attachment as an
                # attachment stream rather than an attached-pic video stream.
                if (
                    stream.get("codec_type") == "attachment"
                    and str(tags.get("mimetype", "")).lower() == "image/jpeg"
                    and str(tags.get("filename", "")).lower().endswith(
                        ("cover.jpg", "cover_land.jpg")
                    )
                ):
                    return True

                # FFmpeg commonly exposes Matroska image attachments as
                # MJPEG streams carrying the attachment filename in tags.
                if (
                    stream.get("codec_name") in {"mjpeg", "jpeg"}
                    and str(tags.get("mimetype", "")).lower() == "image/jpeg"
                    and str(tags.get("filename", "")).lower().endswith(
                        ("cover.jpg", "cover_land.jpg")
                    )
                ):
                    return True

            return False
        except Exception:
            return False


    def merge_video_and_flac(
        self,
        video_path,
        flac_path,
        output_path,
        result,
        progress_start=0.0,
        progress_end=1.0,
        cover_path=None,
        audio_tracks=None,
    ):
        """Mux video with one or more already-created FLAC audio tracks.

        Every audio stream is copied without re-encoding and is labeled with
        its language/track name. The first track is marked as default. The
        resulting MKV therefore exposes the language tracks to players such
        as VLC while the individual FLAC files remain available separately.
        """
        if self.stop_requested:
            raise DownloadCancelled("Download stopped by user.")

        ffmpeg = get_ffmpeg_command()

        if not find_executable("ffmpeg") and ffmpeg == "ffmpeg":
            raise RuntimeError(
                "FFmpeg was not found. It is required to mux FLAC audio into the final video without re-encoding."
            )

        if isinstance(flac_path, (list, tuple)):
            audio_paths = [Path(path) for path in flac_path]
        else:
            audio_paths = [Path(flac_path)]

        audio_paths = [path for path in audio_paths if path.exists()]
        if not audio_paths:
            raise RuntimeError("No FLAC audio tracks were available for the final video mux.")

        track_data = list(audio_tracks or [])
        if len(track_data) < len(audio_paths):
            track_data.extend({} for _ in range(len(audio_paths) - len(track_data)))

        command = [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
        ]

        for path in audio_paths:
            command.extend(["-i", str(path)])

        command.extend([
            "-map",
            "0:v:0",
        ])

        for index in range(len(audio_paths)):
            command.extend(["-map", f"{index + 1}:a:0"])

        command.extend([
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-map_metadata",
            "-1",
        ])

        metadata_values = {
            "title": result.get("title") or "",
            "artist": result.get("artist") or "",
            "album": result.get("album") or "",
            "date": result.get("year") or "",
        }

        for key, value in metadata_values.items():
            if value:
                command.extend(["-metadata", f"{key}={value}"])

        for index, track in enumerate(track_data[:len(audio_paths)]):
            language_code = str(track.get("language_code") or "und").strip().lower()
            label = str(track.get("label") or track.get("language") or f"Audio Track {index + 1}").strip()

            command.extend([
                f"-metadata:s:a:{index}",
                f"language={language_code}",
                f"-metadata:s:a:{index}",
                f"title={label}",
                f"-disposition:a:{index}",
                "default" if index == 0 else "0",
            ])

        # Matroska cover art is stored as Attachments. Use the standard
        # cover.jpg name, plus cover_land.jpg for landscape artwork.
        cover_attachments = []
        if cover_path and Path(cover_path).exists():
            cover_attachments = self.prepare_mkv_cover_attachments(
                cover_path,
                Path(cover_path).parent,
            )

        for attachment in cover_attachments:
            command.extend(["-attach", str(attachment)])

        for index, attachment in enumerate(cover_attachments):
            command.extend([
                f"-metadata:s:t:{index}",
                "mimetype=image/jpeg",
                f"-metadata:s:t:{index}",
                f"filename={attachment.name}",
                f"-metadata:s:t:{index}",
                "title=Cover Art",
            ])

        command.append(str(output_path))

        track_count = len(audio_paths)
        self.set_operation_progress(
            "dl",
            progress_start * 100.0,
            f"Merging video + {track_count} language audio track{'s' if track_count != 1 else ''}...",
            taskbar=True,
        )
        self.append_log(
            self.dl_log,
            f"[FINAL MUX] video + {track_count} FLAC audio track(s) -> MKV (all streams copied)",
        )

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **get_hidden_subprocess_kwargs(),
            )
            self.active_process = process
        except Exception as exc:
            log_path = write_failure_log(
                "download_final_mux_start",
                exc,
                details=f"Output: {output_path}\nAudio tracks: {audio_paths}",
            )
            raise RuntimeError(
                f"Could not start final mux. Failure log: {log_path or FAILURE_LOG_DIR}"
            ) from exc

        output_lines = []

        while True:
            if self.stop_requested and process.poll() is None:
                try:
                    process.terminate()
                except Exception:
                    pass

            line = process.stdout.readline()

            if not line and process.poll() is not None:
                break

            if not line:
                continue

            clean_line = line.strip()
            output_lines.append(clean_line)
            if len(output_lines) <= 25:
                self.append_log(self.dl_log, clean_line)

        return_code = process.poll()
        self.active_process = None

        if self.stop_requested:
            raise DownloadCancelled("Download stopped by user.")

        if return_code != 0:
            log_path = write_failure_log(
                "download_final_mux",
                RuntimeError(f"FFmpeg exit code {return_code}"),
                details="\n".join(output_lines),
            )
            raise RuntimeError(
                f"Final video mux failed. Failure log: {log_path or FAILURE_LOG_DIR}"
            )

        if not Path(output_path).exists():
            exc = RuntimeError(
                "FFmpeg completed but the final merged video was not created."
            )
            log_path = write_failure_log(
                "download_final_mux_output",
                exc,
                details=f"Expected output: {output_path}",
            )
            raise RuntimeError(
                f"{exc} Failure log: {log_path or FAILURE_LOG_DIR}"
            )

        # Verify that the cover is really present in the final MKV. A successful
        # FFmpeg exit code alone is not enough because a player cannot display
        # artwork that never made it into the container.
        if cover_path and Path(cover_path).exists():
            if not self.verify_mkv_cover_attachment(output_path):
                repair_path = Path(output_path).with_name(
                    Path(output_path).stem + ".cover_repair.tmp.mkv"
                )
                try:
                    self.set_operation_progress(
                        "dl",
                        progress_start * 100.0,
                        "Rebinding thumbnail to final video...",
                        taskbar=True,
                    )

                    repair_attachments = self.prepare_mkv_cover_attachments(
                        cover_path,
                        Path(cover_path).parent,
                    )

                    repair_command = [
                        ffmpeg,
                        "-y",
                        "-i",
                        str(output_path),
                    ]

                    for attachment in repair_attachments:
                        repair_command.extend(["-attach", str(attachment)])

                    for attach_index, attachment in enumerate(repair_attachments):
                        repair_command.extend([
                            f"-metadata:s:t:{attach_index}",
                            "mimetype=image/jpeg",
                            f"-metadata:s:t:{attach_index}",
                            f"filename={attachment.name}",
                            f"-metadata:s:t:{attach_index}",
                            "title=Cover Art",
                        ])

                    repair_command.extend([
                        "-c",
                        "copy",
                        "-map_metadata",
                        "0",
                        "-map_chapters",
                        "0",
                        str(repair_path),
                    ])

                    repair = subprocess.run(
                        repair_command,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=180,
                        **get_hidden_subprocess_kwargs(),
                    )

                    if repair.returncode != 0 or not repair_path.exists():
                        raise RuntimeError(
                            f"Thumbnail repair remux failed (exit code {repair.returncode})."
                        )

                    os.replace(repair_path, output_path)

                    if not self.verify_mkv_cover_attachment(output_path):
                        raise RuntimeError(
                            "The final MKV was created but the embedded JPEG cover could not be verified."
                        )

                    self.append_log(
                        self.dl_log,
                        "VIDEO THUMBNAIL: attachment verified after repair remux.",
                    )
                except Exception as exc:
                    try:
                        if repair_path.exists():
                            repair_path.unlink()
                    except Exception:
                        pass
                    log_path = write_failure_log(
                        "download_final_mux_thumbnail_verify",
                        exc,
                        details=(
                            f"Output: {output_path}\n"
                            f"Thumbnail: {cover_path}"
                        ),
                    )
                    raise RuntimeError(
                        f"Final MKV thumbnail could not be verified. Failure log: {log_path or FAILURE_LOG_DIR}"
                    ) from exc

            else:
                self.append_log(
                    self.dl_log,
                    "VIDEO THUMBNAIL: embedded JPEG attachment verified in final MKV.",
                )

        self.set_operation_progress(
            "dl",
            progress_end * 100.0,
            f"{track_count} audio track{'s' if track_count != 1 else ''} bound to final video",
            taskbar=True,
        )

        if cover_attachments and self.verify_mkv_cover_attachment(output_path):
            names = ", ".join(path.name for path in cover_attachments)
            self.append_log(
                self.dl_log,
                f"VIDEO THUMBNAIL: physically embedded in final MKV ({names}) and verified.",
            )
        elif cover_attachments:
            exc = RuntimeError(
                "The final MKV was created, but its JPEG cover attachment could not be verified."
            )
            log_path = write_failure_log(
                "download_final_mux_cover_verification",
                exc,
                details=(
                    f"Output: {output_path}\n"
                    f"Attachments: {cover_attachments}"
                ),
            )
            raise RuntimeError(
                f"Final video cover embedding could not be verified. Failure log: {log_path or FAILURE_LOG_DIR}"
            )

        # The standalone FLAC files are temporary inputs for this mux.
        # They must only be deleted after the final MKV has been verified.
        cleanup_errors = []
        for path in audio_paths:
            try:
                if path.exists():
                    path.unlink()
            except Exception as exc:
                cleanup_errors.append(f"{path}: {exc}")

        if cleanup_errors:
            cleanup_log = write_failure_log(
                "download_final_mux_cleanup",
                RuntimeError("One or more temporary FLAC files could not be deleted."),
                details="\n".join(cleanup_errors),
            )
            self.append_log(
                self.dl_log,
                "TEMP FLAC CLEANUP WARNING: " + "; ".join(cleanup_errors)
                + f" | Failure log: {cleanup_log or FAILURE_LOG_DIR}",
            )
        else:
            self.append_log(
                self.dl_log,
                f"TEMP FLAC CLEANUP: {track_count} temporary language track(s) removed after successful MKV mux.",
            )

        return Path(output_path)


    def build_yt_dlp_command(
        self,
        source_url,
        result,
        selected_format,
    ):
        output_dir = self.paths["downloader"]

        title_for_name = sanitize_filename(
            result.get("output_filename") or result.get("title") or "track"
        )

        output_template = os.path.join(
            output_dir,
            f"{title_for_name}.%(ext)s",
        )

        command = [
            get_ytdlp_command(),
            *get_ytdlp_runtime_args(getattr(self, "performance_mode", "aggressive")),
            "--newline",
            "--windows-filenames",
            "--concurrent-fragments",
            str(get_concurrent_fragment_count(getattr(self, "performance_mode", "aggressive"))),
            "--embed-metadata",
            "--embed-thumbnail",
        ]

        command.extend(get_browser_cookie_args(source_url))

        if "quality_extractor_arg" in result:
            effective_extractor_arg = result.get("quality_extractor_arg")
        else:
            effective_extractor_arg = (
                self._dl_youtube_extractor_arg
                or self._last_quality_extractor_arg
            )
        if effective_extractor_arg:
            command.extend(youtube_extractor_args_list(effective_extractor_arg))

        spec = self.selected_quality_spec(selected_format)
        kind = spec.get("kind")

        if kind == "audio":
            audio_format = spec.get("audio_format") or "flac"
            quality = spec.get("quality") or "0"
            command.extend([
                "-x",
                "--audio-format",
                audio_format,
                "--audio-quality",
                quality,
            ])
        else:
            height = spec.get("height")
            if height:
                requested_height = int(height)
                # 720p and below stay in a normal MP4 workflow with the
                # source's original lossy audio. Prefer a native combined
                # MP4 format first; otherwise pair the video stream with
                # the original M4A/AAC audio stream, then fall back to the
                # best available audio without forcing any audio re-encode.
                video_selector = (
                    f"bestvideo[height<={requested_height}][ext=mp4]+bestaudio[ext=m4a]"
                    f"/bestvideo[height<={requested_height}]+bestaudio"
                    f"/best[height<={requested_height}]"
                )
            else:
                video_selector = (
                    "bestvideo[ext=mp4]+bestaudio[ext=m4a]"
                    "/bestvideo+bestaudio"
                    "/best"
                )

            # This path is reserved for 720p and below video downloads.
            # Audio remains in its original source codec; no FLAC extraction,
            # audio transcoding, or other lossless-audio workflow is used.
            command.extend([
                "-f",
                video_selector,
                "--merge-output-format",
                "mp4",
            ])

        is_video_download = kind == "video"

        if self._selected_download_subtitles and is_video_download:
            command.extend([
                "--write-sub",
                "--write-auto-sub",
                "--embed-subs",
                "--sub-lang",
                "en,ar",
            ])


        command.extend([
            "-o",
            output_template,
            "--",
            source_url,
        ])

        return command


    def discover_downloaded_file(self, output_dir, before_files):
        folder = Path(output_dir)

        candidates = [
            p for p in folder.iterdir()
            if p.is_file()
            and p not in before_files
            and p.suffix.lower() in {
                ".flac",
                ".mp3",
                ".m4a",
                ".mp4",
                ".webm",
                ".aac",
            }
        ]

        if not candidates:
            return None

        candidates.sort(
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        return candidates[0]

    def execute_download_for_result(
        self,
        result,
        item_index=1,
        item_total=1,
        selected_format_override=None,
    ):
        video_id = result.get("video_id")

        if not video_id:
            raise RuntimeError(
                "Resolved result has no video id"
            )

        source_url = result.get("source_url") or f"https://www.youtube.com/watch?v={video_id}"

        # Playlist items are immutable sources. Never allow an enriched YTM
        # result to substitute a different video URL or video ID.
        if result.get("playlist_source_locked"):
            locked_id = str(result.get("video_id") or "").strip()
            parsed_source = urllib.parse.urlparse(source_url)
            source_query = urllib.parse.parse_qs(parsed_source.query)
            source_id = str((source_query.get("v") or [""])[0]).strip()
            if locked_id and source_id and locked_id != source_id:
                raise RuntimeError(
                    f"Playlist source-lock violation: result video ID {locked_id} does not match source URL video ID {source_id}"
                )

        selected_format = (
            selected_format_override
            if selected_format_override is not None
            else self._selected_download_format
        )
        output_dir = self.paths["downloader"]
        os.makedirs(output_dir, exist_ok=True)

        def report(local_fraction, message, taskbar=True):
            # set_operation_progress maps this local item progress to playlist
            # progress when a playlist context is active. For a single download,
            # the same value naturally remains the whole-operation percentage.
            local = max(0.0, min(1.0, float(local_fraction)))
            self.set_operation_progress(
                "dl",
                local * 100.0,
                message,
                taskbar=taskbar,
            )

        report(0.0, "Preparing source...")

        self.append_log(self.dl_log, "SOURCE: " + source_url)
        self.append_log(self.dl_log, "MATCH: " + result.get("source", ""))
        self.append_log(self.dl_log, "ARTIST: " + result.get("artist", ""))
        self.append_log(self.dl_log, "TITLE: " + result.get("title", ""))

        # 1080p and above (including Best Quality) use a separate FLAC audio
        # stage followed by silent video download and lossless MKV mux.
        # 720p and below stay in the normal MP4 path with the source audio
        # stream preserved in its original lossy codec.
        if self.is_lossless_video_mode(selected_format):
            title_for_name = sanitize_filename(
                result.get("output_filename") or result.get("title") or "track"
            )
            base_name = title_for_name

            temp_root = Path(output_dir) / ".ytm_music_toolkit_temp"
            temp_dir = temp_root / str(os.getpid())
            temp_dir.mkdir(parents=True, exist_ok=True)

            final_video = Path(output_dir) / f"{base_name}.mkv"
            audio_track_outputs = []
            cover_attachment = temp_dir / "cover.jpg"
            cover_bytes = None

            try:
                self._last_quality_extractor_arg = (
                    result.get("audio_tracks_extractor_arg")
                    or self._last_quality_extractor_arg
                )
                audio_tracks = self.ensure_audio_tracks_for_result(result)
                if not audio_tracks:
                    raise RuntimeError(
                        "YouTube exposed no separate audio tracks for this video."
                    )

                report(0.02, "Downloading language audio tracks...")
                audio_track_outputs = self.download_all_audio_tracks(
                    source_url,
                    result,
                    output_dir,
                    progress_start=0.02,
                    progress_end=0.30,
                )

                report(0.31, "Downloading highest-quality thumbnail separately...")
                _, cover_bytes, cover_size = self.download_highest_quality_thumbnail(
                    result,
                    cover_attachment,
                )
                cover_written = True
                self.append_log(
                    self.dl_log,
                    f"VIDEO THUMBNAIL: {cover_size[0]}x{cover_size[1]} JPEG downloaded separately for mux.",
                )

                report(0.35, "Binding language labels and artwork...")
                for completed in audio_track_outputs:
                    path = completed["path"]
                    track = completed["track"]
                    if cover_bytes:
                        write_flac_metadata(
                            path,
                            result,
                            cover_bytes=cover_bytes,
                            wipe_tags=False,
                        )
                    self._write_language_tag_to_flac(path, track)
                    self.set_operation_progress(
                        "dl",
                        (0.35 + 0.13 * (audio_track_outputs.index(completed) + 1) / max(1, len(audio_track_outputs))) * 100.0,
                        f"Binding {track.get('label', 'audio track')}...",
                        taskbar=True,
                    )

                report(0.50, "Downloading silent video stream...")
                video_template = str(temp_dir / f"{base_name}.%(ext)s")
                video_selector_spec = self.selected_quality_spec(selected_format)
                requested_height = int(video_selector_spec.get("height") or 0)
                if requested_height:
                    video_selector = (
                        f"bestvideo[height={requested_height}]"
                        f"/bestvideo[height<={requested_height}]"
                        "/bestvideo"
                    )
                else:
                    video_selector = "bestvideo"

                video_command = [
                    get_ytdlp_command(),
                    *get_ytdlp_runtime_args(getattr(self, "performance_mode", "aggressive")),
                    "--newline",
                    "--windows-filenames",
                    "--concurrent-fragments",
                    str(get_concurrent_fragment_count(getattr(self, "performance_mode", "aggressive"))),
                    "--no-playlist",
                    *youtube_extractor_args_list(
                        result.get("quality_extractor_arg")
                        if "quality_extractor_arg" in result
                        else (
                            self._dl_youtube_extractor_arg
                            or self._last_quality_extractor_arg
                        )
                    ),
                ]
                video_command.extend(get_browser_cookie_args(source_url))
                video_command.extend([
                    "-f",
                    video_selector,
                    "-o",
                    video_template,
                    "--",
                    source_url,
                ])

                self.run_ytdlp_logged(
                    video_command,
                    "VIDEO",
                    output_dir,
                    progress_start=0.50,
                    progress_end=0.74,
                )

                video_extensions = {".mp4", ".webm", ".mkv", ".mov", ".m4v"}
                video_candidates = [
                    p for p in temp_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in video_extensions
                ]

                if not video_candidates:
                    raise RuntimeError(
                        "yt-dlp finished the video stage but the video file could not be located."
                    )

                video_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                temp_video_path = video_candidates[0]

                silent_video_path = temp_dir / f"{base_name}.silent.mkv"
                report(0.75, "Preparing video-only stream...")
                self.strip_audio_from_video(
                    temp_video_path,
                    silent_video_path,
                    progress_start=0.74,
                    progress_end=0.78,
                )
                if temp_video_path != silent_video_path:
                    try:
                        temp_video_path.unlink()
                    except Exception:
                        pass

                report(0.80, "Merging video + all language audio tracks...")
                audio_paths = [item["path"] for item in audio_track_outputs]
                track_specs = [item["track"] for item in audio_track_outputs]
                self.merge_video_and_flac(
                    silent_video_path,
                    audio_paths,
                    final_video,
                    result,
                    progress_start=0.80,
                    progress_end=0.96,
                    cover_path=cover_attachment if cover_written else None,
                    audio_tracks=track_specs,
                )

                report(1.0, "Operation Successful")
                self.append_log(
                    self.dl_log,
                    "VIDEO SAVED: " + str(final_video),
                )
                self.append_log(
                    self.dl_log,
                    f"VIDEO AUDIO: {len(audio_paths)} language track(s), each FLAC, muxed without re-encoding",
                )
                self.append_log(
                    self.dl_log,
                    "SEPARATE FLAC FILES: temporary mux inputs removed after successful final video creation",
                )
                if cover_written:
                    self.append_log(
                        self.dl_log,
                        "VIDEO THUMBNAIL: separately downloaded and embedded as verified Matroska cover attachment(s)",
                    )
                return final_video

            except Exception:
                raise
            finally:
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    if temp_root.exists() and not any(temp_root.iterdir()):
                        temp_root.rmdir()
                except Exception as exc:
                    write_failure_log(
                        "download_temp_cleanup",
                        exc,
                        details=f"Directory: {temp_dir}",
                    )

        # Normal audio / 720p-and-below video path.
        # Video downloads here intentionally KEEP the source audio stream
        # in its original lossy codec and are merged into an MP4 container.
        before_files = set(Path(output_dir).iterdir())
        command = self.build_yt_dlp_command(source_url, result, selected_format)

        output_lines = self.run_ytdlp_logged(
            command,
            "media",
            output_dir,
            progress_start=0.03,
            progress_end=0.70,
        )

        report(0.72, "Preparing metadata and artwork...")
        downloaded = self.discover_downloaded_file(output_dir, before_files)

        if not downloaded:
            possible = [
                p for p in Path(output_dir).iterdir()
                if p.is_file() and p.suffix.lower() in {
                    ".flac", ".mp3", ".m4a", ".mp4", ".webm", ".aac",
                }
            ]
            if possible:
                possible.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                downloaded = possible[0]

        if not downloaded:
            exc = RuntimeError("yt-dlp finished but the output file could not be located")
            log_path = write_failure_log("download_output_missing", exc, details=f"Directory: {output_dir}")
            raise RuntimeError(
                f"{exc}. Failure log: {log_path or FAILURE_LOG_DIR}"
            )

        thumbnail_temp_dir = Path(tempfile.mkdtemp(
            prefix=".ytm_thumbnail_",
            dir=output_dir,
        ))
        thumbnail_path = thumbnail_temp_dir / "cover.jpg"
        try:
            report(0.74, "Downloading highest-quality thumbnail separately...")
            _, thumbnail_bytes, thumb_size = self.download_highest_quality_thumbnail(
                result,
                thumbnail_path,
            )
            self.append_log(
                self.dl_log,
                f"THUMBNAIL: {thumb_size[0]}x{thumb_size[1]} JPEG downloaded separately.",
            )

            result_with_thumb = dict(result)
            result_with_thumb["downloaded_thumbnail_bytes"] = thumbnail_bytes

            downloaded = self.postprocess_downloaded_file(
                downloaded,
                result_with_thumb,
                progress_callback=lambda frac, msg: report(0.68 + 0.12 * frac, msg),
                thumbnail_path=thumbnail_path,
            )
            self.append_log(
                self.dl_log,
                f"THUMBNAIL: bound to {downloaded.name} successfully.",
            )

            if Path(downloaded).suffix.lower() == ".mp4" and self.selected_quality_spec(selected_format).get("kind") == "video":
                report(0.82, "Extracting separate language audio tracks...")
                try:
                    self.ensure_audio_tracks_for_result(result)
                    self.download_all_audio_tracks(
                        source_url,
                        result,
                        output_dir,
                        progress_start=0.82,
                        progress_end=0.98,
                        cover_bytes=thumbnail_bytes,
                    )
                except Exception as exc:
                    log_path = write_failure_log(
                        "download_audio_tracks_after_mp4",
                        exc,
                        details=f"Video: {downloaded}\nSource: {source_url}",
                    )
                    raise RuntimeError(
                        f"Separate language audio-track extraction failed. Failure log: {log_path or FAILURE_LOG_DIR}"
                    ) from exc

            report(1.0, "Operation Successful")
        except Exception as exc:
            log_path = write_failure_log(
                "download_thumbnail_or_postprocess",
                exc,
                details=f"File: {downloaded}\nSource video id: {result.get('video_id')}",
            )
            raise RuntimeError(
                f"Thumbnail binding or metadata processing failed. Failure log: {log_path or FAILURE_LOG_DIR}"
            ) from exc
        finally:
            shutil.rmtree(thumbnail_temp_dir, ignore_errors=True)
        return downloaded




    def ensure_audio_tracks_for_result(self, result):
        """Inspect the source and cache its distinct available audio tracks.

        The inspector returns one best format per language/variant track. The
        chosen extractor strategy is cached on the result and reused by every
        subsequent yt-dlp command so format IDs remain valid across the full
        download pipeline.
        """
        if not result:
            return []

        cached = result.get("audio_tracks")
        if isinstance(cached, list):
            return cached

        video_id = str(result.get("video_id") or "").strip()
        source_url = str(
            result.get("source_url")
            or (f"https://www.youtube.com/watch?v={video_id}" if video_id else "")
        ).strip()
        if not source_url:
            raise RuntimeError("Cannot inspect audio tracks without a source URL.")

        try:
            formats, extractor_arg = inspect_youtube_formats(
                source_url,
                timeout=45,
            )
        except Exception as exc:
            log_path = write_failure_log(
                "download_audio_track_inspection",
                exc,
                details=f"Source: {source_url}",
            )
            raise RuntimeError(
                f"Could not inspect the available audio tracks. Failure log: {log_path or FAILURE_LOG_DIR}"
            ) from exc

        tracks = build_audio_track_options(formats)
        if not tracks:
            exc = RuntimeError("No separate audio tracks were exposed by YouTube for this video.")
            log_path = write_failure_log(
                "download_audio_track_inspection_empty",
                exc,
                details=f"Source: {source_url}\nExtractor strategy: {extractor_arg}",
            )
            raise RuntimeError(
                f"{exc} Failure log: {log_path or FAILURE_LOG_DIR}"
            )

        result["audio_tracks"] = tracks
        result["audio_tracks_extractor_arg"] = extractor_arg
        self._last_quality_extractor_arg = extractor_arg
        return tracks


    def _write_language_tag_to_flac(self, file_path, track):
        """Write explicit language/track labels without disturbing audio/artwork."""
        flac = FLAC(file_path)

        language_code = str(track.get("language_code") or "und").strip().lower()
        language_name = str(track.get("language") or "Unknown").strip()
        label = str(track.get("label") or language_name or "Audio Track").strip()

        flac["LANGUAGE"] = [language_code]
        flac["LANGUAGE_NAME"] = [language_name]
        flac["AUDIO_TRACK"] = [label]

        if track.get("is_default"):
            flac["AUDIO_DEFAULT"] = ["Yes"]
        else:
            flac.pop("AUDIO_DEFAULT", None)

        if track.get("is_original"):
            flac["AUDIO_ORIGINAL"] = ["Yes"]
        else:
            flac.pop("AUDIO_ORIGINAL", None)

        flac.save()


    def download_all_audio_tracks(
        self,
        source_url,
        result,
        output_dir,
        progress_start=0.0,
        progress_end=1.0,
        cover_bytes=None,
    ):
        """Download each discovered language/variant as its own FLAC file."""
        if self.stop_requested:
            raise DownloadCancelled("Download stopped by user.")

        tracks = self.ensure_audio_tracks_for_result(result)
        if not tracks:
            raise RuntimeError("No audio tracks are available for this source.")

        output_folder = Path(output_dir)
        output_folder.mkdir(parents=True, exist_ok=True)
        title = sanitize_filename(
            result.get("output_filename") or result.get("title") or "audio"
        )

        # Keep the selected extractor strategy consistent with the inspection
        # that produced the exact format IDs below.
        if "audio_tracks_extractor_arg" in result:
            extractor_arg = result.get("audio_tracks_extractor_arg")
        else:
            extractor_arg = (
                self._last_quality_extractor_arg
                or self._dl_youtube_extractor_arg
            )

        completed = []
        total = len(tracks)

        for index, track in enumerate(tracks, 1):
            if self.stop_requested:
                raise DownloadCancelled("Download stopped by user.")

            label = str(track.get("label") or track.get("language") or f"Audio Track {index}").strip()
            safe_label = sanitize_filename(label)
            final_path = output_folder / f"{title} [{safe_label}].flac"
            template = str(output_folder / f"{title} [{safe_label}].%(ext)s")

            command = [
                get_ytdlp_command(),
                *get_ytdlp_runtime_args(getattr(self, "performance_mode", "aggressive")),
                "--newline",
                "--windows-filenames",
                "--no-playlist",
                "--no-overwrites",
            ]

            command.extend(youtube_extractor_args_list(extractor_arg))

            command.extend(get_browser_cookie_args(source_url))

    
            command.extend([
                "-f",
                str(track.get("format_id")),
                "-x",
                "--audio-format",
                "flac",
                "--audio-quality",
                "0",
                "-o",
                template,
                "--",
                source_url,
            ])

            local_start = progress_start + (progress_end - progress_start) * ((index - 1) / total)
            local_end = progress_start + (progress_end - progress_start) * (index / total)

            self.set_operation_progress(
                "dl",
                local_start * 100.0,
                f"Downloading {label} audio track...",
                taskbar=True,
            )

            try:
                self.run_ytdlp_logged(
                    command,
                    f"audio track {index}/{total} — {label}",
                    str(output_folder),
                    progress_start=local_start,
                    progress_end=local_end,
                )
            except DownloadCancelled:
                raise
            except Exception as exc:
                log_path = write_failure_log(
                    "download_audio_track",
                    exc,
                    details=(
                        f"Source: {source_url}\n"
                        f"Track: {label}\n"
                        f"Format ID: {track.get('format_id')}\n"
                        f"Command: {command}"
                    ),
                )
                raise RuntimeError(
                    f"Could not download {label} audio. Failure log: {log_path or FAILURE_LOG_DIR}"
                ) from exc

            # yt-dlp uses the template's extension after post-processing. When
            # a previous same-named file exists, the temporary final name above
            # should still point to the latest file; otherwise find the newest
            # matching FLAC for this exact language label.
            if not final_path.exists():
                matching = sorted(
                    output_folder.glob(f"{title} [{safe_label}]*.flac"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if matching:
                    final_path = matching[0]

            if not final_path.exists():
                exc = RuntimeError(
                    f"yt-dlp reported success but the {label} FLAC file was not found."
                )
                log_path = write_failure_log(
                    "download_audio_track_output_missing",
                    exc,
                    details=f"Expected: {final_path}\nSource: {source_url}",
                )
                raise RuntimeError(
                    f"{exc} Failure log: {log_path or FAILURE_LOG_DIR}"
                )

            if cover_bytes:
                write_flac_metadata(
                    final_path,
                    result,
                    cover_bytes=cover_bytes,
                    wipe_tags=False,
                )

            self._write_language_tag_to_flac(final_path, track)

            completed.append({
                "path": Path(final_path),
                "track": dict(track),
            })

            self.set_operation_progress(
                "dl",
                local_end * 100.0,
                f"{label} audio track ready...",
                taskbar=True,
            )

        return completed


    def download_highest_quality_thumbnail(
        self,
        result,
        destination_path,
    ):
        """Download and persist the highest-resolution valid thumbnail candidate."""
        result = result or {}
        destination = Path(destination_path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        candidates = []

        if result.get("ytm_matched"):
            # YT Music matches are album-art driven. Do not mix in the
            # video's 16:9 thumbnails because a larger pixel area should not
            # override the user's intended square music artwork.
            if result.get("cover_url"):
                candidates.append(result.get("cover_url"))
            for candidate in result.get("thumbnail_candidates", []) or []:
                if candidate:
                    candidates.append(candidate)
        else:
            # Ordinary YouTube downloads should use the video's native
            # thumbnail, trying every direct size and any extractor-supplied
            # candidate before giving up.
            source_thumb = result.get("source_thumbnail_url") or ""
            if source_thumb:
                candidates.append(source_thumb)

            for candidate in result.get("thumbnail_candidates", []) or []:
                if candidate:
                    candidates.append(candidate)

            video_id = result.get("video_id") or ""
            if video_id:
                candidates.extend(
                    youtube_thumbnail_candidates(
                        f"https://www.youtube.com/watch?v={video_id}"
                    )
                )

            if result.get("cover_url"):
                candidates.append(result.get("cover_url"))

        deduped = []
        seen = set()
        for candidate in candidates:
            candidate = canonicalize_thumbnail_url(str(candidate or "").strip())
            if candidate and candidate not in seen:
                seen.add(candidate)
                deduped.append(candidate)

        if not deduped:
            raise RuntimeError("No thumbnail candidates were available for this media.")

        best_raw = None
        best_area = -1
        best_bytes = -1
        best_source = ""

        for candidate in deduped:
            try:
                response = session.get(
                    candidate,
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                raw = response.content
                if not raw:
                    continue

                image = Image.open(BytesIO(raw))
                image = ImageOps.exif_transpose(image)
                width, height = image.size
                area = int(width) * int(height)

                if area > best_area or (area == best_area and len(raw) > best_bytes):
                    best_raw = raw
                    best_area = area
                    best_bytes = len(raw)
                    best_source = candidate
            except Exception:
                continue

        if best_raw is None:
            raise RuntimeError("All thumbnail candidates failed image validation.")

        normalized = normalize_cover_to_jpeg(best_raw)
        if not normalized:
            raise RuntimeError("The selected thumbnail could not be normalized to JPEG.")

        destination.write_bytes(normalized)

        try:
            with Image.open(BytesIO(normalized)) as check:
                width, height = check.size
        except Exception as exc:
            raise RuntimeError("Downloaded thumbnail failed the final image validation.") from exc

        self.append_log(
            self.dl_log,
            f"THUMBNAIL: downloaded {width}x{height} from {best_source}",
        )
        return destination, normalized, (width, height)


    def embed_mp4_video_thumbnail(self, file_path, thumbnail_path):
        """Embed a JPEG as a real attached-picture stream in an MP4 video.

        The video and audio streams are copied without re-encoding. This is
        separate from MP4 audio-style ``covr`` artwork because video players
        that support attached pictures can consume the image as cover art.
        """
        if not thumbnail_path or not Path(thumbnail_path).exists():
            raise RuntimeError("Thumbnail file is missing for MP4 embedding.")

        ffmpeg = get_ffmpeg_command()
        if not find_executable("ffmpeg") and ffmpeg == "ffmpeg":
            raise RuntimeError("FFmpeg was not found. It is required to embed the MP4 video thumbnail.")

        source = Path(file_path)
        temp_output = source.with_name(source.stem + ".thumbnail_embed.tmp.mp4")

        command = [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-i",
            str(thumbnail_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-map",
            "0:s?",
            "-map",
            "1:0",
            "-map_metadata",
            "0",
            "-map_chapters",
            "0",
            "-c:v:0",
            "copy",
            "-c:a",
            "copy",
            "-c:s",
            "copy",
            "-c:v:1",
            "mjpeg",
            "-disposition:v:1",
            "attached_pic",
            "-metadata:s:v:1",
            "title=Cover Art",
            str(temp_output),
        ]

        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                **get_hidden_subprocess_kwargs(),
            )

            if proc.returncode != 0:
                raise RuntimeError(
                    f"FFmpeg MP4 thumbnail embedding failed (exit code {proc.returncode})."
                )

            if not temp_output.exists():
                raise RuntimeError("FFmpeg completed but the thumbnail-embedded MP4 was not created.")

            os.replace(temp_output, source)
            return True
        except Exception as exc:
            try:
                if temp_output.exists():
                    temp_output.unlink()
            except Exception:
                pass

            log_path = write_failure_log(
                "download_mp4_thumbnail_embed",
                exc,
                details=f"Video: {source}\nThumbnail: {thumbnail_path}",
            )
            raise RuntimeError(
                f"Could not embed the video thumbnail into {source.name}. Failure log: {log_path or FAILURE_LOG_DIR}"
            ) from exc


    def embed_webm_video_thumbnail(self, file_path, thumbnail_path):
        """Attach artwork to WebM by remuxing unchanged streams into MKV.

        WebM cannot store Matroska attachment streams, so the output container
        becomes MKV while its encoded audio and video remain untouched.
        """
        if not thumbnail_path or not Path(thumbnail_path).exists():
            raise RuntimeError("Thumbnail file is missing for WebM embedding.")

        ffmpeg = get_ffmpeg_command()
        if not find_executable("ffmpeg") and ffmpeg == "ffmpeg":
            raise RuntimeError("FFmpeg was not found. It is required to embed the WebM video thumbnail.")

        source = Path(file_path)
        destination = source.with_suffix(".mkv")
        temp_output = destination.with_name(destination.stem + ".thumbnail_embed.tmp.mkv")
        command = [
            ffmpeg, "-y", "-i", str(source),
            "-map", "0", "-map", "1:0", "-c", "copy",
            "-attach", str(thumbnail_path),
            "-metadata:s:t:0", "mimetype=image/jpeg",
            "-metadata:s:t:0", "filename=cover.jpg",
            "-metadata:s:t:0", "title=Cover Art",
            str(temp_output),
        ]

        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                **get_hidden_subprocess_kwargs(),
            )
            if proc.returncode != 0 or not temp_output.exists():
                raise RuntimeError(
                    f"FFmpeg WebM-to-MKV thumbnail embedding failed (exit code {proc.returncode})."
                )
            os.replace(temp_output, destination)
            source.unlink()
            if not self.verify_mkv_cover_attachment(destination):
                raise RuntimeError("The remuxed MKV does not contain a verifiable JPEG cover attachment.")
            return destination
        except Exception as exc:
            try:
                if temp_output.exists():
                    temp_output.unlink()
            except Exception:
                pass
            log_path = write_failure_log(
                "download_webm_thumbnail_embed",
                exc,
                details=f"Video: {source}\nThumbnail: {thumbnail_path}",
            )
            raise RuntimeError(
                f"Could not embed the video thumbnail into {source.name}. Failure log: {log_path or FAILURE_LOG_DIR}"
            ) from exc


    def postprocess_downloaded_file(
        self,
        file_path,
        result,
        progress_callback=None,
        thumbnail_path=None,
    ):
        def report(fraction, message):
            if progress_callback:
                progress_callback(max(0.0, min(1.0, fraction)), message)

        try:
            report(0.05, "Fetching matched artwork...")

            cover_bytes = result.get("downloaded_thumbnail_bytes")
            cover_url = result.get("cover_url")

            if not cover_bytes and cover_url:
                raw, _, _ = inspect_image_from_url(cover_url)
                if raw:
                    cover_bytes = raw

            suffix = Path(file_path).suffix.lower()
            report(0.35, "Applying metadata and artwork...")

            if suffix == ".flac":
                write_flac_metadata(
                    file_path,
                    result,
                    cover_bytes=cover_bytes,
                    wipe_tags=False,
                )

                report(0.78, "Normalizing cover artwork to 1:1...")
                try:
                    crop_flac_cover(file_path)
                except Exception as exc:
                    log_path = write_failure_log(
                        "download_cover_crop",
                        exc,
                        details=f"File: {file_path}",
                    )
                    self.append_log(
                        self.dl_log,
                        f"COVER CROP WARNING: {exc} | Failure log: {log_path or FAILURE_LOG_DIR}",
                    )

            else:
                metadata_written = write_generic_audio_metadata(
                    file_path,
                    result,
                    cover_bytes=cover_bytes,
                )

                if suffix == ".mp4" and thumbnail_path:
                    report(0.82, "Embedding video thumbnail...")
                    self.embed_mp4_video_thumbnail(
                        file_path,
                        thumbnail_path,
                    )
                elif suffix == ".webm" and thumbnail_path:
                    report(0.82, "Embedding video thumbnail...")
                    file_path = self.embed_webm_video_thumbnail(
                        file_path,
                        thumbnail_path,
                    )
                elif not metadata_written:
                    raise RuntimeError(
                        f"Thumbnail embedding is not supported for downloaded format {suffix or '(unknown)'}."
                    )

            report(1.0, "Metadata + artwork complete")
            return Path(file_path)

        except Exception as exc:
            log_path = write_failure_log(
                "download_postprocess",
                exc,
                details=f"File: {file_path}",
            )
            raise RuntimeError(
                f"Metadata/artwork processing failed for {Path(file_path).name}. Failure log: {log_path or FAILURE_LOG_DIR}"
            ) from exc


    def run_download_worker(self, user_input):
        self._last_download_outcome = "running"
        queue_run = bool(getattr(self, "_v3_queue_active", False))
        used_ytm_matching = (
            not is_youtube_url(user_input)
            or is_youtube_music_url(user_input)
        )
        # Track real playlist outcomes: metadata failures currently skip items,
        # and the worker must never report success if not one file was saved.
        playlist_stats = {
            "total": 0,
            "downloaded": 0,
            "metadata_failures": 0,
            "resolution_failures": 0,
        }

        try:
            os.makedirs(self.paths["downloader"], exist_ok=True)
            self.set_operation_progress(
                "dl",
                2,
                "Resolving source and preparing the pipeline...",
                taskbar=True,
            )

            mode, payload = self.resolve_for_download(user_input)

            if mode == "playlist":
                urls, playlist_uses_ytm = payload
                used_ytm_matching = bool(playlist_uses_ytm)

                if not urls:
                    raise RuntimeError("Could not read any playlist entries")

                total = len(urls)
                playlist_stats["total"] = total

                for index, playlist_entry in enumerate(urls, 1):
                    if self.stop_requested:
                        raise DownloadCancelled("Download stopped by user.")

                    resolver = self.ensure_resolver()
                    if isinstance(playlist_entry, dict):
                        url = str(playlist_entry.get("source_url") or "").strip()
                        meta = resolver.metadata_from_playlist_entry(playlist_entry, url)
                    else:
                        url = str(playlist_entry or "").strip()
                        meta = None

                    self.set_collection_progress(
                        "dl",
                        index,
                        total,
                        0.0,
                        f"Playlist {index}/{total} — preparing item metadata...",
                        taskbar=True,
                    )

                    # Flat playlist metadata is normally sufficient. Only make
                    # another extractor call when the listing omitted its ID/title.
                    if not meta and url:
                        meta = resolver.metadata_from_url(url)

                    if not meta:
                        playlist_stats["metadata_failures"] += 1
                        self.append_log(self.dl_log, f"[{index}/{total}] metadata lookup failed — item skipped")
                        write_failure_log(
                            "download_playlist_metadata",
                            RuntimeError("Metadata lookup returned no result"),
                            details=f"Item {index}/{total}: {url}",
                        )
                        continue

                    # IMPORTANT: a playlist item must always download the
                    # exact video that exists in the playlist. Previously,
                    # music.youtube.com playlists searched YT Music and then
                    # replaced the original video's ID with the search result
                    # ID. A weak/ambiguous match could therefore download a
                    # completely different song.
                    source_result = resolver.direct_result_from_metadata(meta)
                    if source_result and isinstance(playlist_entry, dict) and playlist_entry.get("ytmusic_liked_entry"):
                        source_result["source"] = "YouTube Music Liked Music (authenticated library)"
                        source_result["ytm_matched"] = True
                        source_result["ytmusic_liked_entry"] = True
                        source_result["quality_extractor_arg"] = LIKED_MUSIC_EXTRACTOR_ARG

                    is_liked_music_entry = (
                        isinstance(playlist_entry, dict)
                        and bool(playlist_entry.get("ytmusic_liked_entry"))
                    )
                    if playlist_uses_ytm and not is_liked_music_entry:
                        ytm_result = None
                        try:
                            ytm_result = resolver.search(
                                meta["artist"],
                                meta["title"],
                                meta.get("album", ""),
                            )
                        except Exception as exc:
                            write_failure_log(
                                "download_playlist_ytm_match",
                                exc,
                                details=f"Item {index}/{total}: {url}",
                            )

                        # Keep the exact playlist source ID no matter what.
                        # YTM data is accepted only when it is consistent with
                        # the original item's artist/title; otherwise the
                        # source video's own metadata/artwork remains in use.
                        result = source_result

                        if ytm_result:
                            # ABSOLUTE playlist source lock:
                            # YTM matching may enrich a playlist item ONLY when
                            # it resolves to the exact same YouTube video ID.
                            # A title/artist similarity is not sufficient because
                            # it can select a live/remaster/cover/lyric-video
                            # variant of the intended track.
                            source_video_id = str(source_result.get("video_id") or "").strip()
                            matched_video_id = str(ytm_result.get("video_id") or "").strip()

                            if source_video_id and matched_video_id and source_video_id == matched_video_id:
                                result = dict(ytm_result)
                                result["video_id"] = source_video_id
                                result["source_url"] = source_result.get("source_url", url)
                                result["requested_artist"] = meta.get("artist", "")
                                result["requested_title"] = meta.get("title", "")
                                result["playlist_source_locked"] = True
                            else:
                                self.append_log(
                                    self.dl_log,
                                    f"[{index}/{total}] YTM result points to a different video — rejected; keeping exact playlist source.",
                                )
                                result = source_result
                        else:
                            self.append_log(
                                self.dl_log,
                                f"[{index}/{total}] YTM match unavailable — keeping exact playlist source.",
                            )
                    else:
                        result = source_result

                    if self.stop_requested:
                        raise DownloadCancelled("Download stopped by user.")

                    if not result:
                        playlist_stats["resolution_failures"] += 1
                        self.append_log(self.dl_log, f"[{index}/{total}] no usable source metadata — item skipped")
                        write_failure_log(
                            "download_playlist_resolution",
                            RuntimeError("No usable result was resolved"),
                            details=f"Item {index}/{total}: {url}",
                        )
                        continue

                    self.after(0, lambda r=result: self.update_downloader_preview(r))
                    # Playlist quality behavior:
                    # - "Best Quality Separate" inspects EACH item independently
                    #   and uses that video's highest available resolution.
                    # - A manually selected resolution remains the user's ceiling
                    #   for every item, but the actual item resolution is resolved
                    #   independently so 720p-only items do not get pushed through
                    #   the 1080p+ FLAC/MKV workflow.
                    playlist_selected_format = self._selected_download_format
                    current_spec = self.selected_quality_spec(playlist_selected_format)
                    item_spec_override = None

                    if current_spec.get("best_per_item"):
                        self._last_quality_extractor_arg = None
                        item_quality_options = self.resolve_quality_options_for_result(result)
                        item_extractor_arg = self._last_quality_extractor_arg
                        # None is meaningful: it resets a fallback client used by
                        # the prior playlist item so each download matches its scan.
                        self._dl_youtube_extractor_arg = item_extractor_arg
                        result["quality_extractor_arg"] = item_extractor_arg
                        item_best = select_best_video_quality_spec(item_quality_options)

                        if not item_best or not item_best.get("height"):
                            raise RuntimeError(
                                f"No video format was available for playlist item {index}/{total}."
                            )

                        item_spec_override = dict(item_best)
                        item_spec_override["best_per_item"] = True

                    elif current_spec.get("kind") == "video" and current_spec.get("height"):
                        # Resolve the highest actual format at or below the user's
                        # requested ceiling for this specific playlist item.
                        self._last_quality_extractor_arg = None
                        item_quality_options = self.resolve_quality_options_for_result(result)
                        item_extractor_arg = self._last_quality_extractor_arg
                        # None is meaningful: it resets a fallback client used by
                        # the prior playlist item so each download matches its scan.
                        self._dl_youtube_extractor_arg = item_extractor_arg
                        result["quality_extractor_arg"] = item_extractor_arg
                        requested_height = int(current_spec.get("height") or 0)
                        item_spec_override = select_best_video_quality_spec(
                            item_quality_options,
                            maximum_height=requested_height,
                        )
                        if not item_spec_override:
                            raise RuntimeError(
                                f"No video format at or below {requested_height}p was available for playlist item {index}/{total}."
                            )

                    download_result = dict(result)
                    source_title = sanitize_filename(result.get("title") or "video")
                    # Keep playlist filenames clean and title-based. The unique-stem
                    # helper below handles duplicate titles without playlist numbering
                    # or exposing YouTube IDs in every filename.
                    download_result["output_filename"] = source_title[:180]
                    self._dl_playlist_progress_context = (index, total)
                    try:
                        downloaded = self.execute_download_for_result(
                            download_result,
                            item_index=index,
                            item_total=total,
                            selected_format_override=item_spec_override or playlist_selected_format,
                        )
                    finally:
                        self._dl_playlist_progress_context = None

                    self.append_log(
                        self.dl_log,
                        f"[{index}/{total}] finalized: {downloaded.name}",
                    )
                    playlist_stats["downloaded"] += 1

                # Do not display a false "Download complete" after silently
                # skipping every playlist entry during metadata resolution.
                if playlist_stats["downloaded"] == 0:
                    failed_meta = playlist_stats["metadata_failures"]
                    failed_resolution = playlist_stats["resolution_failures"]
                    raise RuntimeError(
                        "Playlist finished without saving any files. "
                        f"0/{total} items downloaded; {failed_meta} metadata lookups failed; "
                        f"{failed_resolution} items had no usable metadata. "
                        "Check the newest 'youtube_metadata' and 'download_playlist_metadata' "
                        f"logs in {FAILURE_LOG_DIR} for the underlying yt-dlp error."
                    )

            else:
                result, error = payload
                queue_item = getattr(self, "_queue_active_item", None)
                queued_meta = (
                    queue_item.get("playlist_metadata")
                    if queue_run and isinstance(queue_item, dict)
                    else None
                )
                if isinstance(queued_meta, dict):
                    resolver = self.ensure_resolver()
                    queued_result = resolver.direct_result_from_metadata(queued_meta)
                    expected_video_id = str(
                        (queue_item or {}).get("video_id")
                        or (queued_result or {}).get("video_id")
                        or ""
                    ).strip()
                    queued_video_id = str((queued_result or {}).get("video_id") or "").strip()

                    if queued_result and expected_video_id and queued_video_id == expected_video_id:
                        result = queued_result
                        error = None

                        if queue_item.get("ytmusic_liked_entry"):
                            result["source"] = "YouTube Music Liked Music (authenticated library)"
                            result["ytm_matched"] = True
                            result["ytmusic_liked_entry"] = True
                            result["quality_extractor_arg"] = LIKED_MUSIC_EXTRACTOR_ARG
                        elif queue_item.get("playlist_uses_ytm"):
                            try:
                                ytm_result = resolver.search(
                                    str(queued_meta.get("artist") or ""),
                                    str(queued_meta.get("title") or ""),
                                    str(queued_meta.get("album") or ""),
                                )
                            except Exception as match_exc:
                                ytm_result = None
                                write_failure_log(
                                    "queue_playlist_ytm_match",
                                    match_exc,
                                    details=f"Playlist track: {queue_item.get('title') or user_input}",
                                )

                            match_id = str((ytm_result or {}).get("video_id") or "").strip()
                            if ytm_result and match_id == expected_video_id:
                                result = dict(ytm_result)
                                result["video_id"] = expected_video_id
                                result["source_url"] = queued_meta.get("source_url") or user_input
                                result["requested_artist"] = queued_meta.get("artist") or ""
                                result["requested_title"] = queued_meta.get("title") or ""
                                result["playlist_source_locked"] = True
                            else:
                                result = queued_result

                used_ytm_matching = bool(result and result.get("ytm_matched"))

                if self.stop_requested:
                    raise DownloadCancelled("Download stopped by user.")

                if not result:
                    raise RuntimeError(error or "No result")

                self.after(0, lambda r=result: self.update_downloader_preview(r))

                current_source = user_input.strip()
                single_mode = self.downloader_quality_mode_for_source(current_source)
                queue_item = getattr(self, "_queue_active_item", None)
                queued_quality_is_locked = (
                    queue_run
                    and isinstance(queue_item, dict)
                    and isinstance(self._selected_download_format, dict)
                    and self._selected_download_format.get("kind") in {"video", "audio"}
                )
                quality_source_matches = (
                    queued_quality_is_locked
                    or (
                        single_mode == "single"
                        and self._dl_preview_quality_source == current_source
                        and self._dl_preview_mode == "single"
                    )
                )

                selected_spec = self.selected_quality_spec(self._selected_download_format)
                if selected_spec.get("best_per_item"):
                    selected_spec = {}

                if not quality_source_matches or not selected_spec:
                    self._last_quality_extractor_arg = None
                    quality_options = self.resolve_quality_options_for_result(result)
                    quality_options = self.sanitize_quality_options_for_mode(quality_options, "single")
                    if quality_options:
                        self._dl_preview_quality_options = quality_options
                        self._dl_preview_quality_source = current_source
                        self._dl_preview_mode = "single"
                        self._dl_youtube_extractor_arg = self._last_quality_extractor_arg
                        self._selected_download_format = quality_options[0][0]
                        self.after(0, lambda opts=quality_options, src=current_source: self.show_download_quality_selector(opts, animated=True, source_value=src, source_mode="single"))

                result["quality_extractor_arg"] = self._dl_youtube_extractor_arg
                self.execute_download_for_result(result, item_index=1, item_total=1)

            def finish_success():
                self.dl_progress.set(1.0)
                self.dl_progress_percent.configure(text="100%")
                self.set_operation_progress(
                    "dl",
                    100,
                    "Operation Successful",
                    taskbar=True,
                )
                self.set_label(self.dl_status, "Status: Operation Successful")

                if playlist_stats["total"]:
                    saved = playlist_stats["downloaded"]
                    total = playlist_stats["total"]
                    failed_meta = playlist_stats["metadata_failures"]
                    failed_resolution = playlist_stats["resolution_failures"]
                    skipped = failed_meta + failed_resolution
                    self.set_label(self.dl_status, f"Status: Playlist saved {saved}/{total} items")
                    if skipped:
                        message = (
                            f"Playlist processing finished: {saved}/{total} items saved. "
                            f"{failed_meta} metadata lookups failed; {failed_resolution} items "
                            "could not be resolved. See the Downloader activity and the latest "
                            f"logs in {FAILURE_LOG_DIR}."
                        )
                    else:
                        message = f"Playlist download complete: all {saved} items were saved."
                else:
                    message = (
                        "Download complete and YT Music metadata/artwork applied."
                        if used_ytm_matching
                        else "Download complete. Source YouTube metadata/artwork was used directly."
                    )
                if not queue_run:
                    messagebox.showinfo("Success", message)

            self._last_download_outcome = "success"
            self.after(0, finish_success)

        except DownloadCancelled as exc:
            self._last_download_outcome = "cancelled"
            self.append_log(self.dl_log, f"[CANCELLED] {exc}")
            self.set_operation_progress(
                "dl",
                self.dl_progress.get() * 100 if hasattr(self.dl_progress, "get") else 0,
                "Download stopped by user.",
                taskbar=False,
            )
            # Cancellation is user-requested, so it is not treated as a failure log.

        except Exception as exc:
            self._last_download_outcome = "failed"
            log_path = write_failure_log(
                "download_worker",
                exc,
                details=f"Input: {user_input}",
            )
            self.append_log(
                self.dl_log,
                f"[ERROR] {exc} | Failure log: {log_path or FAILURE_LOG_DIR}",
            )
            if not queue_run:
                self.after(
                    0,
                    lambda e=str(exc), p=(log_path or FAILURE_LOG_DIR): messagebox.showerror(
                        "Download Error",
                        f"{e}\n\nFailure log:\n{p}",
                    ),
                )
            self.set_operation_progress(
                "dl",
                0,
                "Download failed — failure log written",
                taskbar=False,
            )
            self.set_label(self.dl_status, "Status: Download failed")

        finally:
            self.stop_requested = False
            self.download_running = False
            if queue_run:
                self.set_header_status("● QUEUE", busy=True)
                self.taskbar_progress.set_state(2)
            else:
                self.set_header_status("● READY", busy=False)
                self.taskbar_progress.set_state(0)
            self.active_process = None
            self.after(0, self.reset_downloader_ui)


    # --------------------------------------------------------
    # PAUSE / RESUME / STOP
    # --------------------------------------------------------

    def toggle_pause(self):
        if self.stop_requested or not self.active_process:
            return

        try:
            import psutil
        except ImportError:
            messagebox.showwarning(
                "Notice",
                "Pause/resume requires the psutil package.",
            )
            return

        try:
            parent = psutil.Process(
                self.active_process.pid
            )
            processes = [
                parent,
                *parent.children(recursive=True),
            ]

            if not self.is_paused:
                for proc in processes:
                    try:
                        proc.suspend()
                    except Exception:
                        pass

                self.is_paused = True
                self.dl_pause.grid_forget()
                self.dl_resume.configure(
                    state="normal",
                )
                self.dl_resume.grid(
                    row=0,
                    column=1,
                    sticky="ew",
                    padx=4,
                )
                self.set_label(
                    self.dl_status,
                    "Status: Download Paused.",
                )
                self.taskbar_progress.set_state(8)
            else:
                for proc in processes:
                    try:
                        proc.resume()
                    except Exception:
                        pass

                self.is_paused = False
                self.dl_resume.grid_forget()
                self.dl_pause.configure(
                    state="normal",
                )
                self.dl_pause.grid(
                    row=0,
                    column=1,
                    sticky="ew",
                    padx=4,
                )
                self.set_label(
                    self.dl_status,
                    "Status: Resuming download...",
                )
                self.taskbar_progress.set_state(2)

        except Exception as exc:
            log_path = write_failure_log(
                "pause_resume",
                exc,
            )
            messagebox.showerror(
                "Pause/Resume Error",
                f"{exc}\n\nFailure log:\n{log_path or FAILURE_LOG_DIR}",
            )

    def stop_active_process(self):
        process = self.active_process

        if process and process.poll() is None:
            try:
                import psutil

                parent = psutil.Process(
                    process.pid
                )

                for child in parent.children(
                    recursive=True
                ):
                    try:
                        child.terminate()
                    except Exception:
                        pass

                try:
                    parent.terminate()
                except Exception:
                    pass

            except ImportError:
                try:
                    process.terminate()
                except Exception:
                    pass

        self.is_paused = False
        self.stop_requested = True
        self.set_label(
            self.dl_status,
            "Status: Stopping download...",
        )

    def reset_downloader_ui(self):
        self.is_paused = False
        self.active_process = None

        try:
            self._dl_preview_token += 1
            self._stop_loading_preview()
            if self._dl_preview_job:
                try:
                    self.after_cancel(self._dl_preview_job)
                except Exception:
                    pass
                self._dl_preview_job = None
            self._dl_preview_source = ""
            self._dl_preview_pil = None
        except Exception:
            pass

        try:
            self.hide_downloader_running_controls()
            self.dl_pause.configure(state="disabled")
            self.dl_resume.configure(state="disabled")
            self.dl_stop.configure(state="disabled")
            self.dl_start.configure(
                state="normal",
                text=" Start Download",
            )
            self.taskbar_progress.set_state(0)
        except Exception:
            pass


    # --------------------------------------------------------
    # METADATA TAB
    # --------------------------------------------------------

    def build_metadata_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)

        box = ctk.CTkFrame(
            tab,
            fg_color="#000000",
            corner_radius=24,
            border_width=1,
            border_color=APPLE_THEME_PALETTES.get(
                getattr(self, "appearance_mode", "dark"),
                APPLE_THEME_PALETTES["dark"],
            )["separator"],
        )
        box.grid(
            row=0,
            column=0,
            padx=18,
            pady=12,
            sticky="ew",
        )

        ctk.CTkLabel(
            box,
            text=" Metadata Rewriter",
            font=(APP_FONT, 16, "bold"),
            text_color="#ffffff",
        ).pack(
            anchor="w",
            padx=22,
            pady=(18, 2),
        )

        ctk.CTkLabel(
            box,
            text=(
                "Strips all writable metadata and keeps only contributing artist, album, and year"
            ),
            font=(APP_FONT, 11),
            text_color="#94a3b8",
            wraplength=720,
            justify="left",
        ).pack(
            anchor="w",
            padx=22,
            pady=(0, 12),
        )

        self.meta_path_row, self.meta_path_label = self.make_path_row(
            box,
            "metadata",
        )
        self.meta_path_row.pack(
            fill="x",
            padx=22,
            pady=(0, 10),
        )

        controls = ctk.CTkFrame(
            box,
            fg_color="transparent",
        )
        controls.pack(
            fill="x",
            padx=22,
            pady=(0, 14),
        )

        ctk.CTkLabel(
            controls,
            text="STRICT REWRITE  •  ARTIST  •  ALBUM  •  YEAR",
            font=(APP_FONT, 11, "bold"),
            text_color="#94a3b8",
            anchor="w",
        ).pack(
            side="left",
        )

        self.meta_start_row = ctk.CTkFrame(
            box,
            fg_color="transparent",
        )
        self.meta_start_row.pack(
            fill="x",
            padx=22,
            pady=(0, 12),
        )

        self.meta_start = ctk.CTkButton(
            self.meta_start_row,
            text=" Start Rewrite",
            command=self.start_metadata_rewrite,
            height=40,
            font=(APP_FONT, 13, "bold"),
            fg_color="transparent",
            hover_color="#1e293b",
            text_color="#ffffff",
            corner_radius=8,
        )
        self.meta_start.pack(
            fill="x",
            expand=True,
        )

        self.meta_status = ctk.CTkLabel(
            box,
            text="Status: Inactive",
            font=(APP_FONT, 12),
            text_color="#ffffff",
            anchor="w",
        )
        self.meta_status.pack(
            fill="x",
            padx=22,
            pady=(0, 8),
        )

        self.make_operation_meter(
            box,
            "meta",
            "Ready to rewrite metadata...",
        )

    def start_metadata_rewrite(self):
        folder = self.paths["metadata"]

        if not os.path.isdir(folder):
            messagebox.showerror(
                "Error",
                "Select a valid folder.",
            )
            return

        self.meta_start.configure(
            state="disabled",
            text=" Rewriting...",
        )
        self.show_operation_meter("meta")
        self.set_header_status("● REWRITING", busy=True)
        self.set_operation_progress(
            "meta",
            0,
            "Preparing metadata rewrite...",
        )

        threading.Thread(
            target=self.metadata_worker,
            daemon=True,
        ).start()


    def metadata_worker(self):
        try:
            resolver = self.ensure_resolver()
            files = list(Path(self.paths["metadata"]).rglob("*.flac"))
            if not files:
                raise RuntimeError("No FLAC files found.")

            total = len(files)
            for index, file_path in enumerate(files, 1):
                try:
                    self.set_collection_progress("meta", index, total, 0.03, f"[{index}/{total}] Reading {file_path.name}...")
                    flac = FLAC(file_path)
                    artists = flac.get("artist", [])
                    current_artist = (
                        ", ".join(str(x) for x in artists if str(x).strip())
                        if isinstance(artists, list)
                        else str(artists or "")
                    )
                    current_album = flac.get("album", [""])[0] if flac.get("album") else ""
                    current_title = flac.get("title", [""])[0] if flac.get("title") else ""
                    if not current_title:
                        current_title = derive_title_from_filename(file_path)

                    self.set_collection_progress("meta", index, total, 0.20, f"[{index}/{total}] Matching on YouTube Music...")
                    result = resolver.search(current_artist, current_title, current_album)
                    if not result:
                        raise RuntimeError("No YouTube Music match found")

                    self.set_collection_progress("meta", index, total, 0.62, f"[{index}/{total}] Rewriting metadata only — cover untouched...")
                    rewrite_flac_metadata_only(file_path, result)
                    self.set_collection_progress("meta", index, total, 0.95, f"[{index}/{total}] Finalizing file...")
                    self.set_collection_progress("meta", index, total, 1.0, f"[{index}/{total}] Complete — {file_path.name}")

                except Exception as exc:
                    log_path = write_failure_log(
                        "metadata_rewrite_item",
                        exc,
                        details=f"File: {file_path}",
                    )
                    self.set_collection_progress(
                        "meta",
                        index,
                        total,
                        1.0,
                        f"[{index}/{total}] Failed — log saved: {Path(log_path).name if log_path else 'YTDLP\\failure log'}",
                    )

                time.sleep(REQUEST_DELAY)

            self.set_operation_progress("meta", 100, "Operation Successful")
            self.after(0, lambda: messagebox.showinfo("Complete", "Metadata rewrite complete."))

        except Exception as exc:
            log_path = write_failure_log("metadata_worker", exc, details=f"Folder: {self.paths['metadata']}")
            self.set_operation_progress("meta", 0, f"Metadata rewrite failed — log saved to {log_path or FAILURE_LOG_DIR}")
            self.after(0, lambda e=str(exc), p=(log_path or FAILURE_LOG_DIR): messagebox.showerror("Metadata Error", f"{e}\n\nFailure log:\n{p}"))
        finally:
            self.set_header_status("● READY", busy=False)
            self.after(0, lambda: self.meta_start.configure(state="normal", text=" Start Rewrite"))


    # --------------------------------------------------------
    # COVER TAB
    # --------------------------------------------------------

    def build_cover_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)

        box = ctk.CTkFrame(
            tab,
            fg_color="#000000",
            corner_radius=24,
            border_width=1,
            border_color=APPLE_THEME_PALETTES.get(
                getattr(self, "appearance_mode", "dark"),
                APPLE_THEME_PALETTES["dark"],
            )["separator"],
        )
        box.grid(
            row=0,
            column=0,
            padx=18,
            pady=12,
            sticky="ew",
        )

        ctk.CTkLabel(
            box,
            text=" Cover Art Overwrite",
            font=(APP_FONT, 16, "bold"),
            text_color="#ffffff",
        ).pack(
            anchor="w",
            padx=22,
            pady=(18, 2),
        )

        ctk.CTkLabel(
            box,
            text=(
                "Album Artwork is obtained using YouTube query matches of current metadata"
            ),
            font=(APP_FONT, 11),
            text_color="#94a3b8",
        ).pack(
            anchor="w",
            padx=22,
            pady=(0, 12),
        )

        self.cover_path_row, self.cover_path_label = self.make_path_row(
            box,
            "cover",
        )
        self.cover_path_row.pack(
            fill="x",
            padx=22,
            pady=(0, 10),
        )

        controls = ctk.CTkFrame(
            box,
            fg_color="transparent",
        )
        controls.pack(
            fill="x",
            padx=22,
            pady=(0, 12),
        )

        self.cover_start = ctk.CTkButton(
            controls,
            text=" Start Cover Upgrade",
            command=self.start_cover_upgrade,
            width=180,
            height=38,
            font=(APP_FONT, 13, "bold"),
            fg_color="transparent",
            hover_color="#1e293b",
            text_color="#ffffff",
            corner_radius=8,
        )
        self.cover_start.pack(
            fill="x",
            expand=True,
        )

        self.cover_status = ctk.CTkLabel(
            box,
            text="Status: Inactive",
            font=(APP_FONT, 12),
            text_color="#ffffff",
            anchor="w",
        )
        self.cover_status.pack(
            fill="x",
            padx=22,
            pady=(0, 8),
        )

        self.make_operation_meter(
            box,
            "cover",
            "Ready to upgrade artwork...",
        )

    def start_cover_upgrade(self):
        folder = self.paths["cover"]

        if not os.path.isdir(folder):
            messagebox.showerror(
                "Error",
                "Select a valid folder.",
            )
            return

        self.cover_start.configure(
            state="disabled",
            text=" Upgrading...",
        )
        self.show_operation_meter("cover")
        self.set_header_status("● ARTWORK", busy=True)
        self.set_operation_progress(
            "cover",
            0,
            "Preparing artwork upgrade...",
        )

        threading.Thread(
            target=self.cover_worker,
            daemon=True,
        ).start()


    def cover_worker(self):
        try:
            resolver = self.ensure_resolver()
            files = list(Path(self.paths["cover"]).rglob("*.flac"))
            if not files:
                raise RuntimeError("No FLAC files found.")

            total = len(files)
            for index, file_path in enumerate(files, 1):
                try:
                    self.set_collection_progress("cover", index, total, 0.03, f"[{index}/{total}] Reading {file_path.name}...")
                    flac = FLAC(file_path)
                    artists = flac.get("artist", [])
                    artist = (
                        ", ".join(str(x) for x in artists if str(x).strip())
                        if isinstance(artists, list)
                        else str(artists or "")
                    )
                    title = flac.get("title", [""])[0] if flac.get("title") else derive_title_from_filename(file_path)
                    album = flac.get("album", [""])[0] if flac.get("album") else ""

                    self.set_collection_progress("cover", index, total, 0.22, f"[{index}/{total}] Matching current metadata...")
                    result = resolver.search(artist, title, album)
                    if not result:
                        raise RuntimeError("No YouTube Music match found")

                    self.set_collection_progress("cover", index, total, 0.52, f"[{index}/{total}] Fetching album artwork...")
                    raw, _, _ = inspect_image_from_url(result.get("cover_url"))
                    if not raw:
                        raise RuntimeError("Matched artwork could not be downloaded")

                    normalized = normalize_cover_to_jpeg(raw) or raw
                    self.set_collection_progress("cover", index, total, 0.78, f"[{index}/{total}] Replacing embedded artwork...")
                    flac.clear_pictures()
                    flac.add_picture(make_picture(normalized))
                    flac.save()
                    self.set_collection_progress("cover", index, total, 1.0, f"[{index}/{total}] Complete — {file_path.name}")

                except Exception as exc:
                    log_path = write_failure_log("cover_upgrade_item", exc, details=f"File: {file_path}")
                    self.set_collection_progress("cover", index, total, 1.0, f"[{index}/{total}] Failed — log saved: {Path(log_path).name if log_path else 'YTDLP\\failure log'}")

                time.sleep(REQUEST_DELAY)

            self.set_operation_progress("cover", 100, "Operation Successful")
            self.after(0, lambda: messagebox.showinfo("Complete", "Cover art upgrade complete."))

        except Exception as exc:
            log_path = write_failure_log("cover_worker", exc, details=f"Folder: {self.paths['cover']}")
            self.set_operation_progress("cover", 0, f"Cover upgrade failed — log saved to {log_path or FAILURE_LOG_DIR}")
            self.after(0, lambda e=str(exc), p=(log_path or FAILURE_LOG_DIR): messagebox.showerror("Cover Error", f"{e}\n\nFailure log:\n{p}"))
        finally:
            self.set_header_status("● READY", busy=False)
            self.after(0, lambda: self.cover_start.configure(state="normal", text=" Start Cover Overwrite"))


    # --------------------------------------------------------
    # CROP TAB
    # --------------------------------------------------------

    def build_crop_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)

        box = ctk.CTkFrame(
            tab,
            fg_color="#000000",
            corner_radius=24,
            border_width=1,
            border_color=APPLE_THEME_PALETTES.get(
                getattr(self, "appearance_mode", "dark"),
                APPLE_THEME_PALETTES["dark"],
            )["separator"],
        )
        box.grid(
            row=0,
            column=0,
            padx=18,
            pady=12,
            sticky="ew",
        )

        ctk.CTkLabel(
            box,
            text=" Cover Cropper",
            font=(APP_FONT, 16, "bold"),
            text_color="#ffffff",
        ).pack(
            anchor="w",
            padx=22,
            pady=(18, 2),
        )

        ctk.CTkLabel(
            box,
            text=(
                "Crops Existing Album Cover into a 1:1 ratio"
            ),
            font=(APP_FONT, 11),
            text_color="#94a3b8",
        ).pack(
            anchor="w",
            padx=22,
            pady=(0, 12),
        )

        self.crop_path_row, self.crop_path_label = self.make_path_row(
            box,
            "crop",
        )
        self.crop_path_row.pack(
            fill="x",
            padx=22,
            pady=(0, 10),
        )

        controls = ctk.CTkFrame(
            box,
            fg_color="transparent",
        )
        controls.pack(
            fill="x",
            padx=22,
            pady=(0, 12),
        )

        self.crop_start = ctk.CTkButton(
            controls,
            text=" Start Crop",
            command=self.start_crop,
            width=140,
            height=38,
            font=(APP_FONT, 13, "bold"),
            fg_color="transparent",
            hover_color="#1e293b",
            text_color="#ffffff",
            corner_radius=8,
        )
        self.crop_start.pack(
            fill="x",
            expand=True,
        )

        self.crop_status = ctk.CTkLabel(
            box,
            text="Status: Inactive",
            font=(APP_FONT, 12),
            text_color="#ffffff",
            anchor="w",
        )
        self.crop_status.pack(
            fill="x",
            padx=22,
            pady=(0, 8),
        )

        self.make_operation_meter(
            box,
            "crop",
            "Ready to crop artwork...",
        )

    def start_crop(self):
        folder = self.paths["crop"]

        if not os.path.isdir(folder):
            messagebox.showerror(
                "Error",
                "Select a valid folder.",
            )
            return

        self.crop_start.configure(
            state="disabled",
            text=" Cropping...",
        )
        self.show_operation_meter("crop")
        self.set_header_status("● CROPPING", busy=True)
        self.set_operation_progress(
            "crop",
            0,
            "Preparing cover crop...",
        )

        threading.Thread(
            target=self.crop_worker,
            daemon=True,
        ).start()


    def crop_worker(self):
        try:
            files = list(Path(self.paths["crop"]).rglob("*.flac"))
            if not files:
                raise RuntimeError("No FLAC files found.")

            total = len(files)
            for index, file_path in enumerate(files, 1):
                try:
                    self.set_collection_progress("crop", index, total, 0.05, f"[{index}/{total}] Inspecting {file_path.name}...")
                    self.set_collection_progress("crop", index, total, 0.30, f"[{index}/{total}] Cropping cover to 1:1...")
                    _, detail = crop_flac_cover(file_path)
                    self.set_collection_progress("crop", index, total, 1.0, f"[{index}/{total}] Complete — {detail}")
                except Exception as exc:
                    log_path = write_failure_log("crop_item", exc, details=f"File: {file_path}")
                    self.set_collection_progress("crop", index, total, 1.0, f"[{index}/{total}] Failed — log saved: {Path(log_path).name if log_path else 'YTDLP\\failure log'}")

            self.set_operation_progress("crop", 100, "Operation Successful")
            self.after(0, lambda: messagebox.showinfo("Complete", "Cover crop complete."))

        except Exception as exc:
            log_path = write_failure_log("crop_worker", exc, details=f"Folder: {self.paths['crop']}")
            self.set_operation_progress("crop", 0, f"Cover crop failed — log saved to {log_path or FAILURE_LOG_DIR}")
            self.after(0, lambda e=str(exc), p=(log_path or FAILURE_LOG_DIR): messagebox.showerror("Crop Error", f"{e}\n\nFailure log:\n{p}"))
        finally:
            self.set_header_status("● READY", busy=False)
            self.after(0, lambda: self.crop_start.configure(state="normal", text=" Start Crop"))


    # --------------------------------------------------------
    # LIBRARY PIPELINE TAB
    # --------------------------------------------------------

    def build_pipeline_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        box = ctk.CTkFrame(
            tab,
            fg_color="#000000",
            corner_radius=24,
            border_width=1,
            border_color=APPLE_THEME_PALETTES.get(
                getattr(self, "appearance_mode", "dark"),
                APPLE_THEME_PALETTES["dark"],
            )["separator"],
        )
        box.grid(
            row=0,
            column=0,
            padx=18,
            pady=12,
            sticky="ew",
        )

        ctk.CTkLabel(
            box,
            text=" Library Overhaul",
            font=(APP_FONT, 17, "bold"),
            text_color="#ffffff",
        ).pack(
            anchor="w",
            padx=22,
            pady=(18, 2),
        )

        ctk.CTkLabel(
            box,
            text=(
                "Strict metadata cleanup + YT Music matching in one "
            ),
            font=(APP_FONT, 11),
            text_color="#94a3b8",
            wraplength=720,
            justify="left",
        ).pack(
            anchor="w",
            padx=22,
            pady=(0, 12),
        )

        self.pipeline_path_row, self.pipeline_path_label = self.make_path_row(
            box,
            "pipeline",
        )
        self.pipeline_path_row.pack(
            fill="x",
            padx=22,
            pady=(0, 10),
        )

        controls = ctk.CTkFrame(
            box,
            fg_color="transparent",
        )
        controls.pack(
            fill="x",
            padx=22,
            pady=(0, 15),
        )

        self.pipeline_start = ctk.CTkButton(
            controls,
            text=" Start Overhaul",
            command=self.start_pipeline,
            width=190,
            height=40,
            font=(APP_FONT, 13, "bold"),
            fg_color="transparent",
            hover_color="#1e293b",
            text_color="#ffffff",
            corner_radius=8,
        )
        self.pipeline_start.pack(
            fill="x",
            expand=True,
        )

        self.pipeline_status = ctk.CTkLabel(
            box,
            text="Status: Inactive",
            font=(APP_FONT, 12),
            text_color="#ffffff",
            anchor="w",
        )
        self.pipeline_status.pack(
            fill="x",
            padx=22,
            pady=(0, 8),
        )

        self.make_operation_meter(
            box,
            "pipeline",
            "Ready for full library overhaul...",
        )

        self.pipeline_log = ctk.CTkTextbox(
            tab,
            height=270,
            font=(APP_FONT, 10),
            fg_color="#000000",
            text_color="#d1d5db",
            corner_radius=12,
        )
        self.pipeline_log.grid(
            row=1,
            column=0,
            padx=18,
            pady=(0, 12),
            sticky="nsew",
        )
        self.pipeline_log.configure(
            state="disabled"
        )
        self.pipeline_console_panel = self.pipeline_log
        self.pipeline_console_tab = tab
        self.pipeline_console_row = 1
        self.hide_activity_console("pipeline")

    def start_pipeline(self):
        folder = self.paths["pipeline"]

        if not os.path.isdir(folder):
            messagebox.showerror(
                "Error",
                "Select a valid folder.",
            )
            return

        self.pipeline_start.configure(
            state="disabled",
            text=" Processing...",
        )
        self.show_operation_meter("pipeline")
        self.show_activity_console("pipeline")
        self.set_header_status("● OVERHAUL", busy=True)
        self.set_operation_progress(
            "pipeline",
            0,
            "Preparing library overhaul...",
        )

        threading.Thread(
            target=self.pipeline_worker,
            daemon=True,
        ).start()


    def pipeline_worker(self):
        try:
            resolver = self.ensure_resolver()
            files = list(Path(self.paths["pipeline"]).rglob("*.flac"))
            if not files:
                raise RuntimeError("No FLAC files found.")

            total = len(files)
            for index, file_path in enumerate(files, 1):
                self.append_log(self.pipeline_log, f"[{index}/{total}] {file_path.name}")
                try:
                    self.set_collection_progress("pipeline", index, total, 0.03, f"[{index}/{total}] Reading {file_path.name}...")
                    flac = FLAC(file_path)
                    artists = flac.get("artist", [])
                    artist = (
                        ", ".join(str(x) for x in artists if str(x).strip())
                        if isinstance(artists, list)
                        else str(artists or "")
                    )
                    album = flac.get("album", [""])[0] if flac.get("album") else ""
                    title = flac.get("title", [""])[0] if flac.get("title") else derive_title_from_filename(file_path)

                    self.set_collection_progress("pipeline", index, total, 0.20, f"[{index}/{total}] Matching on YouTube Music...")
                    result = resolver.search(artist, title, album)
                    if not result:
                        raise RuntimeError("No YouTube Music match found")

                    self.append_log(self.pipeline_log, "  source: " + result.get("source", ""))
                    self.append_log(self.pipeline_log, "  artist: " + result.get("artist", ""))
                    self.append_log(self.pipeline_log, "  title: " + result.get("title", ""))

                    replacement_cover_bytes = None
                    self.set_collection_progress("pipeline", index, total, 0.42, f"[{index}/{total}] Fetching matched album artwork...")
                    if result.get("cover_url"):
                        raw, _, _ = inspect_image_from_url(result.get("cover_url"))
                        if raw:
                            replacement_cover_bytes = raw

                    self.set_collection_progress("pipeline", index, total, 0.62, f"[{index}/{total}] Rewriting metadata while preserving artwork...")
                    rewrite_flac_metadata_strict(
                        file_path,
                        result,
                        replacement_cover_bytes=replacement_cover_bytes,
                    )

                    self.set_collection_progress("pipeline", index, total, 0.86, f"[{index}/{total}] Finalizing artwork shape...")
                    try:
                        crop_flac_cover(file_path)
                    except Exception as crop_exc:
                        log_path = write_failure_log(
                            "pipeline_cover_crop",
                            crop_exc,
                            details=f"File: {file_path}",
                        )
                        self.append_log(
                            self.pipeline_log,
                            f"  cover crop warning: {crop_exc} | Failure log: {log_path or FAILURE_LOG_DIR}",
                        )

                    self.set_collection_progress("pipeline", index, total, 0.95, f"[{index}/{total}] Finalizing file...")
                    self.set_collection_progress("pipeline", index, total, 1.0, f"[{index}/{total}] Complete — {file_path.name}")

                except Exception as exc:
                    log_path = write_failure_log("pipeline_item", exc, details=f"File: {file_path}")
                    self.append_log(self.pipeline_log, f"  ERROR: {exc} | Failure log: {log_path or FAILURE_LOG_DIR}")
                    self.set_collection_progress("pipeline", index, total, 1.0, f"[{index}/{total}] Failed — log saved: {Path(log_path).name if log_path else 'YTDLP\\failure log'}")

                time.sleep(REQUEST_DELAY)

            self.set_operation_progress("pipeline", 100, "Operation Successful")
            self.after(0, lambda: messagebox.showinfo("Complete", "Library overhaul complete."))

        except Exception as exc:
            log_path = write_failure_log("pipeline_worker", exc, details=f"Folder: {self.paths['pipeline']}")
            self.set_operation_progress("pipeline", 0, f"Library overhaul failed — log saved to {log_path or FAILURE_LOG_DIR}")
            self.after(0, lambda e=str(exc), p=(log_path or FAILURE_LOG_DIR): messagebox.showerror("Pipeline Error", f"{e}\n\nFailure log:\n{p}"))
        finally:
            self.hide_activity_console("pipeline")
            self.set_header_status("● READY", busy=False)
            self.after(0, lambda: self.pipeline_start.configure(state="normal", text=" Start Full Overhaul"))



# ============================================================
# V3 ULTIMATE FORMAT / RELIABILITY LAYER
# ============================================================
# This layer extends the V2 build without replacing Codex's UI/animation
# architecture. It adds independent File Type + File Quality controls,
# per-type audio quality presets, stricter format routing, retries,
# collision-safe output naming, dry-run inspection, validation, history,
# performance controls, and a lightweight queue.

FILE_TYPE_OPTIONS_V3 = [
    (" Auto (Recommended)", "auto"),
    (" MP4 Video", "mp4"),
    (" MKV Video", "mkv"),
    (" MP3 Audio", "mp3"),
    (" M4A / AAC Audio", "m4a"),
    (" Opus Audio", "opus"),
    (" Vorbis / OGG Audio", "vorbis"),
    (" FLAC Audio", "flac"),
    (" WAV PCM Audio", "wav"),
]
FILE_TYPE_BY_LABEL_V3 = {label: value for label, value in FILE_TYPE_OPTIONS_V3}
FILE_LABEL_BY_TYPE_V3 = {value: label for label, value in FILE_TYPE_OPTIONS_V3}
VIDEO_FILE_TYPES_V3 = {"auto", "mp4", "mkv"}
AUDIO_FILE_TYPES_V3 = {"mp3", "m4a", "opus", "vorbis", "flac", "wav"}
LOSSLESS_AUDIO_TYPES_V3 = {"flac", "wav"}
AUDIO_BITRATES_V3 = {
    "mp3": [64, 96, 128, 160, 192, 224, 256, 320],
    "m4a": [64, 96, 128, 160, 192, 256, 320],
    "opus": [48, 64, 96, 128, 160, 192, 256, 320],
    "vorbis": [64, 96, 128, 160, 192, 256, 320],
}


def _v3_file_type_id(label):
    return FILE_TYPE_BY_LABEL_V3.get(str(label or ""), "auto")


def _v3_audio_quality_options(file_type):
    file_type = str(file_type or "").lower()
    if file_type in LOSSLESS_AUDIO_TYPES_V3:
        return [(
            {"flac": "Lossless — FLAC", "alac": "Lossless — ALAC", "wav": "Lossless — PCM WAV"}[file_type],
            {"kind": "audio", "audio_format": file_type, "quality": None, "lossless": True, "file_type": file_type},
        )]
    return [
        (f" {rate} kbps", {"kind": "audio", "audio_format": file_type, "quality": f"{rate}K", "bitrate": rate, "lossless": False, "file_type": file_type})
        for rate in sorted(AUDIO_BITRATES_V3.get(file_type, []), reverse=True)
    ]


def _v3_video_quality_options(formats, file_type, mode="single"):
    file_type = str(file_type or "auto").lower()
    if mode == "playlist":
        out = [("Best Option Separate", {"kind": "video", "best_per_item": True, "file_type": file_type})]
        for height, label in sorted(VIDEO_QUALITY_LABELS.items(), reverse=True):
            out.append((label, {"kind": "video", "height": height, "best": False, "file_type": file_type}))
        return out
    heights = detected_video_heights(formats)
    if not heights:
        return []
    highest = heights[0]
    out = [(f" Best Quality — {highest}p", {"kind": "video", "height": highest, "best": True, "file_type": file_type})]
    for height in heights[1:]:
        out.append((VIDEO_QUALITY_LABELS.get(height, f" {height}P"), {"kind": "video", "height": height, "best": False, "file_type": file_type}))
    return out


def _v3_quality_options(formats, file_type, mode="single"):
    file_type = str(file_type or "auto").lower()
    if file_type in AUDIO_FILE_TYPES_V3:
        return _v3_audio_quality_options(file_type)
    return _v3_video_quality_options(formats, file_type, mode)


def _v3_unique_stem(output_dir, title, extensions):
    base = sanitize_filename(title)
    folder = Path(output_dir)
    existing = {p.name.lower() for p in folder.iterdir()} if folder.exists() else set()
    if not any(f"{base}{ext}".lower() in existing for ext in extensions):
        return base
    i = 1
    while True:
        candidate = f"{base} ({i})"
        if not any(f"{candidate}{ext}".lower() in existing for ext in extensions):
            return candidate
        i += 1


def _v3_validate_output(file_path, kind):
    path = Path(file_path)
    if not path.exists() or path.stat().st_size <= 0:
        raise RuntimeError(f"Output is missing or empty: {path}")
    if kind == "audio":
        suffix = path.suffix.lower()
        if suffix == ".flac":
            audio = FLAC(path)
            if not audio.info or audio.info.length <= 0:
                raise RuntimeError(f"Invalid FLAC output: {path.name}")
            return True
        if suffix == ".mp3":
            ID3(path)
            return True
    ffprobe = find_executable("ffprobe") or "ffprobe"
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        **get_hidden_subprocess_kwargs(),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe validation failed: {path.name}")
    streams = json.loads(proc.stdout or "{}").get("streams", [])
    if kind == "video" and not any(s.get("codec_type") == "video" for s in streams):
        raise RuntimeError(f"No video stream found in {path.name}")
    if kind == "audio" and not any(s.get("codec_type") == "audio" for s in streams):
        raise RuntimeError(f"No audio stream found in {path.name}")
    return True


def _v3_history(entry):
    try:
        ensure_failure_log_dir()
        path = Path(FAILURE_LOG_DIR) / "operation_history.json"
        data = []
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    data = loaded
            except Exception:
                data = []
        safe = dict(entry or {})
        safe["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        data.append(safe)
        path.write_text(json.dumps(data[-250:], indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ---- resolver preview: preserve the already-inspected format universe ----
_ORIGINAL_RESOLVER_PREVIEW_V3 = YTMResolver.preview_from_url


def _v3_public_metadata_preview(url):
    """Fallback title/artwork preview when yt-dlp cannot inspect YouTube formats."""
    if is_playlist_url(url):
        return None
    try:
        response = session.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
        title = str(payload.get("title") or "").strip()
        if not title:
            return None

        thumbnail_candidates = []
        thumbnail = str(payload.get("thumbnail_url") or "").strip()
        if thumbnail:
            candidate = canonicalize_thumbnail_url(thumbnail)
            if candidate:
                thumbnail_candidates.append(candidate)
        for candidate in youtube_thumbnail_candidates(url):
            if candidate and candidate not in thumbnail_candidates:
                thumbnail_candidates.append(candidate)

        write_failure_log(
            "preview_metadata_fallback",
            RuntimeError("yt-dlp format inspection failed; loaded public oEmbed metadata instead"),
            details=f"URL: {url}\nTitle: {title}",
        )
        return {
            "title": title,
            "cover_url": thumbnail_candidates[0] if thumbnail_candidates else "",
            "thumbnail_candidates": thumbnail_candidates,
            "quality_options": AUDIO_DOWNLOAD_OPTIONS.copy(),
            "formats": [],
            "youtube_extractor_arg": None,
            "is_playlist": False,
            "metadata_only_fallback": True,
        }
    except Exception as exc:
        write_failure_log(
            "preview_oembed_fallback",
            exc,
            details=f"URL: {url}",
        )
        return None


def _v3_resolver_preview(url):
    preview = _ORIGINAL_RESOLVER_PREVIEW_V3(url)
    if not preview:
        preview = _v3_public_metadata_preview(url)
        if not preview:
            return None

    if not preview.get("is_playlist"):
        if preview.get("metadata_only_fallback"):
            preview["formats"] = []
            preview["quality_options"] = AUDIO_DOWNLOAD_OPTIONS.copy()
        else:
            try:
                _data, formats, extractor_arg = inspect_youtube_info(url, timeout=45)
                preview["formats"] = formats
                preview["youtube_extractor_arg"] = extractor_arg
            except Exception as exc:
                write_failure_log("v3_preview_format_cache", exc, details=f"URL: {url}")
                preview["formats"] = []
                if not preview.get("quality_options"):
                    preview["quality_options"] = AUDIO_DOWNLOAD_OPTIONS.copy()
    else:
        preview["formats"] = []
    return preview


YTMResolver.preview_from_url = staticmethod(_v3_resolver_preview)


# ---- downloader UI extension ----
_ORIGINAL_BUILD_DOWNLOADER_TAB_V3 = YTMMusicToolkit.build_downloader_tab
_ORIGINAL_START_DOWNLOAD_V3 = YTMMusicToolkit.start_download
_ORIGINAL_RUN_WORKER_V3 = YTMMusicToolkit.run_download_worker
_ORIGINAL_BUILD_COMMAND_V3 = YTMMusicToolkit.build_yt_dlp_command
_ORIGINAL_POSTPROCESS_V3 = YTMMusicToolkit.postprocess_downloaded_file
_ORIGINAL_EXECUTE_V3 = YTMMusicToolkit.execute_download_for_result
_ORIGINAL_IS_LOSSLESS_V3 = YTMMusicToolkit.is_lossless_video_mode
_ORIGINAL_APPLY_PREVIEW_V3 = YTMMusicToolkit.apply_silent_link_preview


def _v3_build_downloader_tab(self, tab):
    _ORIGINAL_BUILD_DOWNLOADER_TAB_V3(self, tab)
    try:
        options = self.dl_quality_label.master
        options.grid_columnconfigure(0, weight=1)
        options.grid_columnconfigure(1, weight=1)

        self._v3_selected_file_type = "auto"
        self._v3_selected_file_quality = ""
        self._v3_preview_formats = []
        self._v3_queue = []

        self.dl_file_type_label = ctk.CTkLabel(options, text=" File Type", font=(APP_FONT, 15, "bold"), text_color="#ffffff")
        self.dl_file_type = ctk.CTkComboBox(
            options,
            values=[label for label, _ in FILE_TYPE_OPTIONS_V3],
            state="readonly",
            fg_color="#050505", text_color="#ffffff", button_color="#1e293b", button_hover_color="#334155",
            dropdown_fg_color="#000000", dropdown_text_color="#ffffff", corner_radius=8,
            font=(APP_FONT, 14), dropdown_font=(APP_FONT, 14), height=42,
            command=self._v3_file_type_changed,
        )
        self.dl_file_type.set(FILE_LABEL_BY_TYPE_V3["auto"])

        # Reuse V2's quality combo but move it into the right-hand column.
        self.dl_quality_label.configure(text=" File Quality")

        utility = ctk.CTkFrame(options, fg_color="transparent")
        utility.grid(row=5, column=0, columnspan=2, sticky="ew", padx=22, pady=(0, 8))
        utility.grid_columnconfigure(0, weight=1)
        utility.grid_columnconfigure(1, weight=1)

        self.dl_dry_run = StringVar(value="0")
        ctk.CTkCheckBox(utility, text="Inspect only (dry run)", variable=self.dl_dry_run, onvalue="1", offvalue="0", font=(APP_FONT, 11), text_color="#cbd5e1").grid(row=0, column=0, sticky="w")

        self.dl_performance = ctk.CTkComboBox(
            utility, values=["Balanced", "Conservative", "Aggressive"], state="readonly", height=32,
            font=(APP_FONT, 11), dropdown_font=(APP_FONT, 11), fg_color="#050505",
            button_color="#1e293b", button_hover_color="#334155", dropdown_fg_color="#000000",
            dropdown_text_color="#ffffff", text_color="#ffffff",
            command=lambda value: self._v3_set_performance(value),
        )
        self.dl_performance.set({"balanced": "Balanced", "conservative": "Conservative", "aggressive": "Aggressive"}.get(self.performance_mode, "Balanced"))
        self.dl_performance.grid(row=0, column=1, sticky="ew")

        ctk.CTkButton(utility, text="ⓘ Inspect Details", width=120, height=32, font=(APP_FONT, 10, "bold"), fg_color="transparent", hover_color="#1e293b", text_color="#cbd5e1", command=self._v3_show_media_details).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ctk.CTkButton(utility, text="＋ Queue", width=85, height=32, font=(APP_FONT, 10, "bold"), fg_color="transparent", hover_color="#1e293b", text_color="#cbd5e1", command=self._v3_queue_current).grid(row=1, column=1, sticky="w", pady=(6, 0))
        self.dl_queue_count = ctk.CTkLabel(utility, text="Queue: 0", font=(APP_FONT, 10, "bold"), text_color="#64748b")
        self.dl_queue_count.grid(row=1, column=1, sticky="e", pady=(6, 0))

        # Move the existing Save To row down one row.
        self.dl_path_row.grid_configure(row=6)

        # Hide the original selector until preview/inspection is ready.
        self.hide_download_quality_selector()
    except Exception as exc:
        write_failure_log("v3_downloader_ui", exc)


def _v3_hide_selector(self):
    self._dl_quality_visible = False
    self._dl_preview_quality_options = []
    self._dl_preview_quality_source = ""
    self._dl_preview_quality_mode = "none"
    self._v3_selected_file_quality = ""
    try:
        self.dl_file_type_label.grid_remove()
        self.dl_file_type.grid_remove()
        self.dl_quality_label.grid_remove()
        self.dl_format.grid_remove()
        self.dl_format.configure(values=[])
        self.dl_format.set("")
    except Exception:
        pass


def _v3_file_type_changed(self, selected_label=None):
    try:
        label = str(selected_label or self.dl_file_type.get())
        file_type = _v3_file_type_id(label)
        self._v3_selected_file_type = file_type
        mode = self.downloader_quality_mode_for_source(self._dl_preview_quality_source or self.dl_input.get())
        quality_options = _v3_quality_options(self._v3_preview_formats, file_type, mode if mode in {"single", "playlist"} else "single")
        self._dl_preview_quality_options = quality_options
        values = [label for label, _ in quality_options]
        if values:
            if mode == "playlist" and file_type in VIDEO_FILE_TYPES_V3:
                default = "Best Option Separate"
            else:
                default = values[0]
            self.dl_format.configure(values=values)
            self.dl_format.set(default)
            self._v3_selected_file_quality = default
        if not self._dl_preview_quality_source:
            _v3_hide_selector(self)
            return
        self.dl_file_type_label.grid(row=0, column=0, sticky="w", padx=22, pady=(14, 4))
        self.dl_file_type.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 8))
        if file_type in LOSSLESS_AUDIO_TYPES_V3:
            self.dl_quality_label.grid_remove()
            self.dl_format.grid_remove()
        else:
            self.dl_quality_label.grid(row=0, column=1, sticky="w", padx=22, pady=(14, 4))
            self.dl_format.grid(row=1, column=1, sticky="ew", padx=22, pady=(0, 8))
        self._dl_quality_visible = bool(values)
    except Exception as exc:
        write_failure_log("v3_file_type_change", exc)


def _v3_show_selector(self, quality_options=None, animated=True, source_value="", source_mode=None):
    source_value = str(source_value or self._dl_preview_quality_source or self.dl_input.get()).strip()
    mode = self.downloader_quality_mode_for_source(source_value)
    if mode not in {"single", "playlist"}:
        _v3_hide_selector(self)
        return
    self._dl_preview_quality_source = source_value
    self._dl_preview_quality_mode = mode
    try:
        self.dl_file_type.set(FILE_LABEL_BY_TYPE_V3.get(self._v3_selected_file_type, FILE_LABEL_BY_TYPE_V3["auto"]))
        _v3_file_type_changed(self, self.dl_file_type.get())
        if mode == "playlist" and self._v3_selected_file_type in VIDEO_FILE_TYPES_V3:
            opts = _v3_quality_options(self._v3_preview_formats, self._v3_selected_file_type, "playlist")
            self._dl_preview_quality_options = opts
            self.dl_format.configure(values=[label for label, _ in opts])
            self.dl_format.set("Best Option Separate")
            self._v3_selected_file_quality = "Best Option Separate"
        elif self._v3_selected_file_type in LOSSLESS_AUDIO_TYPES_V3:
            self.dl_quality_label.grid_remove()
            self.dl_format.grid_remove()
        self._dl_quality_visible = True
    except Exception as exc:
        write_failure_log("v3_show_selector", exc, details=f"Source: {source_value}")
        _v3_hide_selector(self)
        return
    if animated:
        self._animate("v3-quality-selector", 360, lambda amount: None)


def _v3_selected_quality_spec(self, selected_format=None):
    if isinstance(selected_format, dict):
        return dict(selected_format)
    label = str(selected_format or self._v3_selected_file_quality or self.dl_format.get() or "").strip()
    for option_label, spec in self._dl_preview_quality_options or []:
        if option_label == label:
            return dict(spec)
    return {}


def _v3_apply_preview(self, preview):
    preview_formats = preview.get("formats") or []
    if preview.get("is_playlist"):
        playlist_heights = set()
        for item in preview.get("quality_inventory") or []:
            for value in item.get("heights") or []:
                try:
                    height = int(value)
                except (TypeError, ValueError):
                    continue
                if height > 0:
                    playlist_heights.add(height)
        preview_formats = [
            {"height": height, "vcodec": "preview", "format_id": f"preview_{height}p"}
            for height in sorted(playlist_heights, reverse=True)
        ]

    self._v3_preview_formats = preview_formats
    self._v3_preview_formats_ready = bool(self._v3_preview_formats)
    _ORIGINAL_APPLY_PREVIEW_V3(self, preview)

    if preview.get("metadata_only_fallback"):
        try:
            self.dl_status.configure(
                text="Status: Preview loaded; video qualities appear when format inspection succeeds. Audio options remain available."
            )
        except Exception:
            pass


def _v3_start_download(self):
    # Capture the second dropdown explicitly, then let V2's worker architecture do the heavy lifting.
    if self.download_running:
        return
    current = self.dl_input.get().strip()
    if not current:
        return _ORIGINAL_START_DOWNLOAD_V3(self)
    try:
        file_type = _v3_file_type_id(self.dl_file_type.get()) if getattr(self, "dl_file_type", None) else "auto"
        quality = self.dl_format.get().strip() if getattr(self, "dl_format", None) and self._dl_quality_visible else ""
        if file_type in LOSSLESS_AUDIO_TYPES_V3:
            quality = _v3_audio_quality_options(file_type)[0][0]
        if self.downloader_quality_mode_for_source(current) == "playlist" and file_type in VIDEO_FILE_TYPES_V3:
            quality = quality or "Best Option Separate"
        self._v3_selected_file_type = file_type
        self._v3_selected_file_quality = quality
        self._selected_download_format = quality
        self._selected_file_type = file_type
        self._selected_file_quality = quality
        self._v3_dry_run_active = bool(getattr(self, "dl_dry_run", StringVar(value="0")).get() == "1")
    except Exception:
        self._v3_selected_file_type = "auto"
        self._selected_file_quality = ""
        self._selected_download_format = ""
        self._v3_dry_run_active = False
    _ORIGINAL_START_DOWNLOAD_V3(self)


def _v3_run_worker(self, user_input):
    if getattr(self, "_v3_dry_run_active", False):
        try:
            mode, payload = self.resolve_for_download(user_input)
            self.set_operation_progress("dl", 40, "Inspecting source formats...", taskbar=True)
            if mode == "single":
                result, error = payload
                if not result:
                    raise RuntimeError(error or "No result")
                formats, extractor_arg = inspect_youtube_formats(result.get("source_url") or f"https://www.youtube.com/watch?v={result.get('video_id')}", timeout=45)
                self._v3_preview_formats = formats
                self._dl_youtube_extractor_arg = extractor_arg
                opts = _v3_quality_options(formats, self._v3_selected_file_type, "single")
                self._dl_preview_quality_options = opts
                self.after(0, lambda: self._v3_show_selector(opts, animated=True, source_value=user_input, source_mode="single"))
            else:
                self.set_operation_progress("dl", 85, "Playlist inspection complete — no files downloaded.", taskbar=True)
            self.set_operation_progress("dl", 100, "Inspection Complete", taskbar=True)
            _v3_history({"operation": "dry_run", "input": user_input, "result": "inspected_only", "file_type": self._v3_selected_file_type})
        except Exception as exc:
            log_path = write_failure_log("v3_dry_run", exc, details=f"Input: {user_input}")
            self.set_operation_progress("dl", 0, f"Inspection failed — {log_path or FAILURE_LOG_DIR}", taskbar=False)
        finally:
            self.download_running = False
            self.stop_requested = False
            self.after(0, self.reset_downloader_ui)
        return
    return _ORIGINAL_RUN_WORKER_V3(self, user_input)


def _v3_build_command(self, source_url, result, selected_format):
    spec = _v3_selected_quality_spec(self, selected_format)
    if not spec:
        return _ORIGINAL_BUILD_COMMAND_V3(self, source_url, result, selected_format)

    output_dir = self.paths["downloader"]
    file_type = str(spec.get("file_type") or getattr(self, "_v3_selected_file_type", "auto")).lower()
    title = sanitize_filename(result.get("output_filename") or result.get("title") or "track")
    command = [
        get_ytdlp_command(),
        *get_ytdlp_runtime_args(getattr(self, "performance_mode", "aggressive")),
        "--newline", "--windows-filenames",
        "--concurrent-fragments", str(get_concurrent_fragment_count(getattr(self, "performance_mode", "aggressive"))),
        "--retries", "10", "--fragment-retries", "10", "--retry-sleep", "exp=1:30",
        "--no-overwrites", "--format-sort", "res,fps,hdr:12,vcodec,channels,acodec,size,br,asr,proto,ext",
    ]
    command.extend(get_browser_cookie_args(source_url))
    extractor_arg = result.get("quality_extractor_arg") or getattr(self, "_dl_youtube_extractor_arg", None) or getattr(self, "_last_quality_extractor_arg", None)
    command.extend(youtube_extractor_args_list(extractor_arg))

    if spec.get("kind") == "audio":
        audio_format = spec.get("audio_format") or "flac"
        command.extend(["-x", "--audio-format", audio_format])
        if spec.get("quality"):
            command.extend(["--audio-quality", spec["quality"]])
    elif spec.get("kind") == "video":
        height = int(spec.get("height") or 0)
        if not height:
            raise RuntimeError("The selected video quality has no resolution")
        if file_type == "mp4" or (file_type == "auto" and height <= 720):
            selector = f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        else:
            selector = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        container = "mp4" if file_type == "auto" and height <= 720 else file_type
        command.extend(["-f", selector, "--merge-output-format", container])
    else:
        raise RuntimeError("No valid download type selected")

    if getattr(self, "_selected_download_subtitles", False) and spec.get("kind") == "video" and file_type in {"mp4", "mkv", "webm"}:
        command.extend(["--write-sub", "--write-auto-sub", "--embed-subs", "--sub-lang", "en,ar"])
    command.extend(["-o", os.path.join(output_dir, f"{title}.%(ext)s"), "--", source_url])
    return command


def _v3_is_lossless_video(self, selected_format):
    spec = _v3_selected_quality_spec(self, selected_format)
    if spec.get("kind") != "video":
        return False
    try:
        h = int(spec.get("height") or 0)
    except Exception:
        return False
    ft = str(spec.get("file_type") or getattr(self, "_v3_selected_file_type", "auto"))
    return h >= 1080 and ft in {"auto", "mkv"}


def _v3_postprocess(self, file_path, result, progress_callback=None, thumbnail_path=None):
    def report(frac, msg):
        if progress_callback:
            progress_callback(max(0.0, min(1.0, frac)), msg)
    try:
        suffix = Path(file_path).suffix.lower()
        cover_bytes = result.get("downloaded_thumbnail_bytes")
        if suffix == ".flac":
            write_flac_metadata(file_path, result, cover_bytes=cover_bytes, wipe_tags=False)
        elif suffix in {".mp3", ".m4a", ".opus", ".ogg", ".oga", ".wav"}:
            write_generic_audio_metadata(file_path, result, cover_bytes=cover_bytes)
        elif suffix in {".mp4", ".mov"} and thumbnail_path:
            report(0.75, "Binding video thumbnail...")
            self.embed_mp4_video_thumbnail(file_path, thumbnail_path)
        elif suffix == ".mkv" and thumbnail_path:
            report(0.75, "Binding video thumbnail...")
            self._v3_embed_mkv_thumbnail(file_path, thumbnail_path)
        report(1.0, "Metadata + artwork complete")
        return Path(file_path)
    except Exception as exc:
        log_path = write_failure_log("v3_postprocess", exc, details=f"File: {file_path}")
        raise RuntimeError(f"Media post-processing failed. Failure log: {log_path or FAILURE_LOG_DIR}") from exc


def _v3_embed_mkv_thumbnail(self, file_path, thumbnail_path):
    source = Path(file_path)
    temp = source.with_name(source.stem + ".cover.tmp.mkv")
    ffmpeg = get_ffmpeg_command()
    command = [ffmpeg, "-y", "-i", str(source), "-map", "0", "-c", "copy", "-attach", str(thumbnail_path), "-metadata:s:t:0", "mimetype=image/jpeg", "-metadata:s:t:0", "filename=cover.jpg", "-metadata:s:t:0", "title=Cover Art", str(temp)]
    proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, **get_hidden_subprocess_kwargs())
    if proc.returncode != 0 or not temp.exists():
        raise RuntimeError(f"FFmpeg MKV thumbnail embedding failed: {proc.stderr[-1200:]}")
    os.replace(temp, source)
    if not _v3_verify_mkv_attachment(source):
        raise RuntimeError("Final MKV thumbnail attachment could not be verified")


def _v3_verify_mkv_attachment(path):
    ffprobe = find_executable("ffprobe") or "ffprobe"
    proc = subprocess.run([ffprobe, "-v", "error", "-show_entries", "stream=index,codec_type:stream_tags=mimetype,filename", "-show_entries", "format_tags=title", "-of", "json", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, **get_hidden_subprocess_kwargs())
    if proc.returncode != 0:
        return False
    payload = json.loads(proc.stdout or "{}")
    streams = payload.get("streams", [])
    return any(str(s.get("codec_type") or "") == "attachment" and str((s.get("tags") or {}).get("mimetype") or "") == "image/jpeg" for s in streams)


def _v3_execute(self, result, item_index=1, item_total=1, selected_format_override=None):
    selected = selected_format_override if selected_format_override is not None else self._selected_download_format
    spec = _v3_selected_quality_spec(self, selected)
    file_type = str(spec.get("file_type") or getattr(self, "_v3_selected_file_type", "auto"))
    exts = {
        "auto": [".mkv", ".mp4", ".flac"], "mp4": [".mp4"], "mkv": [".mkv"], "webm": [".webm", ".mkv"], "mov": [".mov"],
        "mp3": [".mp3"], "m4a": [".m4a"], "opus": [".opus"], "vorbis": [".ogg"], "flac": [".flac"], "alac": [".m4a"], "wav": [".wav"],
    }.get(file_type, [".mp4", ".mkv", ".flac"])
    result = dict(result)
    result["output_filename"] = _v3_unique_stem(self.paths["downloader"], result.get("output_filename") or result.get("title") or "track", exts)
    out = _ORIGINAL_EXECUTE_V3(self, result, item_index=item_index, item_total=item_total, selected_format_override=selected_format_override)
    kind = "audio" if spec.get("kind") == "audio" else "video"
    _v3_validate_output(out, kind)
    _v3_history({"operation": "download_item", "video_id": result.get("video_id"), "title": result.get("title"), "file": str(out), "file_type": file_type, "quality": selected, "result": "success"})
    return out


def _v3_set_performance(self, value):
    self.performance_mode = {"Balanced": "balanced", "Conservative": "conservative", "Aggressive": "aggressive"}.get(str(value), "balanced")
    self.save_config()


def _v3_show_media_details(self):
    source = str(getattr(self, "_dl_preview_source", "") or self.dl_input.get()).strip()
    if not source:
        messagebox.showinfo("Media Details", "Paste a YouTube link first.")
        return
    fmts = getattr(self, "_v3_preview_formats", []) or []
    heights = detected_video_heights(fmts)
    tracks = build_audio_track_options(fmts)
    top = choose_best_format_at_height(fmts) if 'choose_best_format_at_height' in globals() else None
    lines = [f"Source: {source}", f"Mode: {self.downloader_quality_mode_for_source(source)}", f"Video heights: {', '.join(str(h)+'p' for h in heights) or 'none'}", f"Audio tracks: {len(tracks)}"]
    if top:
        lines.append(f"Best format: {top.get('height', 0)}p {top.get('fps') or 0}fps {top.get('vcodec') or 'unknown'}")
    messagebox.showinfo("Media Details", "\n".join(lines))


def _v3_queue_current(self):
    value = self.dl_input.get().strip()
    if not value or not is_youtube_url(value):
        messagebox.showerror("Queue", "Enter a valid YouTube URL first.")
        return
    if value not in getattr(self, "_v3_queue", []):
        self._v3_queue.append(value)
    try:
        self.dl_queue_count.configure(text=f"Queue: {len(self._v3_queue)}")
    except Exception:
        pass


# Keep the useful V2 methods but route the UI and downloader through the V3 layer.
YTMMusicToolkit.build_downloader_tab = _v3_build_downloader_tab
YTMMusicToolkit.hide_download_quality_selector = _v3_hide_selector
YTMMusicToolkit.show_download_quality_selector = _v3_show_selector
YTMMusicToolkit.selected_quality_spec = _v3_selected_quality_spec
YTMMusicToolkit._v3_file_type_changed = _v3_file_type_changed
YTMMusicToolkit._v3_set_performance = _v3_set_performance
YTMMusicToolkit._v3_show_media_details = _v3_show_media_details
YTMMusicToolkit._v3_queue_current = _v3_queue_current
YTMMusicToolkit.apply_silent_link_preview = _v3_apply_preview
YTMMusicToolkit.start_download = _v3_start_download
YTMMusicToolkit.run_download_worker = _v3_run_worker
YTMMusicToolkit.build_yt_dlp_command = _v3_build_command
YTMMusicToolkit.is_lossless_video_mode = _v3_is_lossless_video
YTMMusicToolkit.postprocess_downloaded_file = _v3_postprocess
YTMMusicToolkit.execute_download_for_result = _v3_execute

# Patch config persistence conservatively. Existing settings remain compatible.
_original_load_config_v3 = YTMMusicToolkit.load_config
_original_save_config_v3 = YTMMusicToolkit.save_config


def _v3_load_config(self):
    _original_load_config_v3(self)
    try:
        if os.path.exists(CONFIG_FILE):
            data = json.loads(Path(CONFIG_FILE).read_text(encoding="utf-8"))
            self.performance_mode = str(data.get("performance_mode", getattr(self, "performance_mode", "balanced")))
            self.conflict_mode = str(data.get("conflict_mode", getattr(self, "conflict_mode", "rename")))
            self.config_version = 3
    except Exception as exc:
        write_failure_log("v3_config_load", exc)


def _v3_save_config(self):
    _original_save_config_v3(self)
    try:
        if os.path.exists(CONFIG_FILE):
            data = json.loads(Path(CONFIG_FILE).read_text(encoding="utf-8"))
        else:
            data = {}
        data.update({"config_version": 3, "performance_mode": getattr(self, "performance_mode", "balanced"), "conflict_mode": getattr(self, "conflict_mode", "rename")})
        Path(CONFIG_FILE).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        write_failure_log("v3_config_save", exc)


YTMMusicToolkit.load_config = _v3_load_config
YTMMusicToolkit.save_config = _v3_save_config



# ============================================================
# V3 FINAL FORMAT / QUALITY / RELIABILITY LAYER
# ============================================================
# This layer keeps the existing V2/V3 UI and media pipeline, while making
# file type and file quality explicit, adding safety/recovery features, and
# keeping playlist state isolated from single-video state.

from datetime import datetime

# Portable diagnostics location: never hard-code a user's Windows account.
FAILURE_LOG_DIR = os.path.join(
    os.path.expanduser("~"),
    "Documents",
    "YTDLP",
)

# Supported containers/codecs exposed by the downloader UI.
FILE_TYPE_OPTIONS_V3 = [
    (" Auto", "auto"),
    (" MP4 Video", "mp4"),
    (" MKV Video", "mkv"),
    (" MP3 Audio", "mp3"),
    (" M4A / AAC Audio", "m4a"),
    (" Opus Audio", "opus"),
    (" Vorbis / OGG Audio", "vorbis"),
    (" FLAC Audio", "flac"),
    (" WAV PCM Audio", "wav"),
]
FILE_TYPE_BY_LABEL_V3 = {label: value for label, value in FILE_TYPE_OPTIONS_V3}
FILE_LABEL_BY_TYPE_V3 = {value: label for label, value in FILE_TYPE_OPTIONS_V3}
VIDEO_FILE_TYPES_V3 = {"auto", "mp4", "mkv"}
AUDIO_FILE_TYPES_V3 = {"mp3", "m4a", "opus", "vorbis", "flac", "wav"}
LOSSLESS_AUDIO_TYPES_V3 = {"flac", "wav"}
AUDIO_BITRATES_V3 = {
    "mp3": [64, 96, 128, 160, 192, 224, 256, 320],
    "m4a": [64, 96, 128, 160, 192, 224, 256, 320],
    "opus": [32, 48, 64, 96, 128, 160, 192, 256, 320],
    "vorbis": [64, 96, 128, 160, 192, 224, 256, 320],
}

# Output extension map used by the conflict-safe naming layer.
V3_OUTPUT_EXTENSIONS = {
    "auto": [".mkv", ".mp4", ".flac"],
    "mp4": [".mp4"],
    "mkv": [".mkv"],
    "mp3": [".mp3"],
    "m4a": [".m4a"],
    "opus": [".opus"],
    "vorbis": [".ogg"],
    "flac": [".flac"],
    "wav": [".wav"],
}


def _v3_file_type_id_final(label):
    return FILE_TYPE_BY_LABEL_V3.get(str(label or ""), "auto")


def _v3_audio_quality_options_final(file_type):
    file_type = str(file_type or "").lower()
    if file_type in LOSSLESS_AUDIO_TYPES_V3:
        # UI hides this quality dropdown for truly lossless types.
        name = {"flac": "Lossless — FLAC", "alac": "Lossless — ALAC", "wav": "Lossless — PCM WAV"}[file_type]
        return [(name, {
            "kind": "audio",
            "audio_format": file_type,
            "quality": None,
            "lossless": True,
            "file_type": file_type,
        })]
    return [
        (f" {rate} kbps", {
            "kind": "audio",
            "audio_format": file_type,
            "quality": f"{rate}K",
            "bitrate": rate,
            "lossless": False,
            "file_type": file_type,
        })
        for rate in sorted(AUDIO_BITRATES_V3.get(file_type, []), reverse=True)
    ]


def _v3_best_video_descriptor_final(formats, height):
    candidates = []
    for fmt in formats or []:
        if not isinstance(fmt, dict) or fmt.get("has_drm"):
            continue
        try:
            h = int(fmt.get("height") or 0)
        except (TypeError, ValueError):
            continue
        if h != int(height) or str(fmt.get("vcodec") or "none") == "none":
            continue
        try:
            fps = float(fmt.get("fps") or 0)
        except (TypeError, ValueError):
            fps = 0.0
        hdr = str(fmt.get("dynamic_range") or fmt.get("hdr") or "").strip()
        vcodec = str(fmt.get("vcodec") or "").split(".", 1)[0]
        tbr = float(fmt.get("tbr") or 0) if str(fmt.get("tbr") or "").replace('.', '', 1).isdigit() else 0.0
        candidates.append((fps, 1 if hdr and hdr.lower() not in {"sdr", "none"} else 0, tbr, vcodec, hdr))
    if not candidates:
        return ""
    fps, hdr_rank, _tbr, vcodec, hdr = max(candidates, key=lambda x: (x[0], x[1], x[2]))
    parts = [f"{int(height)}p"]
    if fps >= 1:
        parts.append(f"{int(fps) if fps.is_integer() else fps:g}fps")
    if hdr_rank:
        parts.append(hdr)
    return " • ".join(parts)


def _v3_video_quality_options_final(formats, file_type, mode="single"):
    """Build video choices only from resolutions detected for the current source."""
    file_type = str(file_type or "auto").lower()
    heights = detected_video_heights(formats)

    if mode == "playlist":
        options = [(
            "Best Option Separate",
            {"kind": "video", "best_per_item": True, "file_type": file_type},
        )]
        # Playlist ceilings are generic during preview; each video's real
        # formats are inspected immediately before its own download begins.
        playlist_heights = sorted(VIDEO_QUALITY_LABELS, reverse=True)
        for height in playlist_heights:
            label = VIDEO_QUALITY_LABELS.get(height, f"{height}P")
            options.append((label, {
                "kind": "video",
                "height": height,
                "best": False,
                "file_type": file_type,
                "playlist_ceiling": True,
            }))
        return options

    # Do not invent a resolution ladder before inspection or after inspection fails.
    if not heights:
        return []

    highest = heights[0]
    descriptor = _v3_best_video_descriptor_final(formats, highest)
    best_label = f"Best Quality — {descriptor or str(highest) + 'p'}"
    options = [(best_label, {
        "kind": "video",
        "height": highest,
        "best": True,
        "file_type": file_type,
    })]
    for height in heights[1:]:
        descriptor = _v3_best_video_descriptor_final(formats, height)
        label = descriptor if descriptor else VIDEO_QUALITY_LABELS.get(height, f"{height}P")
        options.append((label, {
            "kind": "video",
            "height": height,
            "best": False,
            "file_type": file_type,
        }))
    return options


def _v3_quality_options_final(formats, file_type, mode="single"):
    if str(file_type or "").lower() in AUDIO_FILE_TYPES_V3:
        return _v3_audio_quality_options_final(file_type)
    return _v3_video_quality_options_final(formats, file_type, mode)

# Keep the public V3 helper names pointed at the final implementations.
_v3_audio_quality_options = _v3_audio_quality_options_final
_v3_video_quality_options = _v3_video_quality_options_final
_v3_quality_options = _v3_quality_options_final
_v3_file_type_id = _v3_file_type_id_final


def _v3_set_dynamic_file_quality_ui(self, mode):
    """Rebuild only the quality dropdown appropriate to the current file type."""
    file_type = str(getattr(self, "_v3_selected_file_type", "auto"))
    options = _v3_quality_options_final(getattr(self, "_v3_preview_formats", []), file_type, mode)
    self._dl_preview_quality_options = options
    labels = [label for label, _spec in options]
    try:
        self.dl_format.configure(values=labels)
    except Exception:
        return options

    if file_type in LOSSLESS_AUDIO_TYPES_V3:
        self._v3_selected_file_quality = ""
        self.dl_quality_label.grid_remove()
        self.dl_format.grid_remove()
    else:
        self.dl_quality_label.grid(row=0, column=1, sticky="w", padx=22, pady=(14, 4))
        self.dl_format.grid(row=1, column=1, sticky="ew", padx=22, pady=(0, 8))
        default = labels[0] if labels else ""
        mode = str(mode or "")
        if mode == "playlist" and file_type in VIDEO_FILE_TYPES_V3:
            default = "Best Option Separate"
        if default and default in labels:
            self.dl_format.set(default)
            self._v3_selected_file_quality = default
        else:
            self.dl_format.set("")
            self._v3_selected_file_quality = ""
    return options


def _v3_file_type_changed_final(self, selected_label=None):
    try:
        label = str(selected_label or self.dl_file_type.get())
        file_type = _v3_file_type_id_final(label)
        self._v3_selected_file_type = file_type
        source = str(self._dl_preview_quality_source or self.dl_input.get()).strip()
        mode = self.downloader_quality_mode_for_source(source) if source else "none"
        if mode not in {"single", "playlist"}:
            self._dl_preview_quality_options = []
            self._v3_selected_file_quality = ""
            self.dl_quality_label.grid_remove()
            self.dl_format.grid_remove()
            return
        _v3_set_dynamic_file_quality_ui(self, mode)
    except Exception as exc:
        write_failure_log("v3_final_file_type_change", exc)


# Replace the older handler with the final context-aware one.
YTMMusicToolkit._v3_file_type_changed = _v3_file_type_changed_final


def _v3_build_command_final(self, source_url, result, selected_format):
    spec = _v3_selected_quality_spec(self, selected_format)
    if not spec:
        raise RuntimeError("No valid file quality selection is available")

    output_dir = self.paths["downloader"]
    file_type = str(spec.get("file_type") or getattr(self, "_v3_selected_file_type", "auto")).lower()
    title = sanitize_filename(result.get("output_filename") or result.get("title") or "track")
    if file_type == "auto" and spec.get("kind") == "video":
        try:
            height = int(spec.get("height") or 0)
        except (TypeError, ValueError):
            height = 0
        actual_container = "mkv" if height >= 1080 else "mp4"
    else:
        actual_container = file_type

    command = [
        get_ytdlp_command(),
        *get_ytdlp_runtime_args(getattr(self, "performance_mode", "aggressive")),
        "--newline",
        "--windows-filenames",
        "--part",
        "--no-overwrites",
        "--retries", "10",
        "--fragment-retries", "10",
        "--retry-sleep", "exp=1:30",
        "--socket-timeout", "20",
        "--concurrent-fragments", str(get_concurrent_fragment_count(getattr(self, "performance_mode", "aggressive"))),
        "--format-sort", "res,fps,hdr:12,vcodec,channels,acodec,size,br,asr,proto,ext",
    ]

    command.extend(get_browser_cookie_args(source_url))

    extractor_arg = result.get("quality_extractor_arg") or getattr(self, "_dl_youtube_extractor_arg", None) or getattr(self, "_last_quality_extractor_arg", None)
    command.extend(youtube_extractor_args_list(extractor_arg))

    if spec.get("kind") == "audio":
        audio_format = str(spec.get("audio_format") or "flac")
        command.extend(["-x", "--audio-format", audio_format])
        if spec.get("quality") and not spec.get("lossless"):
            command.extend(["--audio-quality", str(spec["quality"])])
    elif spec.get("kind") == "video":
        try:
            height = int(spec.get("height") or 0)
        except (TypeError, ValueError):
            height = 0
        if height <= 0:
            raise RuntimeError("The selected video quality has no resolution")

        # Explicit file type controls the container; Auto retains the app's
        # established 720p-and-below MP4 / 1080p+-lossless-MKV policy.
        if actual_container == "mp4":
            selector = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        elif actual_container == "webm":
            selector = f"bestvideo[height<={height}][ext=webm]+bestaudio[ext=webm]/bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        else:
            selector = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        command.extend(["-f", selector, "--merge-output-format", actual_container])
    else:
        raise RuntimeError("No valid download type selected")

    if getattr(self, "_selected_download_subtitles", False) and spec.get("kind") == "video" and actual_container in {"mp4", "mkv", "webm", "mov"}:
        command.extend(["--write-sub", "--write-auto-sub", "--embed-subs", "--sub-lang", "en,ar"])

    command.extend(["-o", os.path.join(output_dir, f"{title}.%(ext)s"), "--", source_url])
    return command

YTMMusicToolkit.build_yt_dlp_command = _v3_build_command_final


def _v3_write_generic_audio_metadata_final(file_path, result, cover_bytes=None):
    """Write common title/artist/album/year metadata for all supported audio outputs."""
    suffix = Path(file_path).suffix.lower()
    artist = ", ".join(result.get("artist_names") or [])
    album = str(result.get("album") or "")
    title = str(result.get("title") or "")
    year = str(result.get("year") or "")

    try:
        if suffix == ".mp3":
            audio = ID3(file_path)
            for tag in ("TPE1", "TALB", "TIT2", "TDRC", "TPE2", "APIC"):
                audio.delall(tag)
            if artist:
                audio.add(TPE1(encoding=3, text=artist))
            if album:
                audio.add(TALB(encoding=3, text=album))
            if title:
                audio.add(TIT2(encoding=3, text=title))
            if year:
                audio.add(TDRC(encoding=3, text=year))
            if cover_bytes:
                image = normalize_cover_to_jpeg(cover_bytes) or cover_bytes
                audio.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Front Cover", data=image))
            audio.save(file_path)
            return

        if suffix == ".m4a":
            audio = MP4(file_path)
            for key in ("©ART", "©alb", "©nam", "©day", "aART", "covr"):
                audio.pop(key, None)
            if artist:
                audio["©ART"] = [artist]
            if album:
                audio["©alb"] = [album]
            if title:
                audio["©nam"] = [title]
            if year:
                audio["©day"] = [year]
            if cover_bytes:
                image = normalize_cover_to_jpeg(cover_bytes) or cover_bytes
                audio["covr"] = [MP4Cover(image, imageformat=MP4Cover.FORMAT_JPEG)]
            audio.save()
            return

        if suffix == ".opus":
            from mutagen.oggopus import OggOpus
            audio = OggOpus(file_path)
            audio.clear()
            if artist:
                audio["ARTIST"] = [artist]
            if album:
                audio["ALBUM"] = [album]
            if title:
                audio["TITLE"] = [title]
            if year:
                audio["DATE"] = [year]
            audio.save()
            return

        if suffix == ".ogg":
            from mutagen.oggvorbis import OggVorbis
            audio = OggVorbis(file_path)
            audio.clear()
            if artist:
                audio["ARTIST"] = [artist]
            if album:
                audio["ALBUM"] = [album]
            if title:
                audio["TITLE"] = [title]
            if year:
                audio["DATE"] = [year]
            audio.save()
            return

        if suffix == ".wav":
            from mutagen.wave import WAVE
            audio = WAVE(file_path)
            if audio.tags is None:
                audio.add_tags()
            if artist:
                audio.tags["TPE1"] = TPE1(encoding=3, text=artist)
            if album:
                audio.tags["TALB"] = TALB(encoding=3, text=album)
            if title:
                audio.tags["TIT2"] = TIT2(encoding=3, text=title)
            if year:
                audio.tags["TDRC"] = TDRC(encoding=3, text=year)
            if cover_bytes:
                image = normalize_cover_to_jpeg(cover_bytes) or cover_bytes
                audio.tags["APIC:Front Cover"] = APIC(encoding=3, mime="image/jpeg", type=3, desc="Front Cover", data=image)
            audio.save()
            return

        if suffix == ".aac":
            # ADTS AAC has no universally portable embedded-cover field. Use
            # ID3v2 for text metadata without corrupting the elementary stream.
            try:
                audio = ID3(file_path)
            except Exception:
                audio = ID3()
            for tag in ("TPE1", "TALB", "TIT2", "TDRC", "TPE2", "APIC"):
                audio.delall(tag)
            if artist:
                audio.add(TPE1(encoding=3, text=artist))
            if album:
                audio.add(TALB(encoding=3, text=album))
            if title:
                audio.add(TIT2(encoding=3, text=title))
            if year:
                audio.add(TDRC(encoding=3, text=year))
            audio.save(file_path)
            return
    except Exception as exc:
        log_path = write_failure_log("v3_audio_metadata", exc, details=f"File: {file_path}")
        raise RuntimeError(f"Audio metadata write failed. Failure log: {log_path or FAILURE_LOG_DIR}") from exc


write_generic_audio_metadata = _v3_write_generic_audio_metadata_final


def _v3_safe_metadata_backup(file_path):
    """Snapshot current tags and first cover before destructive metadata rewrites."""
    path = Path(file_path)
    if path.suffix.lower() != ".flac" or not path.exists():
        return None
    try:
        backup_dir = ensure_failure_log_dir() / "metadata_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        stem = sanitize_filename(path.stem)
        json_path = backup_dir / f"{stem}_{stamp}.json"
        flac = FLAC(path)
        snapshot = {str(k): list(v) if isinstance(v, list) else [str(v)] for k, v in flac.items()}
        snapshot["_file"] = str(path)
        snapshot["_pictures"] = len(flac.pictures or [])
        json_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
        if flac.pictures:
            (backup_dir / f"{stem}_{stamp}.jpg").write_bytes(normalize_cover_to_jpeg(flac.pictures[0].data) or flac.pictures[0].data)
        return str(json_path)
    except Exception:
        return None


_original_rewrite_strict_final = rewrite_flac_metadata_strict


def _v3_rewrite_with_backup(file_path, result, replacement_cover_bytes=None):
    _v3_safe_metadata_backup(file_path)
    return _original_rewrite_strict_final(file_path, result, replacement_cover_bytes=replacement_cover_bytes)


rewrite_flac_metadata_strict = _v3_rewrite_with_backup


# Ensure the failure folder exists immediately on first run, without showing UI.
try:
    ensure_failure_log_dir()
except Exception:
    pass


# Richer media-details dialog.
def _v3_show_media_details_final(self):
    source = str(getattr(self, "_dl_preview_source", "") or self.dl_input.get()).strip()
    if not source:
        messagebox.showinfo("Media Details", "Paste a YouTube link first.")
        return
    fmts = getattr(self, "_v3_preview_formats", []) or []
    heights = detected_video_heights(fmts)
    tracks = build_audio_track_options(fmts)
    best = None
    try:
        candidates = [f for f in fmts if str(f.get("vcodec") or "none") != "none"]
        if candidates:
            best = max(candidates, key=lambda f: (
                int(f.get("height") or 0),
                float(f.get("fps") or 0),
                float(f.get("tbr") or 0),
            ))
    except Exception:
        best = None
    max_abr = 0
    try:
        max_abr = max(float(f.get("abr") or 0) for f in fmts if _format_is_audio_only(f))
    except Exception:
        pass
    thumb = getattr(self, "_v3_preview_thumbnail_size", None)
    lines = [
        f"Source: {source}",
        f"Mode: {self.downloader_quality_mode_for_source(source)}",
        f"Video resolutions: {', '.join(str(h) + 'p' for h in heights) or 'none'}",
        f"Audio tracks: {len(tracks)}",
        f"Source max audio bitrate: {max_abr:.0f} kbps" if max_abr else "Source max audio bitrate: unknown",
    ]
    if thumb:
        lines.append(f"Thumbnail: {thumb[0]}×{thumb[1]}")
    if best:
        lines.append(
            f"Top video candidate: {best.get('height') or 0}p · {best.get('fps') or 0:g}fps · {best.get('vcodec') or 'unknown'} · {best.get('dynamic_range') or 'SDR'}"
        )
    if tracks:
        lines.append("Audio languages: " + ", ".join(str(t.get("label") or t.get("language") or "Unknown") for t in tracks))
    messagebox.showinfo("Media Details", "\n".join(lines))


YTMMusicToolkit._v3_show_media_details = _v3_show_media_details_final


# -------------------- real queue --------------------
def _v3_queue_current_final(self):
    value = self.dl_input.get().strip()
    if not value or not is_youtube_url(value):
        messagebox.showerror("Queue", "Enter a valid YouTube or YouTube Music URL first.")
        return
    file_type = _v3_file_type_id_final(self.dl_file_type.get()) if getattr(self, "dl_file_type", None) else "auto"
    quality = self.dl_format.get().strip() if getattr(self, "dl_format", None) and self._dl_quality_visible else ""
    if file_type in LOSSLESS_AUDIO_TYPES_V3:
        quality = _v3_audio_quality_options_final(file_type)[0][0]
    item = {
        "url": value,
        "file_type": file_type,
        "quality": quality,
        "subtitles": bool(self.dl_subs.get()) if hasattr(self, "dl_subs") else False,
    }
    self._v3_queue = getattr(self, "_v3_queue", [])
    if any(str(x.get("url")) == value and x.get("file_type") == file_type and x.get("quality") == quality for x in self._v3_queue):
        return
    self._v3_queue.append(item)
    try:
        self.dl_queue_count.configure(text=f"Queue: {len(self._v3_queue)}")
    except Exception:
        pass


def _v3_process_queue(self):
    if getattr(self, "download_running", False) or getattr(self, "_v3_queue_active", False):
        return
    items = list(getattr(self, "_v3_queue", []) or [])
    if not items:
        messagebox.showinfo("Queue", "The queue is empty.")
        return
    self._v3_queue = []
    self._v3_queue_active = True
    try:
        self.dl_queue_count.configure(text="Queue: 0")
    except Exception:
        pass
    threading.Thread(target=self._v3_queue_worker, args=(items,), daemon=True).start()


def _v3_queue_worker(self, items):
    completed = 0
    try:
        total = len(items)
        for index, item in enumerate(items, 1):
            if self.stop_requested:
                break
            self._v3_selected_file_type = item.get("file_type") or "auto"
            self._v3_selected_file_quality = item.get("quality") or ""
            self._selected_file_type = self._v3_selected_file_type
            self._selected_file_quality = self._v3_selected_file_quality
            self._selected_download_format = self._v3_selected_file_quality
            self._selected_download_subtitles = bool(item.get("subtitles"))
            self.download_running = True
            self.stop_requested = False
            self._v3_queue_item_index = index
            self._v3_queue_item_total = total
            self.set_operation_progress("dl", 0, f"Queue item {index}/{total} — preparing...", taskbar=True)
            try:
                self._v3_dry_run_active = False
                self.run_download_worker(item["url"])
                completed += 1
            except Exception as exc:
                write_failure_log("v3_queue_item", exc, details=f"Queue item: {index}/{total}\nURL: {item.get('url')}")
            finally:
                self.download_running = False
    except Exception as exc:
        log_path = write_failure_log("v3_queue_worker", exc)
        self.after(0, lambda: messagebox.showerror("Queue Error", f"{exc}\n\nFailure log:\n{log_path or FAILURE_LOG_DIR}"))
    finally:
        self._v3_queue_active = False
        self.after(0, lambda: self.set_operation_progress("dl", 100, f"Queue Complete — {completed}/{len(items)} completed", taskbar=False))


YTMMusicToolkit._v3_queue_current = _v3_queue_current_final
YTMMusicToolkit._v3_process_queue = _v3_process_queue
YTMMusicToolkit._v3_queue_worker = _v3_queue_worker


# -------------------- yt-dlp update check (no automatic download) --------------------
def _v3_check_ytdlp_update(self):
    try:
        local = subprocess.run(
            [get_ytdlp_command(), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            **get_hidden_subprocess_kwargs(),
        )
        installed = local.stdout.strip() or "unknown"
        response = session.get(
            "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest",
            timeout=15,
            headers={"Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()
        latest = str(response.json().get("tag_name") or "unknown").lstrip("v")
        messagebox.showinfo("yt-dlp Update Check", f"Installed: {installed}\nLatest release: {latest}\n\nNo update was downloaded.")
    except Exception as exc:
        log_path = write_failure_log("v3_ytdlp_update_check", exc)
        messagebox.showerror("yt-dlp Update Check", f"Could not check the latest release.\n\nFailure log:\n{log_path or FAILURE_LOG_DIR}")


YTMMusicToolkit._v3_check_ytdlp_update = _v3_check_ytdlp_update


# -------------------- final downloader UI extension --------------------
_original_v3_build_downloader_final = YTMMusicToolkit.build_downloader_tab


def _v4_install_preview_menu(self):
    """Install a compact three-dot utility menu on the preview card."""
    # Remove the visible utility action buttons from the options card.
    try:
        utility = self.dl_queue_count.master
        for widget in list(utility.winfo_children()):
            if isinstance(widget, ctk.CTkButton):
                text_value = str(widget.cget("text") or "").lower()
                if any(token in text_value for token in ("inspect details", "queue", "process queue", "check yt-dlp")):
                    widget.destroy()
        self.dl_queue_count.grid_remove()
    except Exception as exc:
        write_failure_log("v4_remove_downloader_utility_buttons", exc)

    # Add the ellipsis control to the top-right corner of the preview card.
    try:
        preview = self.dl_preview_card
        preview.grid_columnconfigure(2, weight=0)
        self.dl_preview_menu_button = ctk.CTkButton(
            preview,
            text="⋯",
            width=34,
            height=34,
            font=(APP_FONT, 18, "bold"),
            fg_color="transparent",
            hover_color="#101827",
            text_color="#94a3b8",
            corner_radius=10,
            border_width=0,
            command=self._v4_show_preview_menu,
        )
        self.dl_preview_menu_button.grid(
            row=0,
            column=2,
            sticky="ne",
            padx=(0, 12),
            pady=(10, 10),
        )
    except Exception as exc:
        write_failure_log("v4_preview_menu_install", exc)


def _v4_preview_menu(self):
    """Build the current preview utility menu with a live queue count."""
    import tkinter as tk

    menu = tk.Menu(
        self,
        tearoff=False,
        bg="#05080c",
        fg="#f8fafc",
        activebackground="#10253b",
        activeforeground="#ffffff",
        borderwidth=1,
        relief="solid",
        font=(APP_FONT, 10),
    )
    queue_count = len(getattr(self, "_v3_queue", []) or [])
    menu.add_command(label="ⓘ  Inspect Details", command=self._v3_show_media_details)
    menu.add_command(label=f"＋  Add to Queue   ({queue_count})", command=self._v3_queue_current)
    menu.add_separator()
    menu.add_command(label="↻  Check yt-dlp", command=self._v3_check_ytdlp_update)
    return menu


def _v4_show_preview_menu(self):
    try:
        button = self.dl_preview_menu_button
        menu = _v4_preview_menu(self)
        x = button.winfo_rootx() + button.winfo_width() - 6
        y = button.winfo_rooty() + button.winfo_height() - 2
        menu.tk_popup(x, y)
        try:
            self.after_idle(menu.grab_release)
        except Exception:
            pass
    except Exception as exc:
        write_failure_log("v4_preview_menu_open", exc)


YTMMusicToolkit._v4_preview_menu = _v4_preview_menu
YTMMusicToolkit._v4_show_preview_menu = _v4_show_preview_menu
YTMMusicToolkit._v4_install_preview_menu = _v4_install_preview_menu


def _v4_build_downloader_tab(self, tab):
    _original_v3_build_downloader_final(self, tab)
    self.after(0, self._v4_install_preview_menu)


YTMMusicToolkit.build_downloader_tab = _v4_build_downloader_tab


# Keep config versioning at the final feature level.
_original_final_load = YTMMusicToolkit.load_config
_original_final_save = YTMMusicToolkit.save_config


def _v3_load_config_final(self):
    _original_final_load(self)
    self.config_version = 5
    self.appearance_mode = "dark"
    # New installs start in Aggressive mode. Existing saved choices are loaded
    # below, with the old default Balanced setting migrated once to Aggressive.
    self.performance_mode = "aggressive"
    self.conflict_mode = getattr(self, "conflict_mode", "rename") or "rename"
    try:
        if os.path.exists(CONFIG_FILE):
            data = json.loads(Path(CONFIG_FILE).read_text(encoding="utf-8"))
            old_version = int(data.get("config_version", 0) or 0)
            saved_mode = str(data.get("performance_mode", "aggressive")).strip().lower()
            if old_version < 5 and saved_mode == "balanced":
                saved_mode = "aggressive"
            if saved_mode not in {"conservative", "balanced", "aggressive"}:
                saved_mode = "aggressive"
            self.performance_mode = saved_mode
            self.conflict_mode = str(data.get("conflict_mode", self.conflict_mode))
            saved_appearance = str(data.get("appearance_mode", "dark")).strip().lower()
            self.appearance_mode = saved_appearance if saved_appearance in {"dark", "light"} else "dark"
    except Exception as exc:
        write_failure_log("v3_final_config_load", exc)


def _v3_save_config_final(self):
    _original_final_save(self)
    try:
        if os.path.exists(CONFIG_FILE):
            data = json.loads(Path(CONFIG_FILE).read_text(encoding="utf-8"))
        else:
            data = {}
        data.update({
            "config_version": 5,
            "performance_mode": getattr(self, "performance_mode", "aggressive"),
            "conflict_mode": getattr(self, "conflict_mode", "rename"),
            "appearance_mode": getattr(self, "appearance_mode", "dark"),
        })
        Path(CONFIG_FILE).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        write_failure_log("v3_final_config_save", exc)


YTMMusicToolkit.load_config = _v3_load_config_final
YTMMusicToolkit.save_config = _v3_save_config_final


# The downloader now always exposes the final context-sensitive UI semantics.
# Final downloader implementation is the compact V4 wrapper defined above.
YTMMusicToolkit.build_downloader_tab = _v4_build_downloader_tab

# ============================================================
# ALWAYS-VISIBLE DOWNLOAD OPTIONS (File Type + File Quality)
# ============================================================
# Previously both dropdowns were hidden until a link preview finished. They
# are now always on screen. Before a preview exists, the quality dropdown shows
# a placeholder ("Best Quality" for video, bitrates for lossy audio); the real
# per-video resolutions replace it as soon as the preview/inspection completes.
# The placeholder never marks the selector as "matched to a source", so the
# download worker still inspects the exact link and picks the real best option.

def _v5_generic_video_options(file_type):
    """Full resolution ladder used before (or without) a successful inspection."""
    file_type = str(file_type or "auto").lower()
    top = max(VIDEO_QUALITY_LABELS)
    options = [(
        " Best Quality",
        {"kind": "video", "height": top, "best": True, "file_type": file_type},
    )]
    for height in sorted(VIDEO_QUALITY_LABELS, reverse=True):
        options.append((
            VIDEO_QUALITY_LABELS[height],
            {"kind": "video", "height": height, "best": False, "file_type": file_type},
        ))
    return options


def _v5_show_selector_placeholder(self):
    try:
        file_type = str(getattr(self, "_v3_selected_file_type", "auto") or "auto")
        self.dl_file_type_label.grid(row=0, column=0, sticky="w", padx=22, pady=(14, 4))
        self.dl_file_type.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 8))
        self.dl_file_type.set(FILE_LABEL_BY_TYPE_V3.get(file_type, FILE_LABEL_BY_TYPE_V3["auto"]))

        if file_type in LOSSLESS_AUDIO_TYPES_V3:
            self.dl_quality_label.grid_remove()
            self.dl_format.grid_remove()
            return

        options = _v3_quality_options_final([], file_type, "single")
        labels = [label for label, _spec in options]
        self._dl_preview_quality_options = options

        self.dl_quality_label.configure(text=" File Quality")
        self.dl_quality_label.grid(row=0, column=1, sticky="w", padx=22, pady=(14, 4))
        self.dl_format.grid(row=1, column=1, sticky="ew", padx=22, pady=(0, 8))
        self.dl_format.configure(values=labels)
        self.dl_format.set(labels[0] if labels else "")
        # Deliberately NOT marking the selector as source-matched.
        self._dl_quality_visible = False
    except Exception as exc:
        write_failure_log("v5_selector_placeholder", exc)


def _v5_hide_selector(self):
    """Reset preview state exactly as before, but keep the dropdowns on screen."""
    _v3_hide_selector(self)
    if getattr(self, "dl_file_type", None) is not None:
        _v5_show_selector_placeholder(self)


def _v5_file_type_changed(self, selected_label=None):
    try:
        source = str(getattr(self, "_dl_preview_quality_source", "") or "").strip()
        if source and self.downloader_quality_mode_for_source(source) in {"single", "playlist"}:
            return _v3_file_type_changed_final(self, selected_label)
        label = str(selected_label or self.dl_file_type.get())
        self._v3_selected_file_type = _v3_file_type_id_final(label)
        _v5_show_selector_placeholder(self)
    except Exception as exc:
        write_failure_log("v5_file_type_change", exc)


YTMMusicToolkit.hide_download_quality_selector = _v5_hide_selector
YTMMusicToolkit._v3_file_type_changed = _v5_file_type_changed


# ---- download never dies just because qualities failed to load ----
_v5_original_build_command = YTMMusicToolkit.build_yt_dlp_command


def _v5_build_command(self, source_url, result, selected_format):
    pending = getattr(self, "_v5_pending_spec", None)
    if pending:
        selected_format = dict(pending)
    if not _v3_selected_quality_spec(self, selected_format):
        file_type = str(getattr(self, "_v3_selected_file_type", "auto") or "auto").lower()
        if file_type in AUDIO_FILE_TYPES_V3:
            options = _v3_audio_quality_options_final(file_type)
            spec = dict(options[0][1]) if options else {}
        else:
            # Unknown resolutions: ask for the best available (4320p ceiling).
            spec = {"kind": "video", "height": 4320, "best": True, "file_type": file_type}
        if spec:
            selected_format = spec
    return _v5_original_build_command(self, source_url, result, selected_format)


YTMMusicToolkit.build_yt_dlp_command = _v5_build_command

_v5_original_start_download = YTMMusicToolkit.start_download


def _v5_start_download(self):
    """Remember a quality picked before any real inspection finished."""
    self._v5_pending_spec = None
    try:
        if not self._dl_quality_visible and self.dl_format.winfo_ismapped():
            label = self.dl_format.get().strip()
            file_type = str(getattr(self, "_v3_selected_file_type", "auto") or "auto")
            for opt_label, spec in _v3_quality_options_final([], file_type, "single"):
                if opt_label == label:
                    self._v5_pending_spec = dict(spec)
                    break
    except Exception:
        self._v5_pending_spec = None
    return _v5_original_start_download(self)


YTMMusicToolkit.start_download = _v5_start_download


# ============================================================
# DOWNLOAD TEMP WORKSPACE (V6)
# ============================================================
# All media downloads are staged under <download directory>\\tempytm.
# Completed deliverables are moved to the real download folder immediately
# after each item, leaving only temporary artifacts in the staging directory.
# The workspace is removed when a single item, full playlist, queue item, or
# cancelled/failed download worker finishes.

_V6_FINAL_MEDIA_EXTENSIONS = {
    ".mkv", ".mka", ".mp4", ".webm", ".mov", ".m4v",
    ".flac", ".mp3", ".m4a", ".opus", ".ogg", ".oga", ".aac", ".wav",
    ".vtt", ".srt", ".ass", ".ssa", ".lrc",
}

_V6_ORIGINAL_RUN_DOWNLOAD_WORKER = YTMMusicToolkit.run_download_worker
_V6_ORIGINAL_EXECUTE_DOWNLOAD = YTMMusicToolkit.execute_download_for_result


def _v6_remove_temp_workspace(temp_root, context="download_temp_workspace_cleanup"):
    """Remove tempytm reliably on Windows and log any leftovers instead of hiding them."""
    root = Path(temp_root)
    if not root.exists():
        return True

    last_error = None
    for attempt in range(4):
        try:
            shutil.rmtree(root)
            return True
        except FileNotFoundError:
            return True
        except Exception as exc:
            last_error = exc
            time.sleep(0.15 * (attempt + 1))

    log_path = write_failure_log(
        context,
        last_error or RuntimeError("Temporary workspace could not be removed"),
        details=f"Temporary workspace: {root}",
    )
    return False


def _v6_clear_temp_contents(temp_root):
    root = Path(temp_root)
    if not root.exists():
        return
    for child in list(root.iterdir()):
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        except Exception as exc:
            write_failure_log("download_temp_cleanup_item", exc, details=f"Path: {child}")


def _v6_unique_destination_path(destination_dir, filename):
    folder = Path(destination_dir)
    target = folder / filename
    if not target.exists():
        return target
    suffix = target.suffix
    stem = target.name[:-len(suffix)] if suffix else target.name
    index = 1
    while True:
        candidate = folder / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _v6_update_history_path(old_path, new_path):
    try:
        history_path = Path(FAILURE_LOG_DIR) / "operation_history.json"
        if not history_path.is_file():
            return
        records = json.loads(history_path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            return
        old_text = str(old_path)
        new_text = str(new_path)
        for record in reversed(records):
            if isinstance(record, dict) and str(record.get("file") or "") == old_text:
                record["file"] = new_text
                history_path.write_text(
                    json.dumps(records[-250:], indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                return
    except Exception as exc:
        write_failure_log("download_temp_history_update", exc)


def _v6_run_download_worker(self, user_input):
    # "Inspect only" does not create a media workspace or change its output path.
    if getattr(self, "_v3_dry_run_active", False):
        return _V6_ORIGINAL_RUN_DOWNLOAD_WORKER(self, user_input)

    if getattr(self, "_v6_download_temp_root", None):
        return _V6_ORIGINAL_RUN_DOWNLOAD_WORKER(self, user_input)

    original_output_path = self.paths["downloader"]
    destination = Path(original_output_path).expanduser().resolve()
    temp_root = destination / "tempytm"
    try:
        destination.mkdir(parents=True, exist_ok=True)
        if temp_root.exists():
            if not _v6_remove_temp_workspace(temp_root, "download_temp_workspace_stale_cleanup"):
                raise RuntimeError(f"Could not clear the previous temporary workspace: {temp_root}")
        temp_root.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        log_path = write_failure_log(
            "download_temp_workspace_start",
            exc,
            details=f"Destination: {destination}\nTemporary workspace: {temp_root}",
        )
        self.append_log(
            self.dl_log,
            f"[ERROR] Could not prepare the tempytm workspace: {exc} | Failure log: {log_path or FAILURE_LOG_DIR}",
        )
        self.set_label(self.dl_status, "Status: Could not prepare temporary download folder")
        self.download_running = False
        self.after(0, self.reset_downloader_ui)
        return

    self._v6_download_destination = destination
    self._v6_download_temp_root = temp_root
    try:
        return _V6_ORIGINAL_RUN_DOWNLOAD_WORKER(self, user_input)
    finally:
        # The worker catches cancellation and download failures internally, so
        # this finally block also handles Stop, errors, and playlist early exits.
        self.paths["downloader"] = original_output_path
        _v6_remove_temp_workspace(temp_root, "download_temp_workspace_final_cleanup")
        self._v6_download_destination = None
        self._v6_download_temp_root = None


def _v6_execute_through_temp(self, result, item_index=1, item_total=1, selected_format_override=None):
    original_output_path = self.paths["downloader"]
    destination = Path(
        getattr(self, "_v6_download_destination", original_output_path)
    ).expanduser().resolve()
    temp_root = Path(
        getattr(self, "_v6_download_temp_root", destination / "tempytm")
    ).expanduser().resolve()
    owns_workspace = getattr(self, "_v6_download_temp_root", None) is None

    if owns_workspace:
        destination.mkdir(parents=True, exist_ok=True)
        if temp_root.exists():
            if not _v6_remove_temp_workspace(temp_root, "download_temp_workspace_item_stale_cleanup"):
                raise RuntimeError(f"Could not clear the previous temporary workspace: {temp_root}")
        temp_root.mkdir(parents=True, exist_ok=True)
        self._v6_download_destination = destination
        self._v6_download_temp_root = temp_root

    temp_root.mkdir(parents=True, exist_ok=True)
    playlist_context = getattr(self, "_dl_playlist_progress_context", None)
    is_playlist_item = bool(playlist_context and int(playlist_context[1]) > 1)

    result_for_download = dict(result or {})
    selected = (
        selected_format_override
        if selected_format_override is not None
        else self._selected_download_format
    )
    spec = _v3_selected_quality_spec(self, selected)
    file_type = str(
        (spec or {}).get("file_type")
        or getattr(self, "_v3_selected_file_type", "auto")
        or "auto"
    ).lower()
    extensions = {
        "auto": [".mkv", ".mp4", ".flac", ".m4a", ".mp3", ".opus", ".ogg", ".wav", ".aac"],
        "mp4": [".mp4"], "mkv": [".mkv"], "webm": [".webm", ".mkv"],
        "mov": [".mov"], "mp3": [".mp3"], "m4a": [".m4a"],
        "opus": [".opus"], "vorbis": [".ogg"], "flac": [".flac"],
        "alac": [".m4a"], "wav": [".wav"],
    }.get(file_type, [".mkv", ".mp4", ".flac", ".m4a", ".mp3"])

    # Reserve the final basename against the REAL output folder before swapping
    # the worker's output directory to tempytm.
    base = (
        result_for_download.get("output_filename")
        or result_for_download.get("title")
        or "track"
    )
    result_for_download["output_filename"] = _v3_unique_stem(
        destination,
        base,
        extensions,
    )

    try:
        self.paths["downloader"] = str(temp_root)
        out = _V6_ORIGINAL_EXECUTE_DOWNLOAD(
            self,
            result_for_download,
            item_index=item_index,
            item_total=item_total,
            selected_format_override=selected_format_override,
        )
        output_temp_path = Path(out).resolve()
        moved_paths = {}

        # Only final media/subtitle artifacts at the workspace root are exported.
        # Nested working files, .part fragments, thumbnail files, and mux inputs
        # are deliberately not moved into the user's download folder.
        for source in list(temp_root.iterdir()):
            if not source.is_file():
                continue
            if source.suffix.lower() not in _V6_FINAL_MEDIA_EXTENSIONS:
                continue
            if source.name.lower().endswith((".part", ".ytdl", ".tmp", ".temp")):
                continue

            target = _v6_unique_destination_path(destination, source.name)
            source_key = source.resolve()
            try:
                os.replace(str(source), str(target))
            except OSError:
                shutil.move(str(source), str(target))
            moved_paths[source_key] = target

        final_output_path = moved_paths.get(output_temp_path)
        if final_output_path is None or not final_output_path.is_file():
            raise RuntimeError(
                "The completed media file could not be moved out of tempytm. "
                "Check the latest download failure log before retrying."
            )

        _v6_update_history_path(output_temp_path, final_output_path)

        # Export happened immediately after the item completed. Discard any
        # remaining thumbnail, partial, subtitle scratch, merge, or nested temp
        # artifacts before another playlist item starts using the same workspace.
        _v6_clear_temp_contents(temp_root)

        # A single download owns the whole workspace lifecycle; remove the
        # folder immediately after its deliverables have been exported. During a
        # playlist, keep the empty root available for the next item and remove it
        # only when the playlist worker exits (including Stop/cancellation).
        if not is_playlist_item:
            _v6_remove_temp_workspace(temp_root, "download_temp_workspace_single_cleanup")

        return final_output_path
    finally:
        self.paths["downloader"] = original_output_path
        if owns_workspace:
            _v6_remove_temp_workspace(temp_root, "download_temp_workspace_item_cleanup")
            self._v6_download_destination = None
            self._v6_download_temp_root = None


YTMMusicToolkit.run_download_worker = _v6_run_download_worker
YTMMusicToolkit.execute_download_for_result = _v6_execute_through_temp



# ============================================================
# DEDICATED QUEUE TAB (V7)
# ============================================================
# Keeps Add to Queue on Downloader, adds a dedicated Queue tab, and mirrors
# pause/resume/stop controls across both tabs while the queue is processing.


def _queue_palette(self):
    mode = str(getattr(self, "appearance_mode", "dark") or "dark").lower()
    return APPLE_THEME_PALETTES.get(mode, APPLE_THEME_PALETTES["dark"])


def _queue_set_status(self, text):
    def apply():
        try:
            self.queue_status_label.configure(text=str(text))
        except Exception:
            pass
    try:
        self.after(0, apply)
    except Exception:
        pass


def _queue_render_queue(self):
    """Rebuild the visible queue list from the current queue model."""
    palette = _queue_palette(self)
    items = list(getattr(self, "_v3_queue", []) or [])

    for row in list(getattr(self, "_queue_row_widgets", []) or []):
        try:
            row.destroy()
        except Exception:
            pass
    self._queue_row_widgets = []

    count = len(items)
    try:
        self.queue_count_label.configure(
            text=f"{count} item" if count == 1 else f"{count} items"
        )
    except Exception:
        pass
    try:
        self.dl_queue_count.configure(text=f"Queue: {count}")
    except Exception:
        pass
    try:
        access = getattr(self, "dl_queue_access_button", None)
        if access:
            access.configure(text=f"☷  Queue  ·  {count}")
    except Exception:
        pass

    active = bool(getattr(self, "_v3_queue_active", False))
    try:
        self.queue_clear_button.configure(
            state="disabled" if active or not items else "normal"
        )
    except Exception:
        pass

    if not items:
        empty = ctk.CTkFrame(
            self.queue_items_frame,
            fg_color="transparent",
            corner_radius=12,
        )
        empty.pack(fill="x", padx=10, pady=24)
        ctk.CTkLabel(
            empty,
            text="Your queue is empty",
            font=(APP_FONT, 18, "bold"),
            text_color=palette["text"],
        ).pack(anchor="center", pady=(15, 5))
        ctk.CTkLabel(
            empty,
            text="Add a YouTube or YouTube Music link from the Downloader tab.",
            font=(APP_FONT, 12),
            text_color=palette["muted"],
            wraplength=690,
            justify="center",
        ).pack(anchor="center", pady=(0, 15))
        self._queue_row_widgets.append(empty)
        return

    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue

        queue_id = str(item.get("queue_id") or id(item))
        item.setdefault("queue_id", queue_id)
        item.setdefault("status", "Queued")

        status = str(item.get("status") or "Queued")
        file_type = str(item.get("file_type") or "auto").lower()
        type_label = FILE_LABEL_BY_TYPE_V3.get(file_type, file_type.upper())
        quality = str(item.get("quality") or "Best available")
        subtitles = "Subtitles: EN / AR" if item.get("subtitles") else "Subtitles: off"
        source_url = str(item.get("url") or "")

        status_lower = status.lower()
        if status_lower == "processing":
            status_color = palette["orange"]
        elif status_lower == "failed":
            status_color = palette["red"]
        elif status_lower == "stopped":
            status_color = palette["orange"]
        else:
            status_color = palette["blue"]

        row = ctk.CTkFrame(
            self.queue_items_frame,
            fg_color=palette["surface"],
            corner_radius=14,
            border_width=1,
            border_color=palette["separator"],
        )
        row.pack(fill="x", padx=5, pady=5)
        row.grid_columnconfigure(0, weight=1)
        self._queue_row_widgets.append(row)

        ctk.CTkLabel(
            row,
            text=f"{index:02d}   {item.get('title') or type_label}",
            font=(APP_FONT, 12, "bold"),
            text_color=palette["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=(15, 8), pady=(11, 2))

        ctk.CTkLabel(
            row,
            text=status,
            font=(APP_FONT, 10, "bold"),
            text_color=status_color,
            fg_color=palette["surface_elevated"],
            corner_radius=8,
        ).grid(row=0, column=1, sticky="e", padx=(4, 10), pady=(10, 2))

        ctk.CTkButton(
            row,
            text="×",
            width=28,
            height=28,
            font=(APP_FONT, 15, "bold"),
            fg_color=palette["surface_elevated"],
            hover_color=palette["separator_hover"],
            text_color=palette["muted"],
            border_width=1,
            border_color=palette["separator"],
            corner_radius=9,
            state="disabled" if active else "normal",
            command=lambda qid=queue_id: self._queue_remove_item(qid),
        ).grid(row=0, column=2, padx=(0, 10), pady=(8, 2))

        ctk.CTkLabel(
            row,
            text=source_url,
            font=(APP_FONT, 11),
            text_color=palette["muted"],
            anchor="w",
            justify="left",
            wraplength=730,
        ).grid(row=1, column=0, columnspan=3, sticky="ew", padx=15, pady=(0, 4))

        ctk.CTkLabel(
            row,
            text=f"{type_label}    ·    {quality}    ·    {subtitles}",
            font=(APP_FONT, 10),
            text_color=palette["muted"],
            anchor="w",
        ).grid(row=2, column=0, columnspan=3, sticky="ew", padx=15, pady=(0, 11))


def _queue_refresh_ui(self):
    try:
        self.after(0, self._queue_render_queue)
    except Exception:
        pass


def _queue_remove_item(self, queue_id):
    if getattr(self, "_v3_queue_active", False):
        return
    items = list(getattr(self, "_v3_queue", []) or [])
    self._v3_queue = [
        item for item in items
        if str(item.get("queue_id") or id(item)) != str(queue_id)
    ]
    self._queue_refresh_ui()


def _queue_clear(self):
    if getattr(self, "_v3_queue_active", False):
        return
    self._v3_queue = []
    self._queue_set_status("Queue cleared.")
    self._queue_refresh_ui()


def _queue_open_tab(self):
    try:
        self.tabs.set("Queue")
        self._queue_refresh_ui()
    except Exception as exc:
        write_failure_log("queue_tab_open", exc)


def _queue_build_queue_tab(self, tab):
    tab.grid_columnconfigure(0, weight=1)
    tab.grid_rowconfigure(1, weight=1)

    palette = _queue_palette(self)
    header = ctk.CTkFrame(
        tab,
        fg_color=palette["surface"],
        corner_radius=18,
        border_width=1,
        border_color=palette["separator"],
    )
    header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
    header.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(
        header,
        text="Download Queue",
        font=(APP_FONT, 20, "bold"),
        text_color=palette["text"],
        anchor="w",
    ).grid(row=0, column=0, sticky="ew", padx=18, pady=(15, 2))

    ctk.CTkLabel(
        header,
        text="Add links from Downloader, then process them in order.",
        font=(APP_FONT, 11),
        text_color=palette["muted"],
        anchor="w",
        wraplength=700,
        justify="left",
    ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 13))

    self.queue_count_label = ctk.CTkLabel(
        header,
        text="0 items",
        font=(APP_FONT, 11, "bold"),
        text_color=palette["blue"],
        fg_color=palette["surface_elevated"],
        corner_radius=10,
    )
    self.queue_count_label.grid(row=0, column=1, sticky="e", padx=(5, 12), pady=(14, 3))

    self.queue_clear_button = ctk.CTkButton(
        header,
        text="Clear Queue",
        width=100,
        height=30,
        font=(APP_FONT, 10, "bold"),
        fg_color=palette["surface_elevated"],
        hover_color=palette["separator_hover"],
        text_color=palette["text"],
        border_width=1,
        border_color=palette["separator"],
        corner_radius=10,
        command=self._queue_clear,
    )
    self.queue_clear_button.grid(row=1, column=1, sticky="e", padx=(5, 12), pady=(0, 13))

    self.queue_items_frame = ctk.CTkScrollableFrame(
        tab,
        fg_color=palette["window_bg"],
        corner_radius=16,
        border_width=1,
        border_color=palette["separator"],
        scrollbar_button_color=palette["separator_hover"],
        scrollbar_button_hover_color=palette["muted"],
    )
    self.queue_items_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=8)
    self._queue_row_widgets = []

    activity = ctk.CTkFrame(
        tab,
        fg_color=palette["surface"],
        corner_radius=16,
        border_width=1,
        border_color=palette["separator"],
    )
    activity.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 8))
    activity.grid_columnconfigure(0, weight=1)

    self.queue_status_label = ctk.CTkLabel(
        activity,
        text="Queue is idle.",
        font=(APP_FONT, 12, "bold"),
        text_color=palette["text"],
        anchor="w",
    )
    self.queue_status_label.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 5))

    self.queue_progress = ctk.CTkProgressBar(
        activity,
        height=8,
        corner_radius=5,
        fg_color=palette["surface_elevated"],
        progress_color=palette["blue"],
    )
    self.queue_progress.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 7))
    self.queue_progress.set(0)

    self.queue_progress_message = ctk.CTkLabel(
        activity,
        text="Ready to process queued items.",
        font=(APP_FONT, 10),
        text_color=palette["muted"],
        anchor="w",
    )
    self.queue_progress_message.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))

    self.queue_progress_percent = ctk.CTkLabel(
        activity,
        text="0%",
        font=(APP_FONT, 10, "bold"),
        text_color=palette["muted"],
        anchor="e",
    )
    self.queue_progress_percent.grid(row=2, column=1, sticky="e", padx=(8, 16), pady=(0, 12))

    controls = ctk.CTkFrame(tab, fg_color="transparent")
    controls.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 14))
    controls.grid_columnconfigure(0, weight=1)
    controls.grid_columnconfigure(1, weight=1)
    self.queue_controls_frame = controls

    self.queue_process_button = ctk.CTkButton(
        controls,
        text="Process Queue",
        command=self._v3_process_queue,
        height=44,
        font=(APP_FONT, 14, "bold"),
        fg_color=palette["blue"],
        hover_color=palette["blue_hover"],
        text_color="#FFFFFF",
        corner_radius=12,
    )
    self.queue_process_button.grid(row=0, column=0, columnspan=2, sticky="ew")

    self.queue_pause_button = ctk.CTkButton(
        controls,
        text="Pause",
        command=self.toggle_pause,
        height=44,
        font=(APP_FONT, 13, "bold"),
        fg_color=palette["surface_elevated"],
        hover_color=palette["separator_hover"],
        text_color=palette["text"],
        border_width=1,
        border_color=palette["separator"],
        corner_radius=12,
    )
    self.queue_pause_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
    self.queue_pause_button.grid_remove()

    self.queue_resume_button = ctk.CTkButton(
        controls,
        text="Resume",
        command=self.toggle_pause,
        height=44,
        font=(APP_FONT, 13, "bold"),
        fg_color=palette["surface_elevated"],
        hover_color=palette["separator_hover"],
        text_color=palette["text"],
        border_width=1,
        border_color=palette["separator"],
        corner_radius=12,
    )
    self.queue_resume_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
    self.queue_resume_button.grid_remove()

    self.queue_stop_button = ctk.CTkButton(
        controls,
        text="Stop Queue",
        command=self.stop_active_process,
        height=44,
        font=(APP_FONT, 13, "bold"),
        fg_color=palette["red"],
        hover_color=palette["red_hover"],
        text_color="#FFFFFF",
        corner_radius=12,
    )
    self.queue_stop_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))
    self.queue_stop_button.grid_remove()

    self._v3_queue = getattr(self, "_v3_queue", [])
    self._v3_queue_active = False
    self._v3_queue_stop_requested = False
    self._queue_hide_activity_controls()
    self._queue_render_queue()


def _queue_show_activity_controls(self):
    try:
        self.queue_process_button.grid_remove()
        self.queue_resume_button.grid_remove()
        self.queue_pause_button.configure(state="normal")
        self.queue_stop_button.configure(state="normal")
        self.queue_pause_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.queue_stop_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        self.queue_clear_button.configure(state="disabled")
    except Exception:
        pass


def _queue_hide_activity_controls(self):
    try:
        self.queue_pause_button.grid_remove()
        self.queue_resume_button.grid_remove()
        self.queue_stop_button.grid_remove()
        self.queue_process_button.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.queue_process_button.configure(state="normal", text="Process Queue")
        self.queue_clear_button.configure(state="normal" if self._v3_queue else "disabled")
    except Exception:
        pass


def _queue_sync_pause_controls(self):
    if not getattr(self, "_v3_queue_active", False):
        return
    try:
        if self.is_paused:
            self.queue_pause_button.grid_remove()
            self.queue_resume_button.configure(state="normal")
            self.queue_resume_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        else:
            self.queue_resume_button.grid_remove()
            self.queue_pause_button.configure(state="normal")
            self.queue_pause_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
    except Exception:
        pass


def _queue_remove_item_from_model(self, item):
    current = list(getattr(self, "_v3_queue", []) or [])
    queue_id = str(item.get("queue_id") or id(item))
    self._v3_queue = [
        queued for queued in current
        if queued is not item and str(queued.get("queue_id") or id(queued)) != queue_id
    ]


def _queue_process_queue(self):
    if getattr(self, "_v3_queue_active", False) or getattr(self, "download_running", False):
        messagebox.showinfo(
            "Queue",
            "Another download is already running. Stop it or let it finish before processing the queue.",
        )
        return

    items = [item for item in list(getattr(self, "_v3_queue", []) or []) if isinstance(item, dict)]
    if not items:
        messagebox.showinfo("Queue", "The queue is empty. Add a link from the Downloader tab first.")
        self._queue_refresh_ui()
        return

    for item in items:
        item.setdefault("queue_id", str(time.time_ns()))
        item["status"] = "Queued"

    self._v3_queue_active = True
    self._v3_queue_stop_requested = False
    self._v3_queue_batch_total = len(items)
    self._v3_queue_item_index = 1
    self._v3_queue_item_total = len(items)
    self._v3_queue_completed = 0
    self._v3_queue_failed = 0
    self.stop_requested = False
    self.is_paused = False
    self.active_process = None
    self.download_running = True

    try:
        self.dl_start.configure(state="disabled", text=" Processing Queue...")
        self.dl_progress.set(0)
        self.dl_progress_percent.configure(text="0%")
        self.show_downloader_activity_ui()
    except Exception:
        pass

    self._queue_show_activity_controls()
    self._queue_set_status(f"Starting queue · {len(items)} item(s)")
    self.set_header_status("● QUEUE", busy=True)
    self.set_operation_progress("dl", 0, f"Queue ready · {len(items)} item(s)", taskbar=True)
    self._queue_refresh_ui()

    threading.Thread(
        target=self._v3_queue_worker,
        args=(items,),
        daemon=True,
    ).start()


def _queue_worker(self, items):
    completed = 0
    failed = 0
    stopped = False
    total = len(items)

    try:
        for index, item in enumerate(items, 1):
            if getattr(self, "_v3_queue_stop_requested", False):
                stopped = True
                break

            item["status"] = "Processing"
            self._v3_queue_item_index = index
            self._v3_queue_item_total = total
            self._v3_queue_batch_total = total
            self._last_download_outcome = "running"
            self._v3_selected_file_type = item.get("file_type") or "auto"
            self._v3_selected_file_quality = item.get("quality") or ""
            self._selected_file_type = self._v3_selected_file_type
            self._selected_file_quality = self._v3_selected_file_quality
            self._selected_download_format = self._v3_selected_file_quality
            self._selected_download_subtitles = bool(item.get("subtitles"))
            self.download_running = True
            self.stop_requested = False
            self.is_paused = False
            self.active_process = None

            self._queue_set_status(f"Processing item {index} of {total}…")
            self.set_operation_progress(
                "dl",
                0,
                f"Queue item {index}/{total} — preparing...",
                taskbar=True,
            )
            self._queue_refresh_ui()

            try:
                self._queue_v8_prepare_item_download(item)
                self.run_download_worker(item["url"])
            except DownloadCancelled:
                self._last_download_outcome = "cancelled"
            except Exception as exc:
                self._last_download_outcome = "failed"
                write_failure_log(
                    "queue_item_unhandled",
                    exc,
                    details=f"Queue item {index}/{total}\nURL: {item.get('url')}",
                )

            outcome = str(getattr(self, "_last_download_outcome", "success"))
            if getattr(self, "_v3_queue_stop_requested", False) or outcome == "cancelled":
                item["status"] = "Stopped"
                stopped = True
                self._queue_set_status(f"Stopped on item {index} of {total}. Remaining items are still queued.")
                self._queue_refresh_ui()
                break

            if outcome == "failed":
                item["status"] = "Failed"
                failed += 1
                self._queue_set_status(f"Item {index} failed. Continuing with the next queued item…")
            else:
                completed += 1
                _queue_remove_item_from_model(self, item)
                self._queue_set_status(f"Completed item {index} of {total}.")

            self.download_running = False
            self.active_process = None
            self.is_paused = False
            self.stop_requested = False
            self._queue_refresh_ui()
    except Exception as exc:
        failed += 1
        log_path = write_failure_log("queue_worker", exc)
        self._queue_set_status(f"Queue stopped after an unexpected error. Log: {log_path or FAILURE_LOG_DIR}")
    finally:
        self.download_running = False
        self.active_process = None
        self.is_paused = False
        self.stop_requested = False
        self._v3_queue_active = False
        self._v3_queue_stop_requested = False
        self._v3_queue_completed = completed
        self._v3_queue_failed = failed
        self._queue_active_item = None
        self.after(
            0,
            lambda c=completed, f=failed, t=total, stop=stopped: self._queue_finish_controls(c, f, t, stop),
        )


def _queue_finish_controls(self, completed, failed, total, stopped):
    try:
        _QUEUE_ORIGINAL_RESET_DOWNLOADER_UI(self)
    except Exception:
        pass

    self._queue_hide_activity_controls()
    remaining = len(getattr(self, "_v3_queue", []) or [])
    if stopped:
        message = f"Queue stopped · {completed}/{total} completed · {remaining} item(s) remain"
    elif failed:
        message = f"Queue finished · {completed}/{total} completed · {failed} failed · {remaining} remain"
    else:
        message = f"Queue complete · {completed}/{total} completed"

    try:
        self.queue_status_label.configure(text=message)
        self.queue_progress.set(min(1.0, completed / max(1, total)))
        self.queue_progress_percent.configure(text=f"{(completed / max(1, total)) * 100:.0f}%")
        self.queue_progress_message.configure(text=message)
        self.queue_clear_button.configure(state="normal" if remaining else "disabled")
    except Exception:
        pass

    try:
        self.set_operation_progress(
            "dl",
            (completed / max(1, total)) * 100.0,
            message,
            taskbar=False,
        )
        self.set_label(self.dl_status, f"Status: {message}")
    except Exception:
        pass

    self.set_header_status("● READY", busy=False)
    self._queue_refresh_ui()


def _queue_set_operation_progress(self, prefix, percent, message, taskbar=False):
    queue_progress = None
    if prefix == "dl" and getattr(self, "_v3_queue_active", False):
        try:
            local_value = max(0.0, min(100.0, float(percent)))
        except (TypeError, ValueError):
            local_value = 0.0

        playlist_context = getattr(self, "_dl_playlist_progress_context", None)
        if playlist_context:
            try:
                item_index, item_total = playlist_context
                item_total = max(1, int(item_total))
                item_index = max(1, min(item_total, int(item_index)))
                local_value = ((item_index - 1) + (local_value / 100.0)) / item_total * 100.0
            except Exception:
                pass

        total = max(1, int(getattr(self, "_v3_queue_batch_total", 1) or 1))
        index = max(1, min(total, int(getattr(self, "_v3_queue_item_index", 1) or 1)))
        queue_progress = ((index - 1) + (local_value / 100.0)) / total * 100.0
        queue_progress = max(0.0, min(100.0, queue_progress))

        if not playlist_context:
            percent = queue_progress

    _QUEUE_ORIGINAL_SET_OPERATION_PROGRESS(self, prefix, percent, message, taskbar=taskbar)

    if queue_progress is not None:
        def update_queue_meter(value=queue_progress, msg=str(message)):
            try:
                self.queue_progress.set(value / 100.0)
                self.queue_progress_percent.configure(text=f"{value:.0f}%")
                self.queue_progress_message.configure(text=msg)
            except Exception:
                pass
        try:
            self.after(0, update_queue_meter)
        except Exception:
            pass


def _queue_show_downloader_activity_ui(self):
    _QUEUE_ORIGINAL_SHOW_ACTIVITY_UI(self)
    if getattr(self, "_v3_queue_active", False):
        self._queue_show_activity_controls()


def _queue_hide_downloader_running_controls(self):
    if getattr(self, "_v3_queue_active", False):
        return
    _QUEUE_ORIGINAL_HIDE_RUNNING_CONTROLS(self)
    try:
        self._queue_hide_activity_controls()
    except Exception:
        pass


def _queue_reset_downloader_ui(self):
    if getattr(self, "_v3_queue_active", False):
        self.is_paused = False
        self.active_process = None
        try:
            self.after(0, self._queue_sync_pause_controls)
        except Exception:
            pass
        return
    _QUEUE_ORIGINAL_RESET_DOWNLOADER_UI(self)
    try:
        self._queue_hide_activity_controls()
    except Exception:
        pass


def _queue_toggle_pause(self):
    _QUEUE_ORIGINAL_TOGGLE_PAUSE(self)
    if getattr(self, "_v3_queue_active", False):
        try:
            self.after(0, self._queue_sync_pause_controls)
        except Exception:
            pass


def _queue_stop_active_process(self):
    if getattr(self, "_v3_queue_active", False):
        self._v3_queue_stop_requested = True
        self._queue_set_status("Stopping queue after the active item is cancelled…")
    _QUEUE_ORIGINAL_STOP_ACTIVE_PROCESS(self)


def _queue_current_final(self):
    value = self.dl_input.get().strip()
    if not value or not is_youtube_url(value):
        messagebox.showerror("Queue", "Enter a valid YouTube or YouTube Music URL first.")
        return

    file_type = _v3_file_type_id_final(self.dl_file_type.get()) if getattr(self, "dl_file_type", None) else "auto"
    quality = self.dl_format.get().strip() if getattr(self, "dl_format", None) and self._dl_quality_visible else ""
    if file_type in LOSSLESS_AUDIO_TYPES_V3:
        quality = _v3_audio_quality_options_final(file_type)[0][0]

    self._v3_queue = getattr(self, "_v3_queue", [])
    duplicate = any(
        str(item.get("url") or "") == value
        and item.get("file_type") == file_type
        and item.get("quality") == quality
        for item in self._v3_queue
        if isinstance(item, dict)
    )
    if duplicate:
        self._queue_set_status("That link and format are already in the queue.")
        return

    self._v3_queue.append({
        "queue_id": str(time.time_ns()),
        "url": value,
        "file_type": file_type,
        "quality": quality,
        "subtitles": bool(self.dl_subs.get()) if hasattr(self, "dl_subs") else False,
        "status": "Queued",
    })
    self._queue_set_status("Added to queue.")
    self._queue_refresh_ui()


def _queue_install_preview_button(self):
    """Keep Add to Queue visible and replace the old ellipsis with a Queue shortcut."""
    try:
        utility = self.dl_queue_count.master
        inspect_button = None
        add_button = None
        check_button = None

        for widget in list(utility.winfo_children()):
            if not isinstance(widget, ctk.CTkButton):
                continue
            label = str(widget.cget("text") or "").strip().lower()
            if "process queue" in label:
                widget.destroy()
            elif "inspect details" in label:
                inspect_button = widget
            elif "queue" in label and "check" not in label:
                add_button = widget
            elif "check yt-dlp" in label:
                check_button = widget

        if inspect_button:
            self.dl_inspect_details_button = inspect_button
            inspect_button.grid_configure(row=1, column=0, sticky="w", pady=(6, 0))
        if add_button:
            self.dl_add_queue_button = add_button
            add_button.configure(text="＋ Add to Queue", width=130)
            add_button.grid_configure(row=1, column=1, sticky="w", pady=(6, 0))

        if not check_button:
            check_button = ctk.CTkButton(
                utility,
                text="↻ Check yt-dlp",
                width=120,
                height=30,
                font=(APP_FONT, 10, "bold"),
                fg_color="transparent",
                hover_color=APPLE_SEPARATOR_HOVER,
                text_color=APPLE_TEXT,
                corner_radius=10,
                command=self._v3_check_ytdlp_update,
            )
            check_button.grid(row=2, column=0, sticky="w", pady=(5, 0))
        self.dl_check_ytdlp_button = check_button
        check_button.grid_configure(row=2, column=0, sticky="w", pady=(5, 0))
        self.dl_queue_count.grid_configure(row=2, column=1, sticky="e", pady=(5, 0))
    except Exception as exc:
        write_failure_log("queue_downloader_utility_setup", exc)

    try:
        preview = self.dl_preview_card
        preview.grid_columnconfigure(2, weight=0)

        for old_button in (
            getattr(self, "dl_preview_menu_button", None),
            getattr(self, "dl_queue_access_button", None),
        ):
            if old_button is not None:
                try:
                    old_button.destroy()
                except Exception:
                    pass

        palette = _queue_palette(self)
        self.dl_queue_access_button = ctk.CTkButton(
            preview,
            text=f"☷  Queue  ·  {len(getattr(self, '_v3_queue', []) or [])}",
            width=112,
            height=32,
            font=(APP_FONT, 11, "bold"),
            fg_color=palette["surface_elevated"],
            hover_color=palette["separator_hover"],
            text_color=palette["text"],
            border_width=1,
            border_color=palette["separator"],
            corner_radius=10,
            command=self.open_queue_tab,
        )
        self.dl_queue_access_button.grid(
            row=0,
            column=2,
            sticky="ne",
            padx=(0, 12),
            pady=(10, 10),
        )
        self._queue_refresh_ui()
    except Exception as exc:
        write_failure_log("queue_preview_button_install", exc)


def _queue_preview_menu(self):
    """The old popover no longer processes the queue; Queue has its own tab."""
    import tkinter as tk
    palette = _queue_palette(self)
    menu = tk.Menu(
        self,
        tearoff=False,
        bg=palette["surface"],
        fg=palette["text"],
        activebackground=palette["blue"],
        activeforeground="#FFFFFF",
        borderwidth=1,
        relief="solid",
        font=(APP_FONT, 10),
    )
    menu.add_command(label="ⓘ  Inspect Details", command=self._v3_show_media_details)
    menu.add_command(label="↻  Check yt-dlp", command=self._v3_check_ytdlp_update)
    return menu


def _queue_show_preview_action(self):
    self.open_queue_tab()


_QUEUE_ORIGINAL_RESET_DOWNLOADER_UI = YTMMusicToolkit.reset_downloader_ui
_QUEUE_ORIGINAL_SHOW_ACTIVITY_UI = YTMMusicToolkit.show_downloader_activity_ui
_QUEUE_ORIGINAL_HIDE_RUNNING_CONTROLS = YTMMusicToolkit.hide_downloader_running_controls
_QUEUE_ORIGINAL_TOGGLE_PAUSE = YTMMusicToolkit.toggle_pause
_QUEUE_ORIGINAL_STOP_ACTIVE_PROCESS = YTMMusicToolkit.stop_active_process
_QUEUE_ORIGINAL_SET_OPERATION_PROGRESS = YTMMusicToolkit.set_operation_progress

YTMMusicToolkit.build_queue_tab = _queue_build_queue_tab
YTMMusicToolkit._queue_set_status = _queue_set_status
YTMMusicToolkit.open_queue_tab = _queue_open_tab
YTMMusicToolkit._queue_render_queue = _queue_render_queue
YTMMusicToolkit._queue_refresh_ui = _queue_refresh_ui
YTMMusicToolkit._queue_remove_item = _queue_remove_item
YTMMusicToolkit._queue_clear = _queue_clear
YTMMusicToolkit._queue_show_activity_controls = _queue_show_activity_controls
YTMMusicToolkit._queue_hide_activity_controls = _queue_hide_activity_controls
YTMMusicToolkit._queue_sync_pause_controls = _queue_sync_pause_controls
YTMMusicToolkit._queue_finish_controls = _queue_finish_controls
YTMMusicToolkit._queue_remove_item_from_model = _queue_remove_item_from_model
YTMMusicToolkit._v3_queue_current = _queue_current_final
YTMMusicToolkit._v3_process_queue = _queue_process_queue
YTMMusicToolkit._v3_queue_worker = _queue_worker
YTMMusicToolkit._v4_install_preview_menu = _queue_install_preview_button
YTMMusicToolkit._v4_preview_menu = _queue_preview_menu
YTMMusicToolkit._v4_show_preview_menu = _queue_show_preview_action
YTMMusicToolkit.reset_downloader_ui = _queue_reset_downloader_ui
YTMMusicToolkit.show_downloader_activity_ui = _queue_show_downloader_activity_ui
YTMMusicToolkit.hide_downloader_running_controls = _queue_hide_downloader_running_controls
YTMMusicToolkit.toggle_pause = _queue_toggle_pause
YTMMusicToolkit.stop_active_process = _queue_stop_active_process
YTMMusicToolkit.set_operation_progress = _queue_set_operation_progress



# ============================================================
# PLAYLISTS BECOME INDIVIDUAL QUEUE ITEMS (V8)
# ============================================================


def _queue_v8_capture_quality_policy(self):
    file_type = _v3_file_type_id_final(
        self.dl_file_type.get() if getattr(self, "dl_file_type", None) else "auto"
    )
    current_label = ""
    try:
        current_label = str(self.dl_format.get() or "").strip()
    except Exception:
        pass

    if file_type in AUDIO_FILE_TYPES_V3:
        options = _v3_audio_quality_options_final(file_type)
        for label, spec in options:
            if str(label).strip() == current_label:
                chosen = dict(spec)
                chosen["file_type"] = file_type
                return str(label).strip(), chosen
        if options:
            label, spec = options[0]
            chosen = dict(spec)
            chosen["file_type"] = file_type
            return str(label).strip(), chosen

    for label, spec in list(getattr(self, "_dl_preview_quality_options", []) or []):
        if str(label).strip() == current_label and isinstance(spec, dict) and spec.get("kind") == "video":
            chosen = dict(spec)
            chosen["file_type"] = file_type
            clean_label = str(label).strip()
            if chosen.get("best_per_item"):
                clean_label = "Best Option Separate"
            return clean_label, chosen

    if current_label.lower() == "best option separate":
        return "Best Option Separate", {"kind": "video", "best_per_item": True, "file_type": file_type}

    match = re.search(r"\b(4320|2160|1440|1080|720|576|480|360)\s*[pP]\b", current_label)
    if match:
        height = int(match.group(1))
        return current_label, {
            "kind": "video", "height": height, "best": False,
            "playlist_ceiling": True, "file_type": file_type,
        }

    return "Best Option Separate", {"kind": "video", "best_per_item": True, "file_type": file_type}


def _queue_v8_add_playlist_to_queue(self):
    source_url = str(self.dl_input.get() or "").strip()
    if not source_url or not is_playlist_url(source_url):
        messagebox.showerror("Playlist Queue", "Enter a YouTube or YouTube Music playlist URL first.")
        self._queue_v8_update_main_action_button()
        return

    if getattr(self, "_v3_queue_active", False) or getattr(self, "download_running", False):
        messagebox.showinfo("Playlist Queue", "Wait for the current download or queue to finish before adding another playlist.")
        return
    if getattr(self, "_queue_playlist_loading", False):
        return

    quality_label, quality_spec = self._queue_v8_capture_quality_policy()
    file_type = str(quality_spec.get("file_type") or getattr(self, "_v3_selected_file_type", "auto") or "auto").lower()
    snapshot = {
        "file_type": file_type,
        "quality": quality_label,
        "quality_spec": dict(quality_spec),
        "subtitles": bool(self.dl_subs.get()) if hasattr(self, "dl_subs") else False,
        "playlist_uses_ytm": is_youtube_music_url(source_url),
    }

    self._queue_playlist_loading = True
    self._queue_set_status("Reading playlist tracks…")
    try:
        self.dl_start.configure(state="disabled", text=" Reading Playlist…")
    except Exception:
        pass

    threading.Thread(
        target=self._queue_v8_resolve_playlist_worker,
        args=(source_url, snapshot),
        daemon=True,
    ).start()


def _queue_v8_resolve_playlist_worker(self, source_url, snapshot):
    try:
        resolver = self.ensure_resolver()
        entries = resolver.resolve_playlist_urls(source_url)
        if not entries:
            raise RuntimeError("The playlist returned no readable video entries.")

        prepared = []
        total = len(entries)
        for index, entry in enumerate(entries, 1):
            if not isinstance(entry, dict):
                continue

            video_id = str(
                entry.get("video_id") or entry.get("id") or entry.get("videoId") or ""
            ).strip()
            candidate = str(
                entry.get("source_url") or entry.get("webpage_url") or entry.get("url") or ""
            ).strip()
            if not video_id:
                video_id = str(extract_youtube_video_id(candidate) or "").strip()
            if not video_id:
                continue

            track_url = f"https://www.youtube.com/watch?v={video_id}"
            try:
                metadata = resolver.metadata_from_playlist_entry(entry, track_url)
            except Exception as metadata_exc:
                metadata = None
                write_failure_log(
                    "queue_playlist_track_metadata",
                    metadata_exc,
                    details=f"Track {index}/{total}: {track_url}",
                )

            title = str(
                (metadata or {}).get("title")
                or entry.get("track")
                or entry.get("title")
                or entry.get("fulltitle")
                or f"Track {index}"
            ).strip()

            prepared.append({
                "url": track_url,
                "video_id": video_id,
                "title": title,
                "playlist_metadata": metadata,
                "playlist_uses_ytm": bool(snapshot.get("playlist_uses_ytm")),
                "ytmusic_liked_entry": bool(entry.get("ytmusic_liked_entry")),
                "playlist_index": index,
                "playlist_total": total,
                "playlist_title": str(entry.get("playlist_title") or entry.get("playlist") or ""),
            })

        if not prepared:
            raise RuntimeError("No playlist tracks had usable YouTube video IDs.")

        self.after(
            0,
            lambda rows=prepared, url=source_url, settings=dict(snapshot): self._queue_v8_finish_playlist_add(
                url, settings, rows, None
            ),
        )
    except Exception as exc:
        log_path = write_failure_log("queue_playlist_resolve", exc, details=f"Playlist: {source_url}")
        message = str(exc)
        if log_path:
            message += f"\nFailure log: {log_path}"
        self.after(
            0,
            lambda err=message, url=source_url, settings=dict(snapshot): self._queue_v8_finish_playlist_add(
                url, settings, [], err
            ),
        )


def _queue_v8_finish_playlist_add(self, source_url, snapshot, rows, error=None):
    self._queue_playlist_loading = False
    if error:
        self._queue_set_status("Could not read playlist.")
        self._queue_v8_update_main_action_button()
        messagebox.showerror("Playlist Queue", error)
        return

    self._v3_queue = getattr(self, "_v3_queue", [])
    existing = {
        (str(item.get("url") or ""), str(item.get("file_type") or "auto"), str(item.get("quality") or ""))
        for item in self._v3_queue
        if isinstance(item, dict)
    }

    added = 0
    skipped = 0
    total = len(rows)
    for row in rows:
        item_url = str(row.get("url") or "").strip()
        if not item_url:
            continue

        file_type = str(snapshot.get("file_type") or "auto").lower()
        quality_label = str(snapshot.get("quality") or "Best Option Separate")
        key = (item_url, file_type, quality_label)
        if key in existing:
            skipped += 1
            continue

        quality_spec = dict(snapshot.get("quality_spec") or {})
        if quality_spec:
            quality_spec["file_type"] = file_type

        self._v3_queue.append({
            "queue_id": str(time.time_ns()),
            "url": item_url,
            "video_id": row.get("video_id") or extract_youtube_video_id(item_url),
            "title": row.get("title") or item_url,
            "file_type": file_type,
            "quality": quality_label,
            "quality_spec": quality_spec,
            "subtitles": bool(snapshot.get("subtitles")),
            "status": "Queued",
            "playlist_title": row.get("playlist_title") or "",
            "playlist_index": row.get("playlist_index"),
            "playlist_total": row.get("playlist_total") or total,
            "playlist_metadata": row.get("playlist_metadata"),
            "playlist_uses_ytm": bool(row.get("playlist_uses_ytm")),
            "ytmusic_liked_entry": bool(row.get("ytmusic_liked_entry")),
        })
        existing.add(key)
        added += 1

    if added:
        message = f"Added {added} playlist track(s) to the queue."
        if skipped:
            message += f" Skipped {skipped} duplicate item(s)."
        self._queue_set_status(message)
        self._queue_refresh_ui()
        try:
            self.tabs.set("Queue")
        except Exception:
            pass
    else:
        self._queue_set_status("All tracks from this playlist are already in the queue.")
        self._queue_refresh_ui()

    self._queue_v8_update_main_action_button()


def _queue_v8_queue_current(self):
    current_url = str(self.dl_input.get() or "").strip()
    if is_playlist_url(current_url):
        return self.add_playlist_to_queue()
    if not current_url or not is_youtube_url(current_url):
        messagebox.showerror("Queue", "Enter a valid YouTube or YouTube Music URL first.")
        return

    quality_label, quality_spec = self._queue_v8_capture_quality_policy()
    file_type = str(quality_spec.get("file_type") or getattr(self, "_v3_selected_file_type", "auto") or "auto").lower()
    quality_spec = dict(quality_spec)
    quality_spec["file_type"] = file_type

    self._v3_queue = getattr(self, "_v3_queue", [])
    duplicate = any(
        isinstance(item, dict)
        and str(item.get("url") or "") == current_url
        and str(item.get("file_type") or "auto") == file_type
        and str(item.get("quality") or "") == quality_label
        for item in self._v3_queue
    )
    if duplicate:
        self._queue_set_status("That link and format are already in the queue.")
        return

    title = ""
    try:
        if str(getattr(self, "_dl_preview_source", "") or "").strip() == current_url:
            candidate = str(self.dl_title.cget("text") or "").strip()
            if candidate and not candidate.lower().startswith(("waiting", "resolving", "reading")):
                title = candidate
    except Exception:
        pass

    self._v3_queue.append({
        "queue_id": str(time.time_ns()),
        "url": current_url,
        "video_id": extract_youtube_video_id(current_url) or "",
        "title": title,
        "file_type": file_type,
        "quality": quality_label,
        "quality_spec": quality_spec,
        "subtitles": bool(self.dl_subs.get()) if hasattr(self, "dl_subs") else False,
        "status": "Queued",
    })
    self._queue_set_status("Added to queue.")
    self._queue_refresh_ui()


def _queue_v8_prepare_item_download(self, item):
    """Resolve this item's requested ceiling against its actual formats."""
    source_url = str(item.get("url") or "").strip()
    if not source_url or is_playlist_url(source_url):
        raise RuntimeError("Queue items must be individual video URLs, not playlist URLs.")

    file_type = str(item.get("file_type") or "auto").lower()
    requested = dict(item.get("quality_spec") or {})
    requested["file_type"] = file_type
    extractor_arg = LIKED_MUSIC_EXTRACTOR_ARG if item.get("ytmusic_liked_entry") else None

    if requested.get("kind") == "audio" or file_type in AUDIO_FILE_TYPES_V3:
        if requested.get("kind") != "audio":
            options = _v3_audio_quality_options_final(file_type)
            wanted = str(item.get("quality") or "")
            requested = next(
                (dict(spec) for label, spec in options if str(label).strip() == wanted.strip()),
                dict(options[0][1]) if options else {},
            )
        resolved_spec = dict(requested)
        resolved_spec["file_type"] = file_type
    else:
        try:
            maximum_height = int(requested.get("height") or 0)
        except (TypeError, ValueError):
            maximum_height = 0
        best_per_item = bool(requested.get("best_per_item")) or maximum_height <= 0

        formats, actual_extractor_arg = inspect_youtube_formats(
            source_url,
            timeout=45,
            preferred_strategy=extractor_arg,
        )
        extractor_arg = actual_extractor_arg
        options = _v3_quality_options_final(formats, file_type, "single")
        resolved_spec = select_best_video_quality_spec(
            options,
            maximum_height=None if best_per_item else maximum_height,
        )
        if not resolved_spec:
            ceiling = "" if best_per_item else f" at or below {maximum_height}p"
            raise RuntimeError(f"No usable video format{ceiling} was found for this queue item.")
        resolved_spec = dict(resolved_spec)
        resolved_spec["file_type"] = file_type

    quality_label = str(item.get("quality") or "Best available")
    self._queue_active_item = item
    self._v5_pending_spec = None
    self._v3_selected_file_type = file_type
    self._v3_selected_file_quality = quality_label
    self._selected_file_type = file_type
    self._selected_file_quality = quality_label
    self._selected_download_format = dict(resolved_spec)
    self._selected_download_subtitles = bool(item.get("subtitles"))
    self._dl_preview_quality_options = [(quality_label, dict(resolved_spec))]
    self._dl_preview_quality_source = source_url
    self._dl_preview_mode = "single"
    self._dl_preview_quality_mode = "single"
    self._dl_preview_is_playlist = False
    self._dl_youtube_extractor_arg = extractor_arg
    self._last_quality_extractor_arg = extractor_arg


def _queue_v8_set_playlist_quality_options(self):
    source_url = str(self.dl_input.get() or "").strip()
    if not source_url or not is_playlist_url(source_url):
        return

    file_type = _v3_file_type_id_final(
        self.dl_file_type.get() if getattr(self, "dl_file_type", None) else "auto"
    )
    self._v3_selected_file_type = file_type
    self._dl_preview_quality_source = source_url
    self._dl_preview_mode = "playlist"
    self._dl_preview_quality_mode = "playlist"
    self._dl_preview_is_playlist = True

    if file_type in AUDIO_FILE_TYPES_V3:
        try:
            self._v3_file_type_changed(self.dl_file_type.get())
        except Exception:
            pass
        return

    selected = ""
    try:
        selected = str(self.dl_format.get() or "").strip()
    except Exception:
        pass

    options = _v3_video_quality_options_final(
        getattr(self, "_v3_preview_formats", []) or [],
        file_type,
        "playlist",
    )
    labels = [label for label, _ in options]
    normalized = {str(label).strip(): label for label in labels}
    chosen = normalized.get(
        selected,
        next((label for label in labels if str(label).strip() == "Best Option Separate"), labels[0] if labels else ""),
    )

    self._dl_preview_quality_options = options
    self._dl_quality_visible = bool(options)
    try:
        self.dl_quality_label.configure(text=" File Quality")
        self.dl_quality_label.grid(row=0, column=1, sticky="w", padx=22, pady=(14, 4))
        self.dl_format.grid(row=1, column=1, sticky="ew", padx=22, pady=(0, 8))
        self.dl_format.configure(values=labels)
        if chosen:
            self.dl_format.set(chosen)
            self._v3_selected_file_quality = str(chosen).strip()
    except Exception:
        pass


def _queue_v8_update_main_action_button(self):
    try:
        if getattr(self, "_v3_queue_active", False) or getattr(self, "download_running", False):
            return
        if getattr(self, "_queue_playlist_loading", False):
            self.dl_start.configure(state="disabled", text=" Reading Playlist…")
            return

        current_url = str(self.dl_input.get() or "").strip()
        if current_url and is_playlist_url(current_url):
            self.dl_start.configure(
                state="normal",
                text=" Add Playlist to Queue",
                command=self.add_playlist_to_queue,
            )
        else:
            self.dl_start.configure(
                state="normal",
                text=" Start Download",
                command=self.start_download,
            )
    except Exception:
        pass


def _queue_v8_target_changed(self, *args):
    _QUEUE_V8_ORIGINAL_TARGET_CHANGED(self, *args)
    self._queue_v8_set_playlist_quality_options()
    self._queue_v8_update_main_action_button()


def _queue_v8_install_preview_button(self):
    _QUEUE_V8_ORIGINAL_INSTALL_PREVIEW(self)
    self._queue_v8_set_playlist_quality_options()
    self._queue_v8_update_main_action_button()


def _queue_v8_show_quality_selector(self, quality_options=None, animated=True, source_value="", source_mode=None):
    source = str(source_value or self._dl_preview_quality_source or self.dl_input.get()).strip()
    if self.downloader_quality_mode_for_source(source) != "playlist":
        return _QUEUE_V8_ORIGINAL_SHOW_QUALITY_SELECTOR(
            self,
            quality_options=quality_options,
            animated=animated,
            source_value=source,
            source_mode=source_mode,
        )

    previous = ""
    try:
        previous = str(self.dl_format.get() or "").strip()
    except Exception:
        pass

    result = _QUEUE_V8_ORIGINAL_SHOW_QUALITY_SELECTOR(
        self,
        quality_options=quality_options,
        animated=animated,
        source_value=source,
        source_mode=source_mode,
    )
    try:
        labels = [str(label).strip() for label, _ in (self._dl_preview_quality_options or [])]
        if previous and previous in labels:
            actual = next(label for label in self.dl_format.cget("values") if str(label).strip() == previous)
            self.dl_format.set(actual)
            self._v3_selected_file_quality = previous
    except Exception:
        pass
    return result


def _queue_v8_start_download(self):
    current_url = str(self.dl_input.get() or "").strip()
    if current_url and is_playlist_url(current_url):
        return self.add_playlist_to_queue()
    return _QUEUE_V8_ORIGINAL_START_DOWNLOAD(self)


def _queue_v8_finish_controls(self, completed, failed, total, stopped):
    _QUEUE_V8_ORIGINAL_FINISH_CONTROLS(self, completed, failed, total, stopped)
    self._queue_v8_update_main_action_button()


_QUEUE_V8_ORIGINAL_TARGET_CHANGED = YTMMusicToolkit.on_downloader_target_changed
_QUEUE_V8_ORIGINAL_INSTALL_PREVIEW = YTMMusicToolkit._v4_install_preview_menu
_QUEUE_V8_ORIGINAL_START_DOWNLOAD = YTMMusicToolkit.start_download
_QUEUE_V8_ORIGINAL_FINISH_CONTROLS = YTMMusicToolkit._queue_finish_controls
_QUEUE_V8_ORIGINAL_SHOW_QUALITY_SELECTOR = YTMMusicToolkit.show_download_quality_selector
_QUEUE_V8_ORIGINAL_RESET_DOWNLOADER_UI = YTMMusicToolkit.reset_downloader_ui


def _queue_v8_reset_downloader_ui(self):
    _QUEUE_V8_ORIGINAL_RESET_DOWNLOADER_UI(self)
    self._queue_v8_update_main_action_button()


YTMMusicToolkit.add_playlist_to_queue = _queue_v8_add_playlist_to_queue
YTMMusicToolkit._queue_v8_capture_quality_policy = _queue_v8_capture_quality_policy
YTMMusicToolkit._queue_v8_resolve_playlist_worker = _queue_v8_resolve_playlist_worker
YTMMusicToolkit._queue_v8_finish_playlist_add = _queue_v8_finish_playlist_add
YTMMusicToolkit._queue_v8_prepare_item_download = _queue_v8_prepare_item_download
YTMMusicToolkit._queue_v8_set_playlist_quality_options = _queue_v8_set_playlist_quality_options
YTMMusicToolkit._queue_v8_update_main_action_button = _queue_v8_update_main_action_button
YTMMusicToolkit._queue_current_final = _queue_v8_queue_current
YTMMusicToolkit._v3_queue_current = _queue_v8_queue_current
YTMMusicToolkit.on_downloader_target_changed = _queue_v8_target_changed
YTMMusicToolkit._v4_install_preview_menu = _queue_v8_install_preview_button
YTMMusicToolkit.show_download_quality_selector = _queue_v8_show_quality_selector
YTMMusicToolkit.start_download = _queue_v8_start_download
YTMMusicToolkit.reset_downloader_ui = _queue_v8_reset_downloader_ui
YTMMusicToolkit._queue_finish_controls = _queue_v8_finish_controls


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        app = YTMMusicToolkit()
        app.mainloop()
    except Exception as fatal:
        log_path = write_failure_log(
            "fatal_startup",
            fatal,
        )
        try:
            messagebox.showerror(
                APP_NAME,
                f"Fatal startup error:\n\n{fatal}\n\nFailure log:\n{log_path or FAILURE_LOG_DIR}",
            )
        except Exception:
            pass
