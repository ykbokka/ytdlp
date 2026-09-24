from pathlib import Path
from io import BytesIO
import re
import time
import requests

from PIL import Image, ImageOps
from mutagen.flac import FLAC, Picture
from ytmusicapi import YTMusic

# ============================================================
# SETTINGS
# ============================================================

REQUEST_DELAY = 1.0
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def clean(text):
    text = str(text or "").lower()
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = text.replace("&", "and")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())

def derive_title_from_filename(filename):
    name = Path(filename).stem
    name = re.sub(r"^\d+[\s._\-]+", "", name)
    return name.replace("_", " ").strip()

def artist_matches(wanted_artist, result_artist):
    """Returns True if the target artist strictly or loosely matches the result artist."""
    if not wanted_artist:
        return True  # Can't validate if we don't have a target artist to check against
    
    w_art = clean(wanted_artist)
    r_art = clean(result_artist)
    
    if not r_art:
        return False
        
    return (w_art == r_art) or (w_art in r_art) or (r_art in w_art)

def score_match(wanted_artist, wanted_album, wanted_title, result_artist, result_album, result_title):
    score = 0
    w_art, w_alb, w_tit = clean(wanted_artist), clean(wanted_album), clean(wanted_title)
    r_art, r_alb, r_tit = clean(result_artist), clean(result_album), clean(result_title)

    if w_tit and r_tit:
        if w_tit == r_tit:
            score += 100
        elif w_tit in r_tit or r_tit in w_tit:
            score += 60

    if w_art and r_art:
        if w_art == r_art:
            score += 100
        elif w_art in r_art or r_art in w_art:
            score += 70

    if w_alb and r_alb:
        if w_alb == r_alb:
            score += 50
        elif w_alb in r_alb:
            score += 25

    return score

# ============================================================
# YOUTUBE MUSIC SEARCH (SONGS WITH ARTIST-MATCH CHECK -> FALLBACK)
# ============================================================

def resolve_metadata_ytmusic(yt, artist, album, title):
    raw_query = f"{artist} {title}".strip() if artist else title
    if not raw_query:
        return None

    try:
        best_match = None
        is_fallback = False

        # Attempt 1: Strict "songs" filter
        song_results = yt.search(raw_query, filter="songs", limit=10)

        if song_results:
            highest_score = 0
            candidate = None
            
            for item in song_results:
                res_title = item.get("title", "")
                res_artists = " ".join([a.get("name", "") for a in item.get("artists", []) if isinstance(a, dict)])
                res_album = item.get("album", {}).get("name", "") if item.get("album") else ""

                # Evaluate match quality
                score = score_match(artist, album, title, res_artists, res_album, res_title)
                if score > highest_score:
                    highest_score = score
                    candidate = item

            if not candidate:
                candidate = song_results[0]

            # Validate artist match
            cand_artists = " ".join([a.get("name", "") for a in candidate.get("artists", []) if isinstance(a, dict)])
            if artist_matches(artist, cand_artists):
                best_match = candidate
            else:
                print(f"      ⚠️ Artist mismatch on 'songs' tab (Expected: '{artist}', Got: '{cand_artists}'). Triggering fallback...")

        # Attempt 2: Fallback to general search (videos/clips) if no match or artist mismatched
        if not best_match:
            if not song_results:
                print("      ⚠️ No 'songs' tab results found. Falling back to general video search...")
            
            video_results = yt.search(raw_query, limit=10)
            if not video_results:
                return None

            is_fallback = True
            highest_score = 0

            for item in video_results:
                if item.get("resultType") not in ["song", "video"]:
                    continue

                res_title = item.get("title", "")
                res_artists = " ".join([a.get("name", "") for a in item.get("artists", []) if isinstance(a, dict)])
                res_album = item.get("album", {}).get("name", "") if item.get("album") else ""

                score = score_match(artist, album, title, res_artists, res_album, res_title)
                if score > highest_score:
                    highest_score = score
                    best_match = item

            if not best_match:
                best_match = video_results[0]

        year = ""
        album_id = best_match.get("album", {}).get("id") if best_match.get("album") else None
        if album_id:
            try:
                album_details = yt.get_album(album_id)
                year = str(album_details.get("year", ""))
            except Exception:
                pass

        cover_url = None
        thumbnails = best_match.get("thumbnails", [])
        if thumbnails:
            raw_url = thumbnails[-1].get("url", "")
            cover_url = re.sub(r"=w\d+-h\d+.*$", "=s0", raw_url)
            if "=s0" not in cover_url:
                cover_url = re.sub(r"=s\d+.*$", "=s0", cover_url)

        res_artist_str = ", ".join([a.get("name", "") for a in best_match.get("artists", []) if isinstance(a, dict)])

        return {
            "source": "YouTube Music" if not is_fallback else "YouTube Music (Fallback Video)",
            "artist": res_artist_str or artist,
            "album": best_match.get("album", {}).get("name") if best_match.get("album") else album,
            "year": year,
            "title": best_match.get("title") or title,
            "cover_url": cover_url,
            "is_fallback": is_fallback
        }
    except Exception as e:
        print(f"      ⚠️ Search error: {e}")
        return None

# ============================================================
# COVER ART FETCHING (RAW BYTES)
# ============================================================

def fetch_cover_art(url):
    if not url:
        return None
    try:
        resp = session.get(url, timeout=20)
        if resp.status_code == 200:
            return resp.content
        return None
    except Exception as e:
        print(f"      ⚠️ Cover download error: {e}")
        return None

# ============================================================
# MAIN OVERHAUL PIPELINE
# ============================================================

def main():
    print("\n" + "=" * 60)
    print("FLAC METADATA OVERHAUL (SONGS FIRST -> ARTIST-CHECK FALLBACK)")
    print("=" * 60 + "\n")

    user_path = input("ENTER THE PATH: ").strip().strip('"')
    music_folder = Path(user_path)

    if not music_folder.exists():
        print(f"❌ Folder '{music_folder}' does not exist.")
        return

    files = list(music_folder.rglob("*.flac"))
    print(f"Found {len(files)} FLAC file(s)\n")
    if not files:
        return

    yt = YTMusic()

    for idx, file in enumerate(files, 1):
        print("-" * 60)
        print(f"[{idx}/{len(files)}] Reading: {file.name}")

        try:
            flac = FLAC(file)
            search_artist = flac.get("artist", [""])[0]
            search_album = flac.get("album", [""])[0]
            search_title = flac.get("title", [""])[0] or derive_title_from_filename(file)

            existing_cover_bytes = None
            if flac.pictures:
                existing_cover_bytes = flac.pictures[0].data

            print(f"    Current Artist: {search_artist or '[None]'}")
            print(f"    Current Album : {search_album or '[None]'}")
            print(f"    Current Title : {search_title}")

            data = resolve_metadata_ytmusic(yt, search_artist, search_album, search_title)

            if not data:
                print("    ❌ Match not found on YouTube Music. Keeping existing metadata...")
                continue

            match_type = "Fallback Video" if data.get("is_fallback") else "Official Song"
            print(f"    ✅ Matched Track ({match_type}): {data['artist']} - {data['title']}")

            print("    🧹 Stripping old tags & artwork...")
            flac.delete()
            flac.clear_pictures()
            flac.save()

            flac = FLAC(file)

            for tag in ["ALBUMARTIST", "ALBUM ARTIST", "albumartist", "album artist"]:
                if tag in flac:
                    del flac[tag]

            final_artist = data.get("artist") or search_artist
            if final_artist:
                flac["ARTIST"] = final_artist
                print(f"    [1/5] WRITTEN ARTIST : {final_artist}")

            final_album = data.get("album") or search_album
            if final_album:
                flac["ALBUM"] = final_album
                print(f"    [2/5] WRITTEN ALBUM  : {final_album}")

            final_year = data.get("year")
            if final_year:
                flac["DATE"] = final_year
                print(f"    [3/5] WRITTEN YEAR   : {final_year}")

            final_title = data.get("title") or search_title
            if final_title:
                flac["TITLE"] = final_title
                print(f"    [4/5] WRITTEN TITLE  : {final_title}")

            flac.save()

            print("    [5/5] FETCHING COVER ART...")
            cover_bytes = fetch_cover_art(data.get("cover_url"))

            if not cover_bytes and existing_cover_bytes:
                print("          ⚠️ Download failed. Re-attaching original embedded cover...")
                cover_bytes = existing_cover_bytes

            if cover_bytes:
                picture = Picture()
                picture.type = 3
                picture.mime = "image/jpeg"
                picture.desc = "Front Cover"
                picture.data = cover_bytes

                flac.add_picture(picture)
                flac.save()
                print("          ✅ Attached cover art")
            else:
                print("          ⚠️ No cover attached")

            time.sleep(REQUEST_DELAY)

        except Exception as e:
            print(f"    ❌ Error processing {file.name}: {e}")

    print("\n" + "=" * 60)
    print("METADATA OVERHAUL COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except Exception as fatal:
        print(f"\nFatal Error: {fatal}")
    finally:
        input("\nPress ENTER to exit...")