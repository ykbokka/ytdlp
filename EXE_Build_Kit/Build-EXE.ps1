$ErrorActionPreference = "Stop"

$WorkRoot = Join-Path $PSScriptRoot "build_workspace"
$AssetsRoot = Join-Path $WorkRoot "assets"
$VenvPython = Join-Path $WorkRoot "venv\Scripts\python.exe"
$SourcePath = Join-Path $WorkRoot "YTM_Music_Toolkit.pyw"
$SpecPath = Join-Path $PSScriptRoot "YTM_Music_Toolkit.spec"
$Requirements = Join-Path $PSScriptRoot "requirements-build.txt"
$DistRoot = Join-Path $PSScriptRoot "dist"
$PyInstallerWork = Join-Path $WorkRoot "pyinstaller_work"
$ManifestPath = Join-Path $WorkRoot "build_manifest.txt"
$ExePath = Join-Path $DistRoot "YTM Music Toolkit.exe"

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments, [string]$Failure)

    # Windows PowerShell 5.1 can treat native stderr output as a terminating
    # error when ErrorActionPreference is Stop. Temporarily relax that behavior,
    # merge the streams, and rely on the process exit code instead.
    $oldPreference = $ErrorActionPreference
    $nativeExitCode = 0
    try {
        $ErrorActionPreference = "Continue"
        & $Program @Arguments 2>&1 | ForEach-Object { Write-Host $_ }
        $nativeExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }

    if ($nativeExitCode -ne 0) { throw $Failure }
}

function Test-Tool {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "A prepared helper executable failed its startup check: $Program"
    }
}

try {
    Write-Host ""
    Write-Host "YTM Music Toolkit - ASSEMBLE EXE ONLY" -ForegroundColor Cyan
    Write-Host "No downloads, package installation, or environment creation happen in this stage."
    Write-Host ""

    $requiredFiles = @(
        $SourcePath,
        $SpecPath,
        $Requirements,
        $VenvPython,
        $ManifestPath,
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

    # Verify that prepared inputs still match the SHA-256 values recorded
    # during requirement preparation. This catches incomplete or stale inputs.
    $manifestLines = Get-Content -LiteralPath $ManifestPath
    $inHashSection = $false
    $verifiedHashCount = 0

    foreach ($line in $manifestLines) {
        if ($line.Trim() -eq "SHA-256 hashes:") {
            $inHashSection = $true
            continue
        }
        if (-not $inHashSection -or [string]::IsNullOrWhiteSpace($line)) { continue }

        if ($line -match '^([A-Fa-f0-9]{64})\s+(.+)$') {
            $expectedHash = $matches[1].ToUpperInvariant()
            $relativePath = $matches[2].Trim()
            $candidate = Join-Path $PSScriptRoot $relativePath

            if (-not (Test-Path $candidate)) {
                throw ("Manifest input is missing: " + $relativePath + ". Run Download-Requirements.bat again.")
            }

            $actualHash = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash
            if ($actualHash -ne $expectedHash) {
                throw ("A prepared input changed after preparation: " + $relativePath + ". Run Download-Requirements.bat again.")
            }

            $verifiedHashCount++
        }
    }

    if ($verifiedHashCount -lt 8) {
        throw "The build manifest is incomplete. Run Download-Requirements.bat again."
    }
    Write-Host "Verified $verifiedHashCount prepared input hashes." -ForegroundColor Green

    $archCode = "import sys; raise SystemExit(0 if sys.maxsize > 2**32 else 1)"
    Invoke-Checked $VenvPython @("-c", $archCode) "The prepared Python environment is not 64-bit. Run Download-Requirements.bat using 64-bit Python."

    Invoke-Checked $VenvPython @("-m", "pip", "check") "The prepared Python environment has dependency conflicts."

    $smokeCode = "import customtkinter, comtypes, ytmusicapi, requests, PIL, mutagen, certifi, charset_normalizer, idna, urllib3, psutil, darkdetect, packaging, typing_extensions; import os; assert os.path.isfile(certifi.where()); assert os.path.isdir(os.path.join(os.path.dirname(ytmusicapi.__file__), 'locales'))"
    Invoke-Checked $VenvPython @("-c", $smokeCode) "A required Python package or resource failed its import check."

    $syntaxCode = "import ast, pathlib; ast.parse(pathlib.Path(r'$SourcePath').read_text(encoding='utf-8-sig'))"
    Invoke-Checked $VenvPython @("-c", $syntaxCode) "The downloaded app source failed its Python syntax check."

    Test-Tool (Join-Path $AssetsRoot "yt-dlp.exe") @("--version")
    Test-Tool (Join-Path $AssetsRoot "deno.exe") @("--version")
    Test-Tool (Join-Path $AssetsRoot "ffmpeg.exe") @("-version")
    Test-Tool (Join-Path $AssetsRoot "ffprobe.exe") @("-version")

    New-Item -ItemType Directory -Force -Path $DistRoot, $PyInstallerWork | Out-Null

    # Remove an older output first so a failed build cannot be mistaken for success.
    if (Test-Path $ExePath) { Remove-Item $ExePath -Force }

    Write-Host "Performing a clean PyInstaller assembly..." -ForegroundColor Cyan
    Invoke-Checked $VenvPython @(
        "-m", "PyInstaller",
        $SpecPath,
        "--noconfirm",
        "--clean",
        "--distpath", $DistRoot,
        "--workpath", $PyInstallerWork
    ) "PyInstaller failed. Review the build output above."

    if (-not (Test-Path $ExePath)) {
        throw "Build completed but the expected EXE was not found."
    }
    if ((Get-Item $ExePath).Length -lt 20MB) {
        throw "The output EXE is suspiciously small. The build may be incomplete."
    }

    $exeHash = Get-FileHash -LiteralPath $ExePath -Algorithm SHA256

    Write-Host ""
    Write-Host "BUILD COMPLETED." -ForegroundColor Green
    Write-Host "EXE: $ExePath"
    Write-Host "Size: $([math]::Round((Get-Item $ExePath).Length / 1MB, 1)) MB"
    Write-Host "SHA-256: $($exeHash.Hash)"
    Write-Host "Input manifest: $ManifestPath"
    Write-Host "This step used prepared files only; it did not download or install anything."
}
catch {
    Write-Host ""
    Write-Host "BUILD FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
