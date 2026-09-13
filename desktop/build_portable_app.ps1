$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$pyVersion = "3.11.9"
$embedZip = "python-$pyVersion-embed-amd64.zip"
$embedUrl = "https://www.python.org/ftp/python/$pyVersion/$embedZip"
$runtimeDir = Join-Path $root "runtime"

Write-Host "=== AssaFlex Bearing Tool -- portable app builder ===" -ForegroundColor Cyan
Write-Host "This only needs to be run ONCE, on one Windows machine with normal"
Write-Host "internet access. The resulting folder is what you zip up and share"
Write-Host "with colleagues -- they never need to run this script."
Write-Host ""

if (Test-Path $runtimeDir) {
    Write-Host "A 'runtime' folder already exists here." -ForegroundColor Yellow
    $answer = Read-Host "Delete it and rebuild from scratch? [y/N]"
    if ($answer -eq "y" -or $answer -eq "Y") {
        Remove-Item $runtimeDir -Recurse -Force
    } else {
        Write-Host "Keeping existing runtime -- skipping Python/package setup."
    }
}

if (-not (Test-Path $runtimeDir)) {
    if (-not (Test-Path $embedZip)) {
        Write-Host "Downloading Python $pyVersion (embeddable, ~10 MB) from python.org..."
        try {
            Invoke-WebRequest -Uri $embedUrl -OutFile $embedZip
        } catch {
            Write-Host ""
            Write-Host "Couldn't reach python.org from this machine ($($_.Exception.Message))." -ForegroundColor Red
            Write-Host "If your network blocks it, download this file yourself from another"
            Write-Host "machine/browser and place it in this folder, then re-run this script:"
            Write-Host "  $embedUrl"
            exit 1
        }
    }

    Write-Host "Extracting Python runtime..."
    Expand-Archive -Path $embedZip -DestinationPath $runtimeDir

    Write-Host "Enabling site-packages (needed for pip-installed libraries)..."
    $pthFile = Get-ChildItem -Path $runtimeDir -Filter "python*._pth" | Select-Object -First 1
    (Get-Content $pthFile.FullName) -replace '^#\s*import site', 'import site' | Set-Content $pthFile.FullName

    Write-Host "Installing pip..."
    & "$runtimeDir\python.exe" "$root\get-pip.py" --no-warn-script-location | Out-Null

    Write-Host "Installing Streamlit and dependencies from PyPI (needs internet access)..."
    & "$runtimeDir\python.exe" -m pip install -r "$root\requirements.txt"
}

Write-Host "Copying application files..."
$appDir = Join-Path $root "app"
if (Test-Path $appDir) { Remove-Item $appDir -Recurse -Force }
New-Item -ItemType Directory -Path $appDir | Out-Null
Copy-Item -Path (Join-Path $root "..\app.py") -Destination $appDir
Copy-Item -Path (Join-Path $root "..\bearing_tool") -Destination $appDir -Recurse
Copy-Item -Path (Join-Path $root "..\schedules") -Destination $appDir -Recurse

Write-Host ""
Write-Host "=== Done! ===" -ForegroundColor Green
Write-Host "This 'desktop' folder is now a complete, self-contained app."
Write-Host ""
Write-Host "Optional cleanup before sharing (not needed to RUN the app -- only keep"
Write-Host "these if you might rebuild later):"
Write-Host "    Remove-Item '$root\$embedZip', '$root\get-pip.py'"
Write-Host ""
Write-Host "Then zip this whole folder and share it. Colleagues just unzip it and"
Write-Host "double-click 'Run AssaFlex Bearing Tool.bat' -- no install, no Python,"
Write-Host "no terminal needed on their end."
