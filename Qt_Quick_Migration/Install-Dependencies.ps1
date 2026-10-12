$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Assets = Join-Path $Root "build_assets"
$Cache = Join-Path $Root "build_downloads"
$Licenses = Join-Path $Assets "licenses"
$Requirements = Join-Path $Root "requirements-build.txt"

function Invoke-Native {
    param([string]$Program, [string[]]$Arguments, [string]$Failure)
    & $Program @Arguments
    $Code = $LASTEXITCODE
    if ($Code -ne 0) { throw "$Failure (exit code $Code)." }
}

function Download-File {
    param([string]$Url, [string]$Destination)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    if ((Test-Path -LiteralPath $Destination) -and (Get-Item -LiteralPath $Destination).Length -ge 64) {
        Write-Host "Using cached file: $([IO.Path]::GetFileName($Destination))"
        return
    }

    $Partial = "$Destination.partial"
    $LastError = ""
    $Curl = Get-Command "curl.exe" -ErrorAction SilentlyContinue
    for ($Attempt = 1; $Attempt -le 3; $Attempt++) {
        $OldProgress = $ProgressPreference
        $OldErrorPreference = $ErrorActionPreference
        try {
            Remove-Item -LiteralPath $Partial -Force -ErrorAction SilentlyContinue
            Write-Host "Downloading $([IO.Path]::GetFileName($Destination)) (attempt $Attempt/3)..."

            if ($Curl) {
                # Windows 10/11 includes curl.exe. Its progress meter makes large downloads
                # visibly active instead of leaving the console on a silent line.
                $ErrorActionPreference = "Continue"
                & $Curl.Source --fail --location --show-error --progress-bar --connect-timeout 30 --max-time 900 --output $Partial $Url
                $DownloadCode = $LASTEXITCODE
                if ($DownloadCode -ne 0) {
                    throw "curl.exe failed with exit code $DownloadCode."
                }
            }
            else {
                # Fallback for uncommon Windows installations without curl.exe.
                $ProgressPreference = "Continue"
                Invoke-WebRequest -Uri $Url -OutFile $Partial -UseBasicParsing -TimeoutSec 900
            }

            if (-not (Test-Path -LiteralPath $Partial) -or (Get-Item -LiteralPath $Partial).Length -lt 64) {
                throw "Downloaded file is empty or incomplete."
            }
            Move-Item -LiteralPath $Partial -Destination $Destination -Force
            return
        }
        catch {
            $LastError = $_.Exception.Message
            Remove-Item -LiteralPath $Partial -Force -ErrorAction SilentlyContinue
            if ($Attempt -lt 3) {
                Write-Host "Download attempt failed: $LastError" -ForegroundColor Yellow
                Start-Sleep -Seconds (2 * $Attempt)
            }
        }
        finally {
            $ProgressPreference = $OldProgress
            $ErrorActionPreference = $OldErrorPreference
        }
    }
    throw "Could not download $Url. Last error: $LastError"
}

function Test-Tool {
    param([string]$Path, [string[]]$Arguments)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $OldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $Output = @(& $Path @Arguments 2>&1)
        $Code = $LASTEXITCODE
        return ($Code -eq 0 -and $Output.Count -gt 0)
    }
    catch { return $false }
    finally { $ErrorActionPreference = $OldPreference }
}

function Copy-Dlls {
    param([string]$Directory)
    Get-ChildItem -LiteralPath $Directory -Filter "*.dll" -File -ErrorAction SilentlyContinue |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Assets $_.Name) -Force }
}

try {
    Write-Host ""
    Write-Host "YouTube Toolkit - Qt Quick dependency installer" -ForegroundColor Cyan
    if (-not [Environment]::Is64BitOperatingSystem) { throw "This EXE builder requires 64-bit Windows." }
    if (-not (Test-Path -LiteralPath $Requirements -PathType Leaf)) { throw "Missing file: $Requirements" }

    New-Item -ItemType Directory -Force -Path $Assets, $Cache, $Licenses | Out-Null

    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        $Py = Get-Command "py.exe" -ErrorAction SilentlyContinue
        if ($Py) {
            Invoke-Native $Py.Source @("-3", "-m", "venv", $Venv) "Could not create the Python virtual environment"
        }
        else {
            $Py = Get-Command "python.exe" -ErrorAction SilentlyContinue
            if (-not $Py) { throw "Install 64-bit Python 3.11 or newer, then run this installer again." }
            Invoke-Native $Py.Source @("-m", "venv", $Venv) "Could not create the Python virtual environment"
        }
    }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "The virtual environment Python was not created." }

    $VersionText = (& $Python -c "import sys; print('.'.join(map(str,sys.version_info[:3])))").Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not detect the build Python version." }
    if ([version]$VersionText -lt [version]"3.11") {
        throw "Python 3.11 or newer is required; current version is $VersionText. Remove Qt_Quick_Migration\.venv after installing a newer Python, then retry."
    }

    $YtDlp = Join-Path $Assets "yt-dlp.exe"
    if (-not (Test-Tool $YtDlp @("--version"))) {
        Remove-Item -LiteralPath $YtDlp -Force -ErrorAction SilentlyContinue
        Download-File "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" $YtDlp
        if (-not (Test-Tool $YtDlp @("--version"))) { throw "yt-dlp.exe failed its version check." }
    } else { Write-Host "yt-dlp is ready." }

    $Deno = Join-Path $Assets "deno.exe"
    if (-not (Test-Tool $Deno @("--version"))) {
        Remove-Item -LiteralPath $Deno -Force -ErrorAction SilentlyContinue
        $Zip = Join-Path $Cache "deno.zip"
        Download-File "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip" $Zip
        $Extract = Join-Path $Cache "deno_extract"
        Remove-Item -LiteralPath $Extract -Recurse -Force -ErrorAction SilentlyContinue
        Expand-Archive -LiteralPath $Zip -DestinationPath $Extract -Force
        $Found = Get-ChildItem -LiteralPath $Extract -Filter "deno.exe" -File -Recurse | Select-Object -First 1
        if (-not $Found) { throw "Deno archive did not contain deno.exe." }
        Copy-Item -LiteralPath $Found.FullName -Destination $Deno -Force
        if (-not (Test-Tool $Deno @("--version"))) { throw "Bundled Deno failed its version check." }
    } else { Write-Host "Deno is ready." }

    $Ffmpeg = Join-Path $Assets "ffmpeg.exe"
    $Ffprobe = Join-Path $Assets "ffprobe.exe"
    if (-not (Test-Tool $Ffmpeg @("-version")) -or -not (Test-Tool $Ffprobe @("-version"))) {
        Remove-Item -LiteralPath $Ffmpeg,$Ffprobe -Force -ErrorAction SilentlyContinue
        $Zip = Join-Path $Cache "ffmpeg-release-essentials.zip"
        Download-File "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" $Zip
        $Extract = Join-Path $Cache "ffmpeg_extract"
        Remove-Item -LiteralPath $Extract -Recurse -Force -ErrorAction SilentlyContinue
        Expand-Archive -LiteralPath $Zip -DestinationPath $Extract -Force
        $FoundFfmpeg = Get-ChildItem -LiteralPath $Extract -Filter "ffmpeg.exe" -File -Recurse | Select-Object -First 1
        $FoundProbe = Get-ChildItem -LiteralPath $Extract -Filter "ffprobe.exe" -File -Recurse | Select-Object -First 1
        if (-not $FoundFfmpeg -or -not $FoundProbe) { throw "FFmpeg archive must contain ffmpeg.exe and ffprobe.exe." }
        Copy-Item -LiteralPath $FoundFfmpeg.FullName -Destination $Ffmpeg -Force
        Copy-Item -LiteralPath $FoundProbe.FullName -Destination $Ffprobe -Force
        Copy-Dlls (Split-Path -Parent $FoundFfmpeg.FullName)
        Get-ChildItem -LiteralPath $Extract -File -Recurse |
            Where-Object { $_.Name -match "^(LICENSE|COPYING)(\..*)?$" -or $_.Name -match "^README(\..*)?$" } |
            Select-Object -First 12 | ForEach-Object {
                Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Licenses ("FFmpeg-" + $_.Name)) -Force
            }
        if (-not (Test-Tool $Ffmpeg @("-version")) -or -not (Test-Tool $Ffprobe @("-version"))) {
            throw "Bundled FFmpeg/FFprobe failed their version checks."
        }
    } else { Write-Host "FFmpeg and FFprobe are ready." }

    $Aria = Join-Path $Assets "aria2c.exe"
    if (-not (Test-Tool $Aria @("--version"))) {
        Remove-Item -LiteralPath $Aria -Force -ErrorAction SilentlyContinue
        $Zip = Join-Path $Cache "aria2.zip"
        Download-File "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip" $Zip
        $ExpectedHash = "67D015301EEF0B612191212D564C5BB0A14B5B9C4796B76454276A4D28D9B288"
        $ActualHash = (Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($ActualHash -ne $ExpectedHash) {
            Remove-Item -LiteralPath $Zip -Force -ErrorAction SilentlyContinue
            throw "aria2 archive SHA-256 check failed; the download was rejected. Rerun the installer to download it again."
        }
        $Extract = Join-Path $Cache "aria2_extract"
        Remove-Item -LiteralPath $Extract -Recurse -Force -ErrorAction SilentlyContinue
        Expand-Archive -LiteralPath $Zip -DestinationPath $Extract -Force
        $Found = Get-ChildItem -LiteralPath $Extract -Filter "aria2c.exe" -File -Recurse | Select-Object -First 1
        if (-not $Found) { throw "aria2 archive did not contain aria2c.exe." }
        Copy-Item -LiteralPath $Found.FullName -Destination $Aria -Force
        Copy-Dlls (Split-Path -Parent $Found.FullName)
        if (-not (Test-Tool $Aria @("--version"))) { throw "Bundled aria2c failed its version check." }
    } else { Write-Host "aria2c is ready." }

    # Bundle third-party notices with the app where upstream license texts are available.
    $NoticeSources = @(
        @{ Url = "https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/LICENSE"; Path = (Join-Path $Licenses "yt-dlp-LICENSE") },
        @{ Url = "https://raw.githubusercontent.com/denoland/deno/main/LICENSE.md"; Path = (Join-Path $Licenses "Deno-LICENSE") },
        @{ Url = "https://raw.githubusercontent.com/aria2/aria2/release-1.37.0/COPYING"; Path = (Join-Path $Licenses "aria2-COPYING") }
    )
    foreach ($Notice in $NoticeSources) {
        if (-not (Test-Path -LiteralPath $Notice.Path)) {
            try { Download-File $Notice.Url $Notice.Path }
            catch { Write-Host "Notice download skipped for $([IO.Path]::GetFileName($Notice.Path)): $($_.Exception.Message)" -ForegroundColor Yellow }
        }
    }

    Write-Host ""
    Write-Host "Installing Python packages and PyInstaller..." -ForegroundColor Cyan
    Invoke-Native $Python @("-m", "pip", "install", "--disable-pip-version-check", "--progress-bar", "off", "--prefer-binary", "-r", $Requirements) "Python dependency installation failed"
    Invoke-Native $Python @("-m", "pip", "check") "Python package checks found dependency conflicts"
    $ImportCheck = "import PySide6, requests, PIL, mutagen, yt_dlp, ytmusicapi, psutil, PyInstaller, certifi; from PySide6.QtQml import QQmlApplicationEngine; import ytmusic_resolver; print('Python imports passed.')"
    Push-Location $Root
    try { Invoke-Native $Python @("-c", $ImportCheck) "Required Python packages failed their import check" }
    finally { Pop-Location }

    Write-Host ""
    Write-Host "DEPENDENCIES READY." -ForegroundColor Green
    Write-Host "Tools: $Assets"
    Write-Host "Run Build-Prototype-EXE.bat next; it also calls this installer safely."
}
catch {
    Write-Host ""
    Write-Host "DEPENDENCY INSTALLATION FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
