$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Write-Host ""
Write-Host "record-transcript-resume - Windows installation"
Write-Host "================================================"
Write-Host ""

$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCommand) {
    Write-Host "Python was not found in PATH."
    Write-Host "Install Python 3.12 or higher from https://www.python.org/downloads/windows/"
    Write-Host "During installation, check the option: Add python.exe to PATH"
    exit 1
}

$VersionText = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$VersionParts = $VersionText.Split(".")
$Major = [int]$VersionParts[0]
$Minor = [int]$VersionParts[1]

if ($Major -lt 3 -or ($Major -eq 3 -and $Minor -lt 12)) {
    Write-Host "Python $VersionText found, but this project requires Python 3.12 or higher."
    exit 1
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating local virtual environment .venv..."
    & python -m venv (Join-Path $ProjectRoot ".venv")
}

Write-Host "Updating pip..."
& $VenvPython -m pip install --upgrade pip

Write-Host "Installing application and development dependencies..."
& $VenvPython -m pip install -e "$ProjectRoot[dev]"

Write-Host ""
Write-Host "Installation complete."
Write-Host "Open the interface with: Open Recorder.vbs"
Write-Host "Or record from the terminal with: Record.bat"
