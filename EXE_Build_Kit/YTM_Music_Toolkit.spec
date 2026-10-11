# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the standalone YTM Music Toolkit EXE.

Expected layout:
EXE_Build_Kit/
  YTM_Music_Toolkit.spec
  build_workspace/
    YTM_Music_Toolkit.pyw
    assets/
      yt-dlp.exe
      deno.exe
      ffmpeg.exe
      ffprobe.exe
      app.ico (optional)
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

ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all("customtkinter")
comtypes_datas, comtypes_binaries, comtypes_hiddenimports = collect_all("comtypes")
ytm_datas, ytm_binaries, ytm_hiddenimports = collect_all("ytmusicapi")

a = Analysis(
    [SOURCE],
    pathex=[WORKSPACE],
    binaries=app_binaries + ctk_binaries + comtypes_binaries + ytm_binaries,
    datas=ctk_datas + comtypes_datas + ytm_datas,
    hiddenimports=ctk_hiddenimports + comtypes_hiddenimports + ytm_hiddenimports,
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
