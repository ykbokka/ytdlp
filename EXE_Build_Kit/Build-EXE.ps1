$ErrorActionPreference = "Stop"

$WorkRoot = Join-Path $PSScriptRoot "build_workspace"
$AssetsRoot = Join-Path $WorkRoot "assets"
$VenvPython = Join-Path $WorkRoot "venv\Scripts\python.exe"
$SourcePath = Join-Path $WorkRoot "YTM_Music_Toolkit.pyw"
$SpecPath = Join-Path $PSScriptRoot "YTM_Music_Toolkit.spec"
$DistRoot = Join-Path $PSScriptRoot "dist"
$PyInstallerWork = Join-Path $WorkRoot "pyinstaller_work"

try {
    Write-Host ""
    Write-Host "YTM Music Toolkit - ASSEMBLE EXE ONLY" -ForegroundColor Cyan
    Write-Host "This step does not download files or install dependencies."
    Write-Host ""

    $requiredFiles = @(
        $SourcePath,
        $SpecPath,
        $VenvPython,
        (Join-Path $AssetsRoot "yt-dlp.exe"),
        (Join-Path $AssetsRoot "deno.exe"),
        (Join-Path $AssetsRoot "ffmpeg.exe"),
        (Join-Path $AssetsRoot "ffprobe.exe")
    )

    foreach ($file in $requiredFiles) {
        if (-not (Test-Path $file)) {
            throw ("A build requirement is missing: " + $file + ". Run Download-Requirements.bat first.")
        }
    }

    New-Item -ItemType Directory -Force -Path $DistRoot, $PyInstallerWork | Out-Null

    Write-Host "Assembling the single-file GUI EXE..." -ForegroundColor Cyan
    & $VenvPython -m PyInstaller $SpecPath --noconfirm --distpath $DistRoot --workpath $PyInstallerWork
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed. Review the build output above." }

    $exePath = Join-Path $DistRoot "YTM Music Toolkit.exe"
    if (-not (Test-Path $exePath)) { throw "Build completed but the expected EXE was not found." }

    Write-Host ""
    Write-Host "BUILD COMPLETED." -ForegroundColor Green
    Write-Host "EXE: $exePath"
    Write-Host "This step used only the prepared build files; no downloads or package installs were run."
}
catch {
    Write-Host ""
    Write-Host "BUILD FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
