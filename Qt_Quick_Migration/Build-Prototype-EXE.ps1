$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Assets = Join-Path $Root "build_assets"
$QmlRoot = Join-Path $Root "qml"
$DistDir = Join-Path $Root "dist"
$BuildDir = Join-Path $Root "pyinstaller_work"
$Licenses = Join-Path $Assets "licenses"
$Icon = Join-Path $Assets "app.ico"
$IconSource = Join-Path $Root "app_icon.svg"
$IconGenerator = Join-Path $Root "make_app_icon.py"

function Invoke-Native {
    param([string]$Program, [string[]]$Arguments, [string]$Failure)
    & $Program @Arguments
    $Code = $LASTEXITCODE
    if ($Code -ne 0) { throw "$Failure (exit code $Code)." }
}

try {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw "Build Python is missing. Run Install-Dependencies.bat first."
    }
    if (-not (Test-Path -LiteralPath $QmlRoot -PathType Container)) {
        throw "QML interface folder was not found: $QmlRoot"
    }
    if (-not (Test-Path -LiteralPath $IconSource -PathType Leaf)) {
        throw "App icon artwork is missing: $IconSource"
    }
    if (-not (Test-Path -LiteralPath $IconGenerator -PathType Leaf)) {
        throw "App icon generator is missing: $IconGenerator"
    }

    $RequiredTools = @(
        @{ Path = (Join-Path $Assets "yt-dlp.exe"); Args = @("--version") },
        @{ Path = (Join-Path $Assets "ffmpeg.exe"); Args = @("-version") },
        @{ Path = (Join-Path $Assets "ffprobe.exe"); Args = @("-version") },
        @{ Path = (Join-Path $Assets "deno.exe"); Args = @("--version") },
        @{ Path = (Join-Path $Assets "aria2c.exe"); Args = @("--version") }
    )
    foreach ($Tool in $RequiredTools) {
        if (-not (Test-Path -LiteralPath $Tool.Path -PathType Leaf)) {
            throw "Required bundled tool is missing: $($Tool.Path). Run Install-Dependencies.bat."
        }
        $PreviousPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            $null = & $Tool.Path @($Tool.Args) 2>&1
            $Code = $LASTEXITCODE
        }
        finally { $ErrorActionPreference = $PreviousPreference }
        if ($Code -ne 0) { throw "Bundled tool failed its startup check: $($Tool.Path). Rerun Install-Dependencies.bat." }
    }

    Push-Location $Root
    try {
        Write-Host "Running Python syntax checks, backend tests and QML smoke test..."
        Invoke-Native $Python @("-m", "compileall", "-q", "main.py", "backend.py", "ytmusic_resolver.py", "smoke_test.py", "test_backend.py", "test_ytmusic_resolver.py", "make_app_icon.py") "Python syntax check failed"
        Invoke-Native $Python @("-m", "unittest", "test_backend.py", "test_ytmusic_resolver.py", "-v") "Backend regression tests failed"
        $OldQtPlatform = $env:QT_QPA_PLATFORM
        $env:QT_QPA_PLATFORM = "offscreen"
        try { Invoke-Native $Python @("smoke_test.py") "Qt Quick QML startup test failed" }
        finally { $env:QT_QPA_PLATFORM = $OldQtPlatform }
        Invoke-Native $Python @("make_app_icon.py", $IconSource, $Icon) "Could not generate the Windows app icon"
    }
    finally { Pop-Location }

    if (-not (Test-Path -LiteralPath $Icon -PathType Leaf)) { throw "The app icon generator did not create: $Icon" }
    if (-not (Test-Path -LiteralPath $DistDir)) { New-Item -ItemType Directory -Force -Path $DistDir | Out-Null }
    if (Test-Path -LiteralPath $BuildDir) { Remove-Item -LiteralPath $BuildDir -Recurse -Force }

    $PyInstallerArgs = @(
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "YouTube Toolkit Qt Preview",
        "--distpath", $DistDir, "--workpath", $BuildDir, "--specpath", $Root,
        "--collect-all", "PySide6",
        "--collect-all", "mutagen",
        "--collect-all", "ytmusicapi",
        "--collect-all", "yt_dlp",
        "--collect-all", "PIL",
        "--collect-all", "requests",
        "--collect-all", "psutil",
        "--collect-all", "certifi",
        "--hidden-import", "backend",
        "--hidden-import", "ytmusic_resolver",
        "--hidden-import", "PySide6.QtQml",
        "--hidden-import", "PySide6.QtQuick",
        "--add-data", "$QmlRoot;qml",
        "--add-data", "$Icon;.",
        "--add-binary", "$(Join-Path $Assets 'yt-dlp.exe');.",
        "--add-binary", "$(Join-Path $Assets 'ffmpeg.exe');.",
        "--add-binary", "$(Join-Path $Assets 'ffprobe.exe');.",
        "--add-binary", "$(Join-Path $Assets 'deno.exe');.",
        "--add-binary", "$(Join-Path $Assets 'aria2c.exe');.",
        (Join-Path $Root "main.py")
    )

    if (Test-Path -LiteralPath $Licenses -PathType Container) {
        $PyInstallerArgs += @("--add-data", "$Licenses;licenses")
    }
    Get-ChildItem -LiteralPath $Assets -Filter "*.dll" -File -ErrorAction SilentlyContinue |
        ForEach-Object { $PyInstallerArgs += @("--add-binary", "$($_.FullName);.") }
    $PyInstallerArgs += @("--icon", $Icon)

    Write-Host ""
    Write-Host "Building a one-file app with the Python runtime, Qt/QML UI, app icon, app modules, packages, yt-dlp, FFmpeg, FFprobe, Deno, aria2c and helper DLLs..."
    Push-Location $Root
    try { Invoke-Native $Python (@("-m", "PyInstaller") + $PyInstallerArgs) "PyInstaller could not create the standalone EXE" }
    finally { Pop-Location }

    $Output = Join-Path $DistDir "YouTube Toolkit Qt Preview.exe"
    if (-not (Test-Path -LiteralPath $Output -PathType Leaf)) { throw "Build reported success but EXE is missing: $Output" }
    $Hash = (Get-FileHash -LiteralPath $Output -Algorithm SHA256).Hash
    $Size = [Math]::Round((Get-Item -LiteralPath $Output).Length / 1MB, 1)
    Write-Host ""
    Write-Host "BUILD FINISHED." -ForegroundColor Green
    Write-Host "EXE: $Output"
    Write-Host "Size: $Size MiB"
    Write-Host "SHA-256: $Hash"
    Write-Host "Personal cookies and user settings intentionally remain outside the EXE."
}
catch {
    Write-Host ""
    Write-Host "Qt Quick EXE build failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
