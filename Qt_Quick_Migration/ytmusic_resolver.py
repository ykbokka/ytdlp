from __future__ import annotations

import hashlib
import http.cookiejar
import http.cookies
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from ytmusicapi import YTMusic

try:
    from ytmusicapi.constants import USER_AGENT as YTMUSIC_USER_AGENT
except ImportError:
    YTMUSIC_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:88.0) "
        "Gecko/20100101 Firefox/88.0"
    )


def clean_text(value: Any) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = text.replace("&", "and")
    text = "".join(char if char.isalnum() or char.isspace() else " " for char in text)
    return " ".join(text.split())


def split_artist_title(value: str) -> tuple[str, str]:
    value = str(value or "").strip()
    for separator in (" - ", " – ", " — "):
        if separator in value:
            artist, title = value.split(separator, 1)
            if artist.strip() and title.strip():
                return artist.strip(), title.strip()
    return "", value


def exact_artist_name_match(target_artist: str, result_artist_names: list[str] | None) -> bool:
    if not target_artist:
        return True
    targets = [part.strip() for part in re.split(r"\s*(?:,|&)\s*", target_artist) if part.strip()]
    results = [str(name).strip() for name in (result_artist_names or []) if str(name).strip()]
    if not targets or not results:
        return False
    normalized_results = [clean_text(name) for name in results]
    return all(clean_text(name) in normalized_results for name in targets)


def title_score(wanted_title: str, result_title: str) -> int:
    wanted, result = clean_text(wanted_title), clean_text(result_title)
    if not wanted or not result:
        return 0
    if wanted == result:
        return 200
    if wanted in result or result in wanted:
        return 120
    wanted_tokens, result_tokens = set(wanted.split()), set(result.split())
    if not wanted_tokens or not result_tokens:
        return 0
    return int((len(wanted_tokens & result_tokens) / max(1, len(wanted_tokens))) * 80)


def canonicalize_thumbnail_url(url: str) -> str:
    url = str(url or "").strip()
    if not url:
        return ""
    url = re.sub(r"=w\d+(?:-h\d+[^&]*)?$", "=s0", url)
    url = re.sub(r"=w\d+-h\d+.*$", "=s0", url)
    url = re.sub(r"=s\d+.*$", "=s0", url)
    return url


def create_temporary_auth_from_cookie_file(cookie_path: str | Path) -> Path:
    cookie_path = Path(cookie_path)
    jar = http.cookiejar.MozillaCookieJar(str(cookie_path))
    try:
        jar.load(ignore_discard=True, ignore_expires=False)
    except Exception as exc:
        raise RuntimeError(f"Could not read cookies.txt: {type(exc).__name__}: {exc}") from exc

    request = urllib.request.Request(
        "https://music.youtube.com/youtubei/v1/browse",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    jar.add_cookie_header(request)
    cookie_header = request.get_header("Cookie") or ""
    if not cookie_header:
        raise RuntimeError("cookies.txt contains no active cookies for music.youtube.com.")

    if not re.search(r"(?:^|;\s*)__Secure-3PAPISID=", cookie_header, re.IGNORECASE):
        raise RuntimeError("cookies.txt does not contain an active __Secure-3PAPISID cookie for YouTube Music.")

    parsed = http.cookies.SimpleCookie()
    try:
        parsed.load(cookie_header.replace('"', ""))
        sapisid = parsed["__Secure-3PAPISID"].value
    except Exception as exc:
        raise RuntimeError("Could not read __Secure-3PAPISID from cookies.txt. Export a fresh signed-in session.") from exc

    timestamp = str(int(time.time()))
    digest = hashlib.sha1(
        f"{timestamp} {sapisid} https://music.youtube.com".encode("utf-8")
    ).hexdigest()
    authorization = f"SAPISIDHASH {timestamp}_{digest}"
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "Authorization": authorization,
        "Content-Encoding": "gzip",
        "Content-Type": "application/json",
        "Origin": "https://music.youtube.com",
        "X-Goog-AuthUser": "0",
        "x-origin": "https://music.youtube.com",
        "Cookie": cookie_header,
        "User-Agent": YTMUSIC_USER_AGENT,
    }

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=".ytmusic-auth-", suffix=".json", delete=False
        ) as stream:
            json.dump(headers, stream, ensure_ascii=False)
            temp_path = Path(stream.name)
        return temp_path
    except Exception:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        raise


class YTMResolver:
    """YT Music matcher using contributing-artist matching and title/album scoring."""

    def __init__(self, auth_file: str | Path | None = None):
        self.yt = YTMusic(str(auth_file)) if auth_file else YTMusic()
        self.year_cache: dict[str, str] = {}

    @staticmethod
    def artist_names(item: dict[str, Any]) -> list[str]:
        names = []
        for artist in item.get("artists", []) or []:
            name = artist.get("name", "") if isinstance(artist, dict) else str(artist)
            if name:
                names.append(str(name))
        if not names:
            fallback = item.get("artist") or item.get("author")
            if fallback:
                names = [str(fallback)]
        return names

    @staticmethod
    def album_name(item: dict[str, Any]) -> str:
        album = item.get("album")
        return str(album.get("name") or "") if isinstance(album, dict) else str(album or "")

    @staticmethod
    def thumbnail_candidates(item: dict[str, Any]) -> list[str]:
        thumbnails = [x for x in (item.get("thumbnails") or []) if isinstance(x, dict)]
        thumbnails.sort(
            key=lambda x: int(x.get("width", 0) or 0) * int(x.get("height", 0) or 0),
            reverse=True,
        )
        results = []
        for thumb in thumbnails:
            url = canonicalize_thumbnail_url(thumb.get("url") or "")
            if url and url not in results:
                results.append(url)
        return results

    def score(self, artist: str, album: str, title: str, item: dict[str, Any]) -> int:
        score = title_score(title, str(item.get("title") or ""))
        if artist and exact_artist_name_match(artist, self.artist_names(item)):
            score += 500
        wanted_album, result_album = clean_text(album), clean_text(self.album_name(item))
        if wanted_album and result_album:
            if wanted_album == result_album:
                score += 100
            elif wanted_album in result_album or result_album in wanted_album:
                score += 45
        return score

    def _year(self, item: dict[str, Any]) -> str:
        album = item.get("album")
        album_id = album.get("id") if isinstance(album, dict) else None
        if not album_id:
            return str(item.get("year") or "")
        if album_id not in self.year_cache:
            try:
                details = self.yt.get_album(album_id)
                self.year_cache[album_id] = str(details.get("year") or "")
            except Exception:
                self.year_cache[album_id] = ""
        return self.year_cache[album_id]

    def _build_result(self, item: dict[str, Any], source: str, fallback: bool = False) -> dict[str, Any]:
        artists = self.artist_names(item)
        candidates = self.thumbnail_candidates(item)
        album = item.get("album")
        return {
            "video_id": str(item.get("videoId") or item.get("video_id") or item.get("id") or ""),
            "title": str(item.get("title") or ""),
            "artist_names": artists,
            "artist": ", ".join(artists),
            "album": self.album_name(item),
            "album_id": album.get("id") if isinstance(album, dict) else None,
            "year": self._year(item),
            "cover_url": candidates[0] if candidates else "",
            "thumbnail_candidates": candidates,
            "source": source,
            "is_fallback": fallback,
        }

    def search(self, artist: str, title: str, album: str = "") -> dict[str, Any] | None:
        artist, title, album = str(artist or "").strip(), str(title or "").strip(), str(album or "").strip()
        query = f"{artist} {title}".strip() if artist else title
        if not query:
            return None

        try:
            songs = self.yt.search(query, filter="songs", limit=15, ignore_spelling=False) or []
        except Exception:
            songs = []
        exact_songs = [
            item for item in songs if isinstance(item, dict)
            and (not artist or exact_artist_name_match(artist, self.artist_names(item)))
        ]
        if exact_songs:
            best = max(exact_songs, key=lambda item: self.score(artist, album, title, item))
            return self._build_result(best, "YouTube Music Songs", False)

        try:
            videos = self.yt.search(query, filter="videos", limit=15, ignore_spelling=False) or []
        except Exception:
            videos = []
        if not videos:
            return None
        exact_videos = [
            item for item in videos if isinstance(item, dict)
            and (not artist or exact_artist_name_match(artist, self.artist_names(item)))
        ]
        pool = exact_videos or [item for item in videos if isinstance(item, dict)]
        if not pool:
            return None
        best = max(pool, key=lambda item: self.score(artist, album, title, item))
        return self._build_result(best, "YouTube Music Videos (Fallback)", True)

    def liked_songs(self, cookie_path: str = "", auth_file: str = "") -> list[dict[str, Any]]:
        candidates = []
        environment_auth = os.environ.get("YTM_MUSIC_TOOLKIT_YTMUSIC_AUTH_FILE", "").strip()
        if auth_file:
            candidates.append(Path(auth_file).expanduser())
        elif environment_auth:
            candidates.append(Path(environment_auth).expanduser())
        documents = Path.home() / "Documents" / "YTDLP"
        candidates.extend([documents / "ytmusicapi_browser.json", documents / "browser.json"])
        if getattr(sys, "_MEIPASS", None):
            candidates.append(Path(sys._MEIPASS) / "ytmusicapi_browser.json")
        if getattr(sys, "frozen", False):
            app_dir = Path(sys.executable).resolve().parent
        else:
            app_dir = Path(__file__).resolve().parent
        candidates.append(app_dir / "ytmusicapi_browser.json")
        auth_candidate = next((p for p in candidates if p.is_file()), None)

        last_errors = []
        if auth_candidate:
            try:
                return self._read_liked_songs(str(auth_candidate))
            except Exception as exc:
                last_errors.append(f"auth file {auth_candidate.name}: {type(exc).__name__}: {exc}")

        temporary = None
        try:
            if not cookie_path:
                raise RuntimeError("No valid cookies.txt is configured for Liked Music.")
            temporary = create_temporary_auth_from_cookie_file(cookie_path)
            return self._read_liked_songs(str(temporary))
        except Exception as exc:
            last_errors.append(f"cookies.txt: {type(exc).__name__}: {exc}")
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

        # Match the legacy application: if ytmusicapi rejects its generated
        # browser-auth headers, make one last attempt to enumerate list=LM with
        # yt-dlp using the same user-selected cookies file.
        if cookie_path:
            try:
                fallback = self._read_liked_songs_via_ytdlp(cookie_path)
                if fallback:
                    return fallback
                last_errors.append("yt-dlp cookies fallback: no usable playlist entries")
            except Exception as exc:
                last_errors.append(f"yt-dlp cookies fallback: {type(exc).__name__}: {exc}")

        raise RuntimeError("Could not read YouTube Music Liked Music. " + " | ".join(last_errors))

    @staticmethod
    def _read_liked_songs_via_ytdlp(cookie_path: str) -> list[dict[str, Any]]:
        roots = []
        if getattr(sys, "_MEIPASS", None):
            roots.append(Path(sys._MEIPASS))
        if getattr(sys, "frozen", False):
            roots.append(Path(sys.executable).resolve().parent)
        roots.append(Path(__file__).resolve().parent)
        executable = ""
        for root in roots:
            for name in ("yt-dlp.exe", "yt-dlp"):
                candidate = root / name
                if candidate.is_file():
                    executable = str(candidate)
                    break
            if executable:
                break
        executable = executable or shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
        if executable:
            command = [executable]
        else:
            try:
                import yt_dlp  # noqa: F401
                command = [sys.executable, "-m", "yt_dlp"]
            except ImportError as exc:
                raise RuntimeError("yt-dlp was not found for the Liked Music fallback.") from exc

        kwargs = {}
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs = {"startupinfo": startupinfo, "creationflags": subprocess.CREATE_NO_WINDOW}
        command.extend([
            "--ignore-config", "--no-warnings", "--ignore-errors",
            "--flat-playlist", "--dump-single-json", "--skip-download",
            "--cookies", str(cookie_path),
            "https://music.youtube.com/playlist?list=LM",
        ])
        proc = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=180, **kwargs
        )
        raw = (proc.stdout or "").strip()
        if not raw:
            raise RuntimeError((proc.stderr or "yt-dlp returned no playlist JSON")[-1400:])
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("yt-dlp returned invalid Liked Music playlist JSON.") from exc
        entries = payload.get("entries") if isinstance(payload, dict) else None
        results = []
        seen = set()
        for item in entries or []:
            if not isinstance(item, dict):
                continue
            video_id = str(item.get("id") or item.get("video_id") or item.get("videoId") or "").strip()
            title = str(item.get("title") or item.get("track") or "").strip()
            if not video_id or not title or video_id in seen:
                continue
            seen.add(video_id)
            artist_value = item.get("artist") or item.get("creator") or item.get("uploader") or item.get("channel") or ""
            if isinstance(artist_value, (list, tuple)):
                artist_value = ", ".join(str(name).strip() for name in artist_value if str(name).strip())
            album_value = item.get("album") or ""
            if isinstance(album_value, dict):
                album_value = str(album_value.get("name") or "")
            candidates = YTMResolver.thumbnail_candidates(item)
            direct_url = str(item.get("webpage_url") or item.get("url") or "")
            if not direct_url.startswith(("http://", "https://")):
                direct_url = f"https://www.youtube.com/watch?v={video_id}"
            metadata = {
                "video_id": video_id, "title": title, "artist": str(artist_value or ""),
                "album": str(album_value or ""), "year": str(item.get("release_year") or item.get("upload_date") or "")[:4],
                "cover_url": candidates[0] if candidates else "", "thumbnail_candidates": candidates,
                "source": "YouTube Music Liked Music (yt-dlp fallback)", "is_fallback": False,
            }
            results.append({
                "id": video_id, "video_id": video_id, "title": title, "track": title,
                "artist": str(artist_value or ""), "album": str(album_value or ""),
                "thumbnail": candidates[0] if candidates else "", "thumbnail_candidates": candidates,
                "ytm_metadata": metadata, "source_url": direct_url,
                "ytmusic_liked_entry": True, "status": "Pending", "duration": "—",
            })
        if not results:
            details = (proc.stderr or "No usable entries were returned.")[-1400:]
            raise RuntimeError(details)
        return results

    @staticmethod
    def _read_liked_songs(auth_file: str) -> list[dict[str, Any]]:
        client = YTMusic(auth_file)
        try:
            payload = client.get_liked_songs(limit=5000)
        except KeyError as exc:
            raise RuntimeError("YouTube Music did not return the signed-in Liked Music shelf. Update cookies.txt from the account that owns the likes.") from exc
        tracks = payload.get("tracks") if isinstance(payload, dict) else None
        results = []
        seen = set()
        for item in tracks or []:
            if not isinstance(item, dict):
                continue
            video_id = str(item.get("videoId") or item.get("video_id") or "").strip()
            title = str(item.get("title") or item.get("track") or "").strip()
            if not video_id or not title or video_id in seen:
                continue
            seen.add(video_id)
            artists = YTMResolver.artist_names(item)
            thumbnail_candidates = YTMResolver.thumbnail_candidates(item)
            album_value = item.get("album") or ""
            album_name = str(album_value.get("name") or "") if isinstance(album_value, dict) else str(album_value)
            metadata = {
                "video_id": video_id,
                "title": title,
                "artist": ", ".join(artists),
                "album": album_name,
                "year": str(item.get("year") or ""),
                "cover_url": thumbnail_candidates[0] if thumbnail_candidates else "",
                "thumbnail_candidates": thumbnail_candidates,
                "source": "YouTube Music Liked Music",
                "is_fallback": False,
            }
            results.append({
                "id": video_id,
                "video_id": video_id,
                "title": title,
                "track": title,
                "artist": ", ".join(artists),
                "artists": item.get("artists") or [],
                "album": album_value,
                "thumbnail": thumbnail_candidates[0] if thumbnail_candidates else "",
                "thumbnail_candidates": thumbnail_candidates,
                "ytm_metadata": metadata,
                "source_url": f"https://www.youtube.com/watch?v={video_id}",
                "ytmusic_liked_entry": True,
                "status": "Pending",
                "duration": "—",
            })
        if not results:
            raise RuntimeError("The authenticated YouTube Music API returned no usable Liked Music tracks.")
        return results
