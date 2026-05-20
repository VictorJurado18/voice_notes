$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Write-Host ""
Write-Host "gravador_audio"
Write-Host "=============="
Write-Host ""

if (-not (Test-Path $VenvPython)) {
    Write-Host "Ambiente local nao encontrado."
    Write-Host "Execute Instalar.bat antes de gravar."
    exit 1
}

$Duration = Read-Host "Quantos segundos deseja gravar? [padrao: 20]"
if ([string]::IsNullOrWhiteSpace($Duration)) {
    $Duration = "20"
}

$Mode = Read-Host "Modo: 1 = microfone + sistema, 2 = so microfone, 3 = so sistema [padrao: 1]"
if ([string]::IsNullOrWhiteSpace($Mode)) {
    $Mode = "1"
}

$Arguments = @("-m", "gravador_audio.cli", "--duration", $Duration)

if ($Mode -eq "2") {
    $Arguments += "--microphone-only"
}
elseif ($Mode -eq "3") {
    $Arguments += "--system-only"
}
elseif ($Mode -ne "1") {
    Write-Host "Modo invalido. Use 1, 2 ou 3."
    exit 1
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"

Write-Host ""
Write-Host "Gravando... mantenha esta janela aberta."
Write-Host ""

& $VenvPython @Arguments
$ExitCode = $LASTEXITCODE

Write-Host ""
if ($ExitCode -eq 0) {
    Write-Host "Pronto. O arquivo foi salvo na pasta recordings."
    $Latest = Get-ChildItem -File (Join-Path $ProjectRoot "recordings") -Filter "*.mp3" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($Latest) {
        Write-Host "Ultimo arquivo: $($Latest.FullName)"
    }
}
else {
    Write-Host "A gravacao falhou. Codigo de saida: $ExitCode"
}

exit $ExitCode
