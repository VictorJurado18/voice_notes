param(
    [switch]$SkipInstaller,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$BuildDir = Join-Path $ProjectRoot "build"
$DistDir = Join-Path $ProjectRoot "dist"
$AppDistDir = Join-Path $DistDir "VoiceNotes"
$SetupFile = Join-Path $ProjectRoot "installer\VoiceNotes.iss"

if (-not (Test-Path $Python)) {
    throw "Virtual environment not found. Run Install.bat once on the build computer."
}

if ($Clean) {
    foreach ($target in @($BuildDir, $AppDistDir, (Join-Path $DistDir "VoiceNotes-Setup.exe"))) {
        if (Test-Path $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
        }
    }
}

Write-Host "Installing packaging tools..."
& $Python -m pip install -e "$ProjectRoot[build]"

Write-Host "Building standalone Voice Notes application..."
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --manifest (Join-Path $ProjectRoot "installer\VoiceNotes.manifest") `
    --name "VoiceNotes" `
    --icon (Join-Path $ProjectRoot "assets\voice-notes.ico") `
    --paths (Join-Path $ProjectRoot "src") `
    --add-data "$(Join-Path $ProjectRoot 'assets\voice-notes.png');assets" `
    --add-data "$(Join-Path $ProjectRoot 'assets\pix-victor-nemeth-jurado.png');assets" `
    --add-data "$(Join-Path $ProjectRoot 'pyproject.toml');." `
    --add-data "$(Join-Path $ProjectRoot 'src\record_transcript_resume\resources');record_transcript_resume/resources" `
    --collect-all customtkinter `
    --collect-all faster_whisper `
    --collect-all ctranslate2 `
    --collect-all av `
    --collect-all onnxruntime `
    --collect-all tokenizers `
    --collect-all pyaudiowpatch `
    --collect-all pystray `
    --collect-all PIL `
    --collect-all pyannote.audio `
    --collect-all pyannote.core `
    --collect-all torch `
    --collect-all torchaudio `
    --collect-all torchcodec `
    --collect-all keyring `
    --collect-all yt_dlp `
    --collect-all imageio_ffmpeg `
    --collect-all docx `
    --collect-all reportlab `
    --hidden-import lameenc `
    --hidden-import numpy `
    --distpath $DistDir `
    --workpath $BuildDir `
    (Join-Path $ProjectRoot "src\record_transcript_resume\gui.py")

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed."
}

if ($SkipInstaller) {
    Write-Host "Standalone app created at: $AppDistDir\VoiceNotes.exe"
    exit 0
}

$InnoCandidates = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path $_) }
$InnoCompiler = $InnoCandidates | Select-Object -First 1

if (-not $InnoCompiler) {
    throw "Inno Setup 6 was not found. Install it, then run this script again."
}

Write-Host "Creating Windows installer..."
& $InnoCompiler "/O$DistDir" $SetupFile
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed."
}

$VersionMatch = Select-String -Path (Join-Path $ProjectRoot "pyproject.toml") -Pattern '^version\s*=\s*"([^"]+)"'
if (-not $VersionMatch) {
    throw "Could not read the application version from pyproject.toml."
}
$Version = $VersionMatch.Matches[0].Groups[1].Value
$InstallerPath = Join-Path $DistDir "VoiceNotes-Setup-$Version.exe"
if (-not (Test-Path -LiteralPath $InstallerPath)) {
    throw "Installer was not generated: $InstallerPath"
}
Write-Host "Installer created at: $InstallerPath"
