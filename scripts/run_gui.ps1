$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VenvPythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Virtual environment not found."
    Write-Host "Run Install.bat before opening the recorder."
    exit 1
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"

if (Test-Path $VenvPythonw) {
    & $VenvPythonw -m record_transcript_resume.gui --widget
}
else {
    & $VenvPython -m record_transcript_resume.gui --widget
}
exit $LASTEXITCODE
