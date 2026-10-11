$ErrorActionPreference = "Stop"

$RepoRaw = "https://raw.githubusercontent.com/ykbokka/ytdlp/main/YTM_Music_Toolkit.pyw"
$WorkRoot = Join-Path $PSScriptRoot "build_workspace"
$AssetsRoot = Join-Path $WorkRoot "assets"
$SourcePath = Join-Path $WorkRoot "YTM_Music_Toolkit.pyw"
$Requirements = Join-Path $PSScriptRoot "requirements-build.txt"
$VenvRoot = Join-Path $WorkRoot "venv"
$ManifestPath = Join-Path $WorkRoot "build_manifest.txt"

function Get-PythonCommand {
    $testCode = 'import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] < (3,15) and sys.maxsize > 2**32 else 1)'

    $cmd = Get-Command "python" -ErrorAction SilentlyContinue
    if ($cmd) {
        & python -c $testCode 2>$null
        if ($LASTEXITCODE -eq 0) { return @{ Command = "python"; Prefix = @() } }
    }

    $pyCmd = Get-Command "py" -ErrorAction SilentlyContinue
    if ($pyCmd) {
        foreach ($version in @("3.14", "3.13", "3.12", "3.11")) {
            $testArgs = @("-$version", "-c", $testCode)
            & py @testArgs 2>$null
            if ($LASTEXITCODE -eq 0) { return @{ Command = "py"; Prefix = @("-$version") } }
        }
    }

    throw "A 64-bit Python 3.11-3.14 installation is required on the BUILD PC only. Install it, then rerun this downloader."
}

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments, [string]$Failure)

    # Merge native stderr into stdout before displaying it. This avoids
    # Windows PowerShell 5.1 treating harmless native warnings as terminating
    # PowerShell errors when ErrorActionPreference is Stop.
    & $Program @Arguments 2>&1 | ForEach-Object { Write-Host $_ }

    if ($LASTEXITCODE -ne 0) { throw $Failure }
}
function Download-File {
    param([string]$Url, [string]$Destination)

    $partial = $Destination + ".partial"
    $lastError = ""

    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            if (Test-Path $partial) { Remove-Item $partial -Force }
            Write-Host "Downloading $([System.IO.Path]::GetFileName($Destination)) (attempt $attempt/3)..." -ForegroundColor Cyan
            Invoke-WebRequest -Uri $Url -OutFile $partial -UseBasicParsing -TimeoutSec 300

            if (-not (Test-Path $partial) -or (Get-Item $partial).Length -lt 1024) {
                throw "Download appears incomplete."
            }

            Move-Item $partial $Destination -Force
            return
        }
        catch {
            $lastError = $_.Exception.Message
            if (Test-Path $partial) { Remove-Item $partial -Force -ErrorAction SilentlyContinue }
            if ($attempt -lt 3) {
                Write-Host "Download attempt failed: $lastError" -ForegroundColor Yellow
                Start-Sleep -Seconds (2 * $attempt)
            }
        }
    }

    throw "Could not download $Url after 3 attempts. Last error: $lastError"
}

function Get-ToolVersion {
    param([string]$Program, [string[]]$Arguments)
    $output = @(& $Program @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "A required tool failed its startup check: $Program"
    }
    foreach ($line in $output) {
        $value = ([string]$line).Trim()
        if ($value.Length -gt 0) { return $value }
    }
    return "Version command succeeded; no version text returned."
}

try {
    Write-Host ""
    Write-Host "YTM Music Toolkit - FULL REQUIREMENTS PREPARATION" -ForegroundColor Cyan
    Write-Host "This stage downloads/prepares requirements; it does not build the EXE."
    Write-Host "Build workspace: $WorkRoot"
    Write-Host ""

    if (-not [Environment]::Is64BitOperatingSystem) {
        throw "This build kit targets 64-bit Windows. Run it on a 64-bit Windows build PC."
    }
    if (-not (Test-Path $Requirements)) {
        throw "Build requirements file is missing: $Requirements"
    }
    if (-not (Test-Path (Join-Path $PSScriptRoot "YTM_Music_Toolkit.spec"))) {
        throw "PyInstaller spec is missing from the build kit."
    }

    $python = Get-PythonCommand
    New-Item -ItemType Directory -Force -Path $WorkRoot, $AssetsRoot | Out-Null

    Write-Host "[1/7] Downloading the app source..." -ForegroundColor Cyan
    Download-File $RepoRaw $SourcePath
    if ((Get-Item $SourcePath).Length -lt 10000) {
        throw "Downloaded app source is unexpectedly small; refusing to continue."
    }

    Write-Host "[2/7] Downloading yt-dlp..." -ForegroundColor Cyan
    $ytDlpPath = Join-Path $AssetsRoot "yt-dlp.exe"
    Download-File "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" $ytDlpPath

    Write-Host "[3/7] Downloading and extracting Deno..." -ForegroundColor Cyan
    $denoZip = Join-Path $WorkRoot "deno.zip"
    Download-File "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip" $denoZip
    $denoExtract = Join-Path $WorkRoot "deno_extract"
    if (Test-Path $denoExtract) { Remove-Item $denoExtract -Recurse -Force }
    Expand-Archive -Path $denoZip -DestinationPath $denoExtract -Force
    $denoExe = Get-ChildItem -Path $denoExtract -Filter "deno.exe" -Recurse | Select-Object -First 1
    if (-not $denoExe) { throw "Deno archive did not contain deno.exe." }
    Copy-Item $denoExe.FullName (Join-Path $AssetsRoot "deno.exe") -Force

    Write-Host "[4/7] Downloading and extracting FFmpeg/FFprobe..." -ForegroundColor Cyan
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

    Write-Host "[5/7] Creating the isolated 64-bit Python build environment..." -ForegroundColor Cyan
    if (Test-Path $VenvRoot) { Remove-Item $VenvRoot -Recurse -Force }
    $pythonArgs = @()
    if ($python.Prefix.Count -gt 0) { $pythonArgs += $python.Prefix }
    $pythonArgs += @("-m", "venv", $VenvRoot)
    Invoke-Checked $python.Command $pythonArgs "Could not create the build virtual environment."

    $venvPython = Join-Path $VenvRoot "Scripts\python.exe"
    Invoke-Checked $venvPython @("-m", "pip", "install", "--upgrade", "pip") "Could not upgrade pip."
    Invoke-Checked $venvPython @("-m", "pip", "install", "-r", $Requirements) "Could not install build dependencies."
    Invoke-Checked $venvPython @("-m", "pip", "check") "The installed Python environment has dependency conflicts."

    Write-Host "[6/7] Running tool and package startup checks..." -ForegroundColor Cyan
    $ytDlpVersion = Get-ToolVersion $ytDlpPath @("--version")
    $denoVersion = Get-ToolVersion (Join-Path $AssetsRoot "deno.exe") @("--version")
    $ffmpegVersion = Get-ToolVersion (Join-Path $AssetsRoot "ffmpeg.exe") @("-version")
    $ffprobeVersion = Get-ToolVersion (Join-Path $AssetsRoot "ffprobe.exe") @("-version")

    $smokeCode = "import customtkinter, comtypes, ytmusicapi, requests, PIL, mutagen, certifi, charset_normalizer, idna, urllib3, psutil, darkdetect, packaging, typing_extensions; import os; assert os.path.isfile(certifi.where()); assert os.path.isdir(os.path.join(os.path.dirname(ytmusicapi.__file__), 'locales'))"
    Invoke-Checked $venvPython @("-c", $smokeCode) "A required Python package or resource failed its import check."

    $syntaxCode = "import ast, pathlib; ast.parse(pathlib.Path(r'$SourcePath').read_text(encoding='utf-8-sig'))"
    Invoke-Checked $venvPython @("-c", $syntaxCode) "The downloaded app source failed its Python syntax check."

    Write-Host "[7/7] Creating a build manifest and checking required files..." -ForegroundColor Cyan
    $requiredFiles = @(
        $SourcePath,
        $ytDlpPath,
        (Join-Path $AssetsRoot "deno.exe"),
        (Join-Path $AssetsRoot "ffmpeg.exe"),
        (Join-Path $AssetsRoot "ffprobe.exe"),
        $venvPython,
        (Join-Path $PSScriptRoot "YTM_Music_Toolkit.spec"),
        $Requirements
    )
    foreach ($file in $requiredFiles) {
        if (-not (Test-Path $file)) { throw "Required build file is missing: $file" }
    }

    $pythonInfo = (& $venvPython -c "import sys,platform; print(sys.version.replace('\n',' ')); print(platform.architecture()[0])" 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not read build Python version." }
    $freeze = @(& $venvPython -m pip freeze --all 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Could not record the installed Python package versions." }

    $manifestLines = @(
        "YTM MUSIC TOOLKIT BUILD INPUT MANIFEST",
        "Created: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
        "",
        "Python runtime:",
        $pythonInfo,
        "",
        "Helper tool versions:",
        "yt-dlp: $ytDlpVersion",
        "Deno: $denoVersion",
        "FFmpeg: $ffmpegVersion",
        "FFprobe: $ffprobeVersion",
        "",
        "Installed Python packages (pip freeze --all):"
    )
    $manifestLines += $freeze
    $manifestLines += @("", "SHA-256 hashes:")
    foreach ($file in $requiredFiles) {
        $hash = Get-FileHash -LiteralPath $file -Algorithm SHA256
        $relative = $file.Substring($PSScriptRoot.Length).TrimStart("\")
        $manifestLines += ($hash.Hash + "  " + $relative)
    }
    Set-Content -LiteralPath $ManifestPath -Value $manifestLines -Encoding UTF8

    Write-Host ""
    Write-Host "ALL BUILD REQUIREMENTS ARE READY." -ForegroundColor Green
    Write-Host "Manifest: $ManifestPath"
    Write-Host "You can now run Build.bat. It will assemble from the prepared files without downloading or installing anything."
    Write-Host "Keep build_workspace intact between preparation and building."
}
catch {
    Write-Host ""
    Write-Host "PREPARATION FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
