$ErrorActionPreference = "Stop"

$RepoRaw = "https://raw.githubusercontent.com/ykbokka/ytdlp/main/YTM_Music_Toolkit.pyw"
$InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\YTM Music Toolkit"
$KitRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Requirements = Join-Path $KitRoot "requirements.txt"
$VenvRoot = Join-Path $InstallRoot "venv"
$ToolsRoot = Join-Path $InstallRoot "tools"
$Launcher = Join-Path $InstallRoot "Launch.bat"

function Test-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-WinGetInstall {
    param(
        [string]$Id,
        [string]$DisplayName
    )
    if (-not (Test-Command "winget")) {
        throw "WinGet is not available. Install $DisplayName manually, then rerun Install.bat."
    }
    Write-Host ""
    Write-Host "$DisplayName is required but was not detected." -ForegroundColor Yellow
    $answer = Read-Host "Install $DisplayName using WinGet package '$Id'? [Y/N]"
    if ($answer -notmatch "^(Y|YES)$") {
        throw "Installation cancelled because $DisplayName is missing."
    }
    & winget install --id $Id --exact --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "WinGet failed to install $DisplayName (exit code $LASTEXITCODE)."
    }
}

function Refresh-Path {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $parts = @($env:PATH, $userPath, $machinePath, (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links"))
    $env:PATH = (($parts | Where-Object { $_ } | ForEach-Object { $_ -split ";" } | Where-Object { $_ } | Select-Object -Unique) -join ";")
}

function Find-PythonLauncher {
    Refresh-Path

    # Prefer the regular python command when it points to a real supported runtime.
    if (Test-Command "python") {
        $pythonVersion = & cmd.exe /d /c "python -V 2>nul"
        if ($LASTEXITCODE -eq 0 -and $pythonVersion -match "Python 3\.(10|11|12|13|14)(\.|$)") {
            return @{ Command = "python"; Prefix = @() }
        }
    }

    # Check installed runtimes newest-first, including the user's existing Python 3.14.
    # Run probes through cmd.exe so missing py runtimes' stderr won't stop PowerShell.
    if (Test-Command "py") {
        foreach ($version in @("3.14", "3.13", "3.12", "3.11", "3.10")) {
            & cmd.exe /d /c "py -$version -V >nul 2>nul"
            if ($LASTEXITCODE -eq 0) {
                return @{ Command = "py"; Prefix = @("-$version") }
            }
        }
    }

    return $null
}

try {
    Write-Host ""
    Write-Host "YTM Music Toolkit — Dedicated Installer" -ForegroundColor Cyan
    Write-Host "Target: $InstallRoot"
    Write-Host "This installs the raw .pyw app, not an EXE."
    Write-Host ""

    $python = Find-PythonLauncher
    if (-not $python) {
        Invoke-WinGetInstall -Id "Python.Python.3.12" -DisplayName "Python 3.12"
        $python = Find-PythonLauncher
    }
    if (-not $python) {
        throw "Python 3.10 or newer could not be found after installation. Restart Windows or install Python 3.12, then rerun."
    }

    Refresh-Path
    if (-not (Test-Command "deno")) {
        Invoke-WinGetInstall -Id "DenoLand.Deno" -DisplayName "Deno (YouTube JavaScript challenge runtime)"
    }

    Refresh-Path
    if (-not (Test-Command "ffmpeg")) {
        Invoke-WinGetInstall -Id "Gyan.FFmpeg.Shared" -DisplayName "FFmpeg (media merging and conversion)"
    }

    Refresh-Path
    New-Item -ItemType Directory -Force -Path $InstallRoot, $ToolsRoot | Out-Null

    Write-Host "Downloading the released application source..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $RepoRaw -OutFile (Join-Path $InstallRoot "YTM_Music_Toolkit.pyw") -UseBasicParsing

    $pythonExe = $python.Command
    $pythonArgs = @()
    if ($python.Prefix.Count -gt 0) { $pythonArgs += $python.Prefix }
    $pythonArgs += @("-m", "venv", $VenvRoot)
    & $pythonExe @pythonArgs
    if ($LASTEXITCODE -ne 0) { throw "Could not create the application's Python virtual environment." }

    $venvPython = Join-Path $VenvRoot "Scripts\python.exe"
    if (-not (Test-Path $venvPython)) { throw "Virtual environment Python was not created at $venvPython" }

    Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }
    & $venvPython -m pip install -r $Requirements
    if ($LASTEXITCODE -ne 0) { throw "Could not install the Python requirements." }

    @'
@echo off
setlocal
set "APP_DIR=%~dp0"
set "PATH=%APP_DIR%venv\Scripts;%APP_DIR%tools;%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
start "" "%APP_DIR%venv\Scripts\pythonw.exe" "%APP_DIR%YTM_Music_Toolkit.pyw"
endlocal
'@ | Set-Content -Path $Launcher -Encoding ASCII

    $programsDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    $startMenuLink = Join-Path $programsDir "YTM Music Toolkit.lnk"
    $desktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "YTM Music Toolkit.lnk"
    $shell = New-Object -ComObject WScript.Shell
    foreach ($linkPath in @($startMenuLink, $desktopLink)) {
        $shortcut = $shell.CreateShortcut($linkPath)
        $shortcut.TargetPath = $Launcher
        $shortcut.WorkingDirectory = $InstallRoot
        $shortcut.Description = "Launch YTM Music Toolkit"
        $shortcut.IconLocation = (Join-Path $VenvRoot "Scripts\pythonw.exe") + ",0"
        $shortcut.Save()
    }

    Write-Host ""
    Write-Host "Installation completed successfully." -ForegroundColor Green
    Write-Host "Installed app: $InstallRoot"
    Write-Host "Python: $(& $venvPython --version)"
    Write-Host "Deno: $(& deno --version | Select-Object -First 1)"
    if (Test-Command "ffmpeg") { Write-Host "FFmpeg: detected" }
    Write-Host "Cookies are not included. Select your own cookies.txt inside the app when needed."
    $launch = Read-Host "Launch YTM Music Toolkit now? [Y/N]"
    if ($launch -match "^(Y|YES)$") { Start-Process -FilePath $Launcher }
    exit 0
}
catch {
    Write-Host ""
    Write-Host "INSTALLATION FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "No cookies or personal download files were changed."
    exit 1
}
