$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Write-Host ""
Write-Host "gravador_audio - instalacao para Windows"
Write-Host "========================================"
Write-Host ""

$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCommand) {
    Write-Host "Python nao foi encontrado no PATH."
    Write-Host "Instale Python 3.12 ou superior em https://www.python.org/downloads/windows/"
    Write-Host "Durante a instalacao, marque a opcao: Add python.exe to PATH"
    exit 1
}

$VersionText = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$VersionParts = $VersionText.Split(".")
$Major = [int]$VersionParts[0]
$Minor = [int]$VersionParts[1]

if ($Major -lt 3 -or ($Major -eq 3 -and $Minor -lt 12)) {
    Write-Host "Python $VersionText encontrado, mas este projeto precisa de Python 3.12 ou superior."
    exit 1
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "Criando ambiente local .venv..."
    & python -m venv (Join-Path $ProjectRoot ".venv")
}

Write-Host "Atualizando pip..."
& $VenvPython -m pip install --upgrade pip

Write-Host "Instalando dependencias de audio..."
& $VenvPython -m pip install -e $ProjectRoot

Write-Host ""
Write-Host "Instalacao concluida."
Write-Host "Agora execute Gravar.bat para criar uma gravacao."
