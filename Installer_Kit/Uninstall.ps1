$ErrorActionPreference = "Stop"
$InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\YTM Music Toolkit"
$StartMenuLink = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\YTM Music Toolkit.lnk"
$DesktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "YTM Music Toolkit.lnk"

try {
    $confirm = Read-Host "Remove the installed app at '$InstallRoot' and its shortcuts? User config, logs, cookies, and downloads will be kept. [Y/N]"
    if ($confirm -notmatch "^(Y|YES)$") {
        Write-Host "Uninstall cancelled."
        exit 0
    }
    foreach ($link in @($StartMenuLink, $DesktopLink)) {
        if (Test-Path $link) { Remove-Item -LiteralPath $link -Force }
    }
    if (Test-Path $InstallRoot) { Remove-Item -LiteralPath $InstallRoot -Recurse -Force }
    Write-Host "Application and shortcuts removed." -ForegroundColor Green
    Write-Host "Kept: %USERPROFILE%\.ytm_music_toolkit.json, %USERPROFILE%\Documents\YTDLP, cookies, and downloaded media."
    exit 0
}
catch {
    Write-Host "UNINSTALL FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
