$ErrorActionPreference = "Stop"

$RepoRaw = "https://raw.githubusercontent.com/ykbokka/ytdlp/main/YTM_Music_Toolkit.pyw"
$WorkRoot = Join-Path $PSScriptRoot "build_workspace"
$AssetsRoot = Join-Path $WorkRoot "assets"
$DistRoot = Join-Path $PSScriptRoot "dist"
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
    throw "Python 3.10–3.14 is required to build. Install Python, then rerun this script."
}

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments, [string]$Failure)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw $Failure }
}

try {
    Write-Host ""
    Write-Host "YTM Music Toolkit — One-File EXE Builder" -ForegroundColor Cyan
    Write-Host "This builds a Windows EXE. It does not install the app on this PC."
    Write-Host "Build output: $DistRoot"
    Write-Host ""

    $python = Get-PythonCommand
    New-Item -ItemType Directory -Force -Path $WorkRoot, $AssetsRoot, $DistRoot | Out-Null

    Write-Host "[1/6] Downloading released application source..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $RepoRaw -OutFile $SourcePath -UseBasicParsing
    if ((Get-Item $SourcePath).Length -lt 10000) { throw "Downloaded app source is unexpectedly small; refusing to build." }

    Write-Host "[2/6] Downloading yt-dlp standalone executable..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" -OutFile (Join-Path $AssetsRoot "yt-dlp.exe") -UseBasicParsing

    Write-Host "[3/6] Downloading Deno runtime..." -ForegroundColor Cyan
    $denoZip = Join-Path $WorkRoot "deno.zip"
    Invoke-WebRequest -Uri "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip" -OutFile $denoZip -UseBasicParsing
    $denoExtract = Join-Path $WorkRoot "deno_extract"
    if (Test-Path $denoExtract) { Remove-Item $denoExtract -Recurse -Force }
    Expand-Archive -Path $denoZip -DestinationPath $denoExtract -Force
    $denoExe = Get-ChildItem -Path $denoExtract -Filter "deno.exe" -Recurse | Select-Object -First 1
    if (-not $denoExe) { throw "Deno download did not contain deno.exe." }
    Copy-Item $denoExe.FullName (Join-Path $AssetsRoot "deno.exe") -Force

    Write-Host "[4/6] Downloading FFmpeg..." -ForegroundColor Cyan
    $ffmpegZip = Join-Path $WorkRoot "ffmpeg.zip"
    Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $ffmpegZip -UseBasicParsing
    $ffmpegExtract = Join-Path $WorkRoot "ffmpeg_extract"
    if (Test-Path $ffmpegExtract) { Remove-Item $ffmpegExtract -Recurse -Force }
    Expand-Archive -Path $ffmpegZip -DestinationPath $ffmpegExtract -Force
    foreach ($tool in @("ffmpeg.exe", "ffprobe.exe")) {
        $found = Get-ChildItem -Path $ffmpegExtract -Filter $tool -Recurse | Select-Object -First 1
        if (-not $found) { throw "FFmpeg archive did not contain $tool." }
        Copy-Item $found.FullName (Join-Path $AssetsRoot $tool) -Force
    }

    Write-Host "[5/6] Creating build environment and installing dependencies..." -ForegroundColor Cyan
    $pythonExe = $python.Command
    $pythonArgs = @()
    if ($python.Prefix.Count -gt 0) { $pythonArgs += $python.Prefix }
    $pythonArgs += @("-m", "venv", $VenvRoot)
    Invoke-Checked $pythonExe $pythonArgs "Could not create the build virtual environment."

    $venvPython = Join-Path $VenvRoot "Scripts\python.exe"
    Invoke-Checked $venvPython @("-m", "pip", "install", "--upgrade", "pip") "Could not upgrade pip."
    Invoke-Checked $venvPython @("-m", "pip", "install", "-r", $Requirements) "Could not install build dependencies."

    Write-Host "[6/6] Building the single-file GUI executable..." -ForegroundColor Cyan
    $specPath = Join-Path $PSScriptRoot "YTM_Music_Toolkit.spec"
    Invoke-Checked $venvPython @("-m", "PyInstaller", $specPath, "--noconfirm", "--clean", "--distpath", $DistRoot, "--workpath", (Join-Path $WorkRoot "pyinstaller_work")) "PyInstaller failed. Review the build output above."

    $exePath = Join-Path $DistRoot "YTM Music Toolkit.exe"
    if (-not (Test-Path $exePath)) { throw "Build command completed but the expected EXE was not found." }
    Write-Host ""
    Write-Host "BUILD COMPLETED." -ForegroundColor Green
    Write-Host "EXE: $exePath"
    Write-Host "This one-file build bundles Python, app dependencies, yt-dlp, Deno, FFmpeg and FFprobe."
    Write-Host "The EXE still needs internet for YouTube Music and other online services. Account-specific features may require the user to authenticate again."
    Write-Host "Build size may be large. Test the EXE on your PC before sharing it."
}
catch {
    Write-Host ""
    Write-Host "BUILD FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
