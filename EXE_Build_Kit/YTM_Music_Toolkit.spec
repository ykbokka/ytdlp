# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the standalone YTM Music Toolkit EXE.

The EXE bundles the Python runtime, third-party Python packages, package data,
and the yt-dlp, Deno, FFmpeg, and FFprobe executables. User-specific settings,
authentication files, downloads, and logs remain outside the EXE intentionally.
"""

import os

from PyInstaller.utils.hooks import collect_all

SPEC_DIR = os.path.abspath(SPECPATH)
WORKSPACE = os.path.join(SPEC_DIR, "build_workspace")
SOURCE = os.path.join(WORKSPACE, "YTM_Music_Toolkit.pyw")
ASSETS = os.path.join(WORKSPACE, "assets")
ICON = os.path.join(ASSETS, "app.ico")

if not os.path.isfile(SOURCE):
    raise FileNotFoundError(
        "Application source not found: " + SOURCE
        + "\nRun EXE_Build_Kit\\Build.bat to download the source first."
    )

required_binaries = ["yt-dlp.exe", "deno.exe", "ffmpeg.exe", "ffprobe.exe"]
app_binaries = []

for filename in required_binaries:
    source_path = os.path.join(ASSETS, filename)
    if not os.path.isfile(source_path):
        raise FileNotFoundError(
            "Required bundled executable not found: " + source_path
            + "\nRun EXE_Build_Kit\\Build.bat to download build assets first."
        )
    app_binaries.append((source_path, "."))

# Collect code, hidden imports, native extensions, and package data for all
# third-party libraries directly used by the application and their common
# runtime dependencies. PyInstaller also bundles the Python standard library
# and interpreter runtime automatically.
packages_to_collect = [
    "customtkinter",
    "comtypes",
    "ytmusicapi",
    "requests",
    "PIL",
    "mutagen",
    "certifi",
    "charset_normalizer",
    "idna",
    "urllib3",
]

app_datas = []
app_binaries_from_packages = []
app_hiddenimports = []

for package_name in packages_to_collect:
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    app_datas += package_datas
    app_binaries_from_packages += package_binaries
    app_hiddenimports += package_hiddenimports

# Explicitly add every ytmusicapi locale file at the exact relative location
# expected by ytmusicapi's gettext.translation("base", localedir=...).
import ytmusicapi

YTMUSICAPI_DIR = os.path.dirname(ytmusicapi.__file__)
LOCALES_DIR = os.path.join(YTMUSICAPI_DIR, "locales")

if not os.path.isdir(LOCALES_DIR):
    raise FileNotFoundError(
        "ytmusicapi locale directory not found: " + LOCALES_DIR
        + "\nReinstall ytmusicapi in the build environment before building."
    )

locale_file_count = 0
for root, _, filenames in os.walk(LOCALES_DIR):
    for filename in filenames:
        source_path = os.path.join(root, filename)
        relative_dir = os.path.relpath(os.path.dirname(source_path), YTMUSICAPI_DIR)
        destination_dir = os.path.join("ytmusicapi", relative_dir)
        app_datas.append((source_path, destination_dir))
        locale_file_count += 1

if locale_file_count == 0:
    raise FileNotFoundError(
        "No ytmusicapi locale files were found in: " + LOCALES_DIR
    )

a = Analysis(
    [SOURCE],
    pathex=[WORKSPACE],
    binaries=app_binaries + app_binaries_from_packages,
    datas=app_datas,
    hiddenimports=app_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="YTM Music Toolkit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON if os.path.isfile(ICON) else None,
)
