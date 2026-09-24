import os
import re
from pathlib import Path
from io import BytesIO
import requests
from PIL import Image

from mutagen.flac import FLAC, Picture
from ytmusicapi import YTMusic
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# ============================================================
# CONFIGURATION & API CREDENTIALS
# ============================================================

# Spotify API credentials (Set via environment variables or paste strings here directly)
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID", "YOUR_SPOTIFY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET", "YOUR_SPOTIFY_CLIENT_SECRET")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def exact_artist_match(target_artist, result_artist):
    """Enforces strict character-for-character matching (ignoring case and whitespace)."""
    if not target_artist or not result_artist:
        return False
    return target_artist.strip().lower() == result_artist.strip().lower()

def derive_title_from_filename(file_path):
    name = file_path.stem
    name = re.sub(r"^\d+[\s._\-]+", "", name)
    return name.replace("_", " ").strip()

def inspect_image_from_url(url):
    """Downloads image in memory and calculates total pixel resolution (width * height)."""
    if not url:
        return None, 0, 0
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 200:
            img_data = resp.content
            img = Image.open(BytesIO(img_data))
            w, h = img.size
            return img_data, w, (w * h)
    except Exception:
        pass
    return None, 0, 0

# ============================================================
# DATABASE FETCHERS
# ============================================================

def fetch_spotify_cover(sp, artist, title):
    """Query Spotify API."""
    if not sp:
        return None, 0, ""
    try:
        query = f"track:{title} artist:{artist}"
        res = sp.search(q=query, type="track", limit=5)
        items = res.get("tracks", {}).get("items", [])

        for item in items:
            artists = [a.get("name", "") for a in item.get("artists", [])]
            # Exact letter-for-letter match check on any listed track artist
            if any(exact_artist_match(artist, a) for a in artists):
                images = item.get("album", {}).get("images", [])
                if images:
                    url = images[0].get("url")  # Spotify's largest image is index 0 (640x640)
                    img_bytes, dim, pixels = inspect_image_from_url(url)
                    if img_bytes:
                        return img_bytes, pixels, f"Spotify ({dim}x{dim})"
    except Exception as e:
        print(f"      ⚠️ Spotify fetch error: {e}")
    return None, 0, ""

def fetch_deezer_cover(artist, title):
    """Query Deezer API."""
    try:
        url = f"https://api.deezer.com/search?q=artist:\"{artist}\" track:\"{title}\""
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            for item in data:
                res_artist = item.get("artist", {}).get("name", "")
                if exact_artist_match(artist, res_artist):
                    # Request maximum resolution cover XL (1000x1000)
                    cover_url = item.get("album", {}).get("cover_xl") or item.get("album", {}).get("cover_big")
                    img_bytes, dim, pixels = inspect_image_from_url(cover_url)
                    if img_bytes:
                        return img_bytes, pixels, f"Deezer ({dim}x{dim})"
    except Exception as e:
        print(f"      ⚠️ Deezer fetch error: {e}")
    return None, 0, ""

def fetch_ytmusic_cover(yt, artist, title):
    """Query YouTube Music API with strict 'songs' filter."""
    try:
        query = f"{artist} {title}".strip()
        results = yt.search(query, filter="songs", limit=10)

        for item in results:
            res_artists = [a.get("name", "") for a in item.get("artists", []) if isinstance(a, dict)]
            if any(exact_artist_match(artist, a) for a in res_artists):
                thumbnails = item.get("thumbnails", [])
                if thumbnails:
                    raw_url = thumbnails[-1].get("url", "")
                    # Strip thumbnail dimensions to fetch master image asset (=s0)
                    master_url = re.sub(r"=w\d+-h\d+.*$", "=s0", raw_url)
                    if "=s0" not in master_url:
                        master_url = re.sub(r"=s\d+.*$", "=s0", master_url)

                    img_bytes, dim, pixels = inspect_image_from_url(master_url)
                    if img_bytes:
                        return img_bytes, pixels, f"YouTube Music ({dim}x{dim})"
    except Exception as e:
        print(f"      ⚠️ YouTube Music fetch error: {e}")
    return None, 0, ""

# ============================================================
# MAIN PIPELINE
# ============================================================

def main():
    print("\n" + "=" * 65)
    print("STRICT MULTI-DATABASE HIGH-RES COVER ART UPGRADER")
    print("=" * 65 + "\n")

    user_path = input("ENTER MUSIC FOLDER PATH: ").strip().strip('"')
    music_folder = Path(user_path)

    if not music_folder.exists():
        print(f"❌ Folder '{music_folder}' does not exist.")
        return

    files = list(music_folder.rglob("*.flac"))
    print(f"Found {len(files)} FLAC file(s)\n")
    if not files:
        return

    # Initialize YTMusic
    yt = YTMusic()

    # Initialize Spotify (Graceful fallback if credentials are unset/invalid)
    sp = None
    try:
        if SPOTIPY_CLIENT_ID != "YOUR_SPOTIFY_CLIENT_ID" and SPOTIPY_CLIENT_SECRET != "YOUR_SPOTIFY_CLIENT_SECRET":
            auth_manager = SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET)
            sp = spotipy.Spotify(auth_manager=auth_manager)
            print("✅ Spotify API connected.")
        else:
            print("⚠️ Spotify credentials not set. Skipping Spotify database (Deezer + YTMusic active).")
    except Exception as e:
        print(f"⚠️ Spotify connection failed ({e}). Proceeding without Spotify.")

    print("-" * 65)

    for idx, file in enumerate(files, 1):
        print(f"[{idx}/{len(files)}] Processing: {file.name}")

        try:
            flac = FLAC(file)
            artist = flac.get("artist", [""])[0].strip()
            title = flac.get("title", [""])[0].strip() or derive_title_from_filename(file)

            if not artist:
                print("    ⚠️ Missing ARTIST tag. Cannot enforce strict artist match. Skipping...\n")
                continue

            print(f"    Tags -> Artist: '{artist}' | Title: '{title}'")

            # Collect covers from databases
            candidates = []

            # 1. Deezer (Often 1000x1000)
            d_bytes, d_pixels, d_label = fetch_deezer_cover(artist, title)
            if d_bytes:
                candidates.append((d_pixels, d_bytes, d_label))

            # 2. Spotify (Usually 640x640)
            if sp:
                s_bytes, s_pixels, s_label = fetch_spotify_cover(sp, artist, title)
                if s_bytes:
                    candidates.append((s_pixels, s_bytes, s_label))

            # 3. YouTube Music ("songs" tab enforcement)
            y_bytes, y_pixels, y_label = fetch_ytmusic_cover(yt, artist, title)
            if y_bytes:
                candidates.append((y_pixels, y_bytes, y_label))

            if not candidates:
                print("    ❌ No strict artist-matched artwork found across databases.\n")
                continue

            # Sort by highest pixel count (Resolution)
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_pixels, best_bytes, best_label = candidates[0]

            # Write highest quality cover to FLAC
            flac.clear_pictures()

            picture = Picture()
            picture.type = 3  # Front Cover
            picture.mime = "image/jpeg"
            picture.desc = "Front Cover"
            picture.data = best_bytes

            flac.add_picture(picture)
            flac.save()

            print(f"    ✨ Updated Cover! Winner: {best_label}\n")

        except Exception as e:
            print(f"    ❌ Error processing {file.name}: {e}\n")

    print("=" * 65)
    print("COVER ART UPGRADE COMPLETE")
    print("=" * 65)

if __name__ == "__main__":
    try:
        main()
    except Exception as fatal:
        print(f"\nFatal Error: {fatal}")
    finally:
        input("\nPress ENTER to exit...")