$ErrorActionPreference = "Stop"

$RepoRaw = "https://raw.githubusercontent.com/ykbokka/ytdlp/main/YTM_Music_Toolkit.pyw"
$WorkRoot = Join-Path $PSScriptRoot "build_workspace"
$AssetsRoot = Join-Path $WorkRoot "assets"
$SourcePath = Join-Path $WorkRoot "YTM_Music_Toolkit.pyw"
$Requirements = Join-Path $PSScriptRoot "requirements-build.txt"
$VenvRoot = Join-Path $WorkRoot "venv"

function Get-PythonCommand {
    foreach ($name in @("python", "py")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        if ($name -eq "python") {
            & python -c "import sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] < (3,15) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return @{ Command = "python"; Prefix = @() } }
        } else {
            foreach ($version in @("3.14", "3.13", "3.12", "3.11", "3.10")) {
                & cmd.exe /d /c "py -$version -V >nul 2>nul"
                if ($LASTEXITCODE -eq 0) { return @{ Command = "py"; Prefix = @("-$version") } }
            }
        }
    }
    throw "Python 3.10-3.14 is required on the BUILD PC only. Install Python, then rerun this downloader."
}

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments, [string]$Failure)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw $Failure }
}

function Download-File {
    param([string]$Url, [string]$Destination)
    Write-Host "Downloading $([System.IO.Path]::GetFileName($Destination)) ..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
    if (-not (Test-Path $Destination) -or (Get-Item $Destination).Length -lt 1024) {
        throw "Download appears incomplete: $Destination"
    }
}

try {
    Write-Host ""
    Write-Host "YTM Music Toolkit - DOWNLOAD ALL BUILD REQUIREMENTS" -ForegroundColor Cyan
    Write-Host "This prepares the build folder. It does NOT create the final EXE."
    Write-Host "Build workspace: $WorkRoot"
    Write-Host ""

    $python = Get-PythonCommand
    New-Item -ItemType Directory -Force -Path $WorkRoot, $AssetsRoot | Out-Null

    Write-Host "[1/6] Downloading the app source..." -ForegroundColor Cyan
    Download-File $RepoRaw $SourcePath
    if ((Get-Item $SourcePath).Length -lt 10000) {
        throw "Downloaded app source is unexpectedly small; refusing to continue."
    }

    Write-Host "[2/6] Downloading yt-dlp..." -ForegroundColor Cyan
    Download-File "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" (Join-Path $AssetsRoot "yt-dlp.exe")

    Write-Host "[3/6] Downloading and extracting Deno..." -ForegroundColor Cyan
    $denoZip = Join-Path $WorkRoot "deno.zip"
    Download-File "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip" $denoZip
    $denoExtract = Join-Path $WorkRoot "deno_extract"
    if (Test-Path $denoExtract) { Remove-Item $denoExtract -Recurse -Force }
    Expand-Archive -Path $denoZip -DestinationPath $denoExtract -Force
    $denoExe = Get-ChildItem -Path $denoExtract -Filter "deno.exe" -Recurse | Select-Object -First 1
    if (-not $denoExe) { throw "Deno archive did not contain deno.exe." }
    Copy-Item $denoExe.FullName (Join-Path $AssetsRoot "deno.exe") -Force

    Write-Host "[4/6] Downloading and extracting FFmpeg/FFprobe..." -ForegroundColor Cyan
    $ffmpegZip = Join-Path $WorkRoot "ffmpeg.zip"
    Download-File "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" $ffmpegZip
    $ffmpegExtract = Join-Path $WorkRoot "ffmpeg_extract"
    if (Test-Path $ffmpegExtract) { Remove-Item $ffmpegExtract -Recurse -Force }
    Expand-Archive -Path $ffmpegZip -DestinationPath $ffmpegExtract -Force
    foreach ($tool in @("ffmpeg.exe", "ffprobe.exe")) {
        $found = Get-ChildItem -Path $ffmpegExtract -Filter $tool -Recurse | Select-Object -First 1
        if (-not $found) { throw "FFmpeg archive did not contain $tool." }
        Copy-Item $found.FullName (Join-Path $AssetsRoot $tool) -Force
    }

    Write-Host "[5/6] Creating the isolated Python build environment..." -ForegroundColor Cyan
    if (Test-Path $VenvRoot) { Remove-Item $VenvRoot -Recurse -Force }
    $pythonExe = $python.Command
    $pythonArgs = @()
    if ($python.Prefix.Count -gt 0) { $pythonArgs += $python.Prefix }
    $pythonArgs += @("-m", "venv", $VenvRoot)
    Invoke-Checked $pythonExe $pythonArgs "Could not create the build virtual environment."

    $venvPython = Join-Path $VenvRoot "Scripts\python.exe"
    Invoke-Checked $venvPython @("-m", "pip", "install", "--upgrade", "pip") "Could not upgrade pip."
    Invoke-Checked $venvPython @("-m", "pip", "install", "-r", $Requirements) "Could not install Python build dependencies."

    Write-Host "[6/6] Verifying all files required by the build..." -ForegroundColor Cyan
    $requiredFiles = @(
        $SourcePath,
        (Join-Path $AssetsRoot "yt-dlp.exe"),
        (Join-Path $AssetsRoot "deno.exe"),
        (Join-Path $AssetsRoot "ffmpeg.exe"),
        (Join-Path $AssetsRoot "ffprobe.exe"),
        $venvPython,
        (Join-Path $PSScriptRoot "YTM_Music_Toolkit.spec")
    )
    foreach ($file in $requiredFiles) {
        if (-not (Test-Path $file)) { throw "Required build file is missing: $file" }
    }
    Invoke-Checked $venvPython @("-m", "PyInstaller", "--version") "PyInstaller is not installed correctly."

    Write-Host ""
    Write-Host "ALL BUILD REQUIREMENTS ARE READY." -ForegroundColor Green
    Write-Host "You can now run Build.bat. It will only assemble the EXE and will not download or install anything."
    Write-Host "Keep build_workspace intact between preparation and building."
}
catch {
    Write-Host ""
    Write-Host "PREPARATION FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
