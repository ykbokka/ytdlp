# -*- mode: python ; coding: utf-8 -*-
"""
High-coverage PyInstaller spec for the standalone YTM Music Toolkit.

This intentionally collects third-party package modules, data, metadata,
native extensions, hidden imports, locale resources, TLS CA certificates, and
the external media/runtime executables used by the application.
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
        + "\nRun EXE_Build_Kit\\Download-Requirements.bat first."
    )

required_binaries = ["yt-dlp.exe", "deno.exe", "ffmpeg.exe", "ffprobe.exe"]
app_binaries = []

for filename in required_binaries:
    source_path = os.path.join(ASSETS, filename)
    if not os.path.isfile(source_path):
        raise FileNotFoundError(
            "Required bundled executable not found: " + source_path
            + "\nRun EXE_Build_Kit\\Download-Requirements.bat first."
        )
    if os.path.getsize(source_path) < 1024 * 1024:
        raise FileNotFoundError(
            "Required executable is suspiciously small and may be an incomplete download: "
            + source_path
        )
    app_binaries.append((source_path, "."))

# Collect all modules, package data, metadata, native extensions, and hidden
# imports from every third-party package used directly or dynamically.
# PyInstaller's standard hooks collect Python, tkinter/Tcl-Tk, and the standard
# library runtime. The application itself puts this folder first on PATH.
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
    "psutil",
    "darkdetect",
    "packaging",
]

app_datas = []
app_binaries_from_packages = []
app_hiddenimports = ["typing_extensions"]

for package_name in packages_to_collect:
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    app_datas += package_datas
    app_binaries_from_packages += package_binaries
    app_hiddenimports += package_hiddenimports

# Explicitly include the certifi root CA bundle. Some frozen applications
# otherwise resolve the certificate path differently after extraction.
import certifi

CERTIFI_CA = certifi.where()
if not os.path.isfile(CERTIFI_CA):
    raise FileNotFoundError("certifi CA bundle was not found: " + CERTIFI_CA)
app_datas.append((CERTIFI_CA, "certifi"))

# ytmusicapi uses gettext.translation("base", ...) at runtime. Preserve every
# locale file at the package-relative path expected by ytmusicapi.
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
    raise FileNotFoundError("No ytmusicapi locale files were found in: " + LOCALES_DIR)

# Dedupe repeated entries (e.g. package auto-collection plus explicit CA or
# locale files) to avoid duplicate destination warnings and ambiguous bundles.
def dedupe_entries(entries):
    result = []
    seen = set()
    for source_path, destination in entries:
        key = (
            os.path.normcase(os.path.abspath(source_path)),
            os.path.normcase(os.path.normpath(destination)),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append((source_path, destination))
    return result

app_datas = dedupe_entries(app_datas)
app_binaries_from_packages = dedupe_entries(app_binaries_from_packages)
app_binaries = dedupe_entries(app_binaries)

if not app_datas:
    raise RuntimeError("No package data was collected; refusing to build an incomplete EXE.")
if not app_hiddenimports:
    raise RuntimeError("No hidden imports were collected; refusing to build an incomplete EXE.")

a = Analysis(
    [SOURCE],
    pathex=[WORKSPACE],
    binaries=app_binaries + app_binaries_from_packages,
    datas=app_datas,
    hiddenimports=sorted(set(app_hiddenimports)),
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
