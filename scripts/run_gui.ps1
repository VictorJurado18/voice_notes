$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VenvPythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Ambiente local nao encontrado."
    Write-Host "Execute Instalar.bat antes de abrir o gravador."
    exit 1
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"

if (Test-Path $VenvPythonw) {
    & $VenvPythonw -m gravador_audio.gui
}
else {
    & $VenvPython -m gravador_audio.gui
}
exit $LASTEXITCODE
