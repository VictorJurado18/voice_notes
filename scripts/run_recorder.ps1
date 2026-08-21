$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Write-Host ""
Write-Host "record-transcript-resume"
Write-Host "========================"
Write-Host ""

if (-not (Test-Path $VenvPython)) {
    Write-Host "Virtual environment not found."
    Write-Host "Run Install.bat before recording."
    exit 1
}

$Duration = Read-Host "How many seconds do you want to record? [default: 20]"
if ([string]::IsNullOrWhiteSpace($Duration)) {
    $Duration = "20"
}

$Mode = Read-Host "Mode: 1 = microphone + system, 2 = microphone only, 3 = system only [default: 1]"
if ([string]::IsNullOrWhiteSpace($Mode)) {
    $Mode = "1"
}

$Arguments = @("-m", "record_transcript_resume.cli", "record", "--duration", $Duration)

if ($Mode -eq "2") {
    $Arguments += "--microphone-only"
}
elseif ($Mode -eq "3") {
    $Arguments += "--system-only"
}
elseif ($Mode -ne "1") {
    Write-Host "Invalid mode. Use 1, 2 or 3."
    exit 1
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"

Write-Host ""
Write-Host "Recording... keep this window open."
Write-Host ""

& $VenvPython @Arguments
$ExitCode = $LASTEXITCODE

Write-Host ""
if ($ExitCode -eq 0) {
    Write-Host "Done. File saved in the output folder."
    $OutputDir = Join-Path $env:USERPROFILE "Music\record-transcript-resume"
    $Latest = Get-ChildItem -File $OutputDir -Filter "*.mp3" -Recurse -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($Latest) {
        Write-Host "Latest file: $($Latest.FullName)"
    }
}
else {
    Write-Host "Recording failed. Exit code: $ExitCode"
}

exit $ExitCode
