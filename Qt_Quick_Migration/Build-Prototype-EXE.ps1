$ErrorActionPreference = "Stop"
$WorkRoot = $PSScriptRoot
$Python = Join-Path $WorkRoot ".venv\Scripts\python.exe"
$RepoRoot = Split-Path -Parent $WorkRoot
$AssetCandidates = @(
    (Join-Path $RepoRoot "EXE_Build_Kit\build_workspace\assets"),
    (Join-Path $RepoRoot "EXE_Build_Kit\assets")
)
$Assets = $AssetCandidates | Where-Object { Test-Path (Join-Path $_ "yt-dlp.exe") -and (Test-Path (Join-Path $_ "ffmpeg.exe")) } | Select-Object -First 1
$QmlRoot = Join-Path $WorkRoot "qml"
$DistDir = Join-Path $WorkRoot "dist"
$BuildDir = Join-Path $WorkRoot "pyinstaller_work"

if (-not (Test-Path $Python)) {
    Write-Host "Creating an isolated build environment..."
    py -m venv (Join-Path $WorkRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python virtual environment." }
}
if (-not (Test-Path $Assets)) {
    throw "Could not find yt-dlp.exe and ffmpeg.exe in EXE_Build_Kit assets. Run EXE_Build_Kit\Download-Requirements.bat first, then retry."
}
if (-not (Test-Path $QmlRoot)) { throw "QML interface folder was not found: $QmlRoot" }

Write-Host "Installing Qt Quick EXE build requirements..."
& $Python -m pip install --disable-pip-version-check -r (Join-Path $WorkRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { throw "Dependency preparation failed." }

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }

$Arguments = @(
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--name", "YouTube Toolkit Qt Preview",
    "--distpath", $DistDir,
    "--workpath", $BuildDir,
    "--specpath", $WorkRoot,
    "--collect-all", "PySide6",
    "--collect-all", "mutagen",
    "--collect-all", "ytmusicapi",
    "--collect-all", "PIL",
    "--collect-all", "requests",
    "--collect-all", "psutil",
    "--add-data", "$QmlRoot;qml",
    "--add-binary", "$(Join-Path $Assets 'yt-dlp.exe');.",
    "--add-binary", "$(Join-Path $Assets 'ffmpeg.exe');.",
    (Join-Path $WorkRoot "main.py")
)
foreach ($OptionalTool in @("ffprobe.exe", "deno.exe", "aria2c.exe")) {
    $OptionalPath = Join-Path $Assets $OptionalTool
    if (Test-Path $OptionalPath) {
        $Arguments += @("--add-binary", "$OptionalPath;.")
    }
}
$Icon = Join-Path $Assets "app.ico"
if (Test-Path $Icon) { $Arguments += @("--icon", $Icon) }

Write-Host "Building one-file Qt Quick executable..."
Push-Location $WorkRoot
try {
    & $Python -m PyInstaller @Arguments
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed. Do not use a stale EXE as the new build." }
}
finally {
    Pop-Location
}

$Output = Join-Path $DistDir "YouTube Toolkit Qt Preview.exe"
if (-not (Test-Path $Output)) { throw "Build reported success but the expected EXE is missing: $Output" }
$Hash = (Get-FileHash -Algorithm SHA256 $Output).Hash
$SizeMiB = [Math]::Round((Get-Item $Output).Length / 1MB, 1)
Write-Host ""
Write-Host "Build finished."
Write-Host "EXE: $Output"
Write-Host "Size: $SizeMiB MiB"
Write-Host "SHA-256: $Hash"
