$ErrorActionPreference = "Stop"
$InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\YTM Music Toolkit"
$RepoRaw = "https://raw.githubusercontent.com/ykbokka/ytdlp/main/YTM_Music_Toolkit.pyw"
$KitRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $InstallRoot "venv\Scripts\python.exe"

try {
    if (-not (Test-Path $VenvPython)) { throw "The app does not appear to be installed at $InstallRoot. Run Install.bat first." }
    $appPath = Join-Path $InstallRoot "YTM_Music_Toolkit.pyw"
    $tempPath = Join-Path $InstallRoot "YTM_Music_Toolkit.pyw.new"
    Write-Host "Downloading the current released .pyw..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $RepoRaw -OutFile $tempPath -UseBasicParsing
    if ((Get-Item $tempPath).Length -lt 10000) { throw "Downloaded source is unexpectedly small; refusing to replace the installed app." }
    Move-Item -Force $tempPath $appPath

    Write-Host "Updating Python dependencies..." -ForegroundColor Cyan
    & $VenvPython -m pip install --upgrade -r (Join-Path $KitRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Dependency update failed with exit code $LASTEXITCODE." }
    Write-Host "Update completed. Your config, cookies, and downloaded files were not changed." -ForegroundColor Green
    exit 0
}
catch {
    Write-Host "UPDATE FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
