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
& $Python -m pip install -e "$ProjectRoot[build,gpu]"
if ($LASTEXITCODE -ne 0) {
    throw "Could not install packaging and CUDA dependencies."
}

$SitePackages = Join-Path $ProjectRoot ".venv\Lib\site-packages"
$CudaBundleArgs = @()
foreach ($component in @("cublas", "cudnn", "cuda_nvrtc")) {
    $binaryDir = Join-Path $SitePackages "nvidia\$component\bin"
    if (-not (Test-Path -LiteralPath $binaryDir)) {
        throw "Missing NVIDIA runtime library directory: $binaryDir"
    }
    $CudaBundleArgs += @("--add-binary", "$binaryDir;.")
}
foreach ($package in @("nvidia_cublas_cu12", "nvidia_cudnn_cu12", "nvidia_cuda_nvrtc_cu12")) {
    $license = Get-ChildItem -Path $SitePackages -Directory -Filter "$package-*.dist-info" |
        ForEach-Object { Join-Path $_.FullName "licenses\License.txt" } |
        Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1
    if (-not $license) {
        throw "Missing NVIDIA runtime license for $package"
    }
    $CudaBundleArgs += @("--add-data", "$license;licenses\NVIDIA\$package")
}

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
    @CudaBundleArgs `
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
    --collect-all send2trash `
    --hidden-import lameenc `
    --hidden-import numpy `
    --distpath $DistDir `
    --workpath $BuildDir `
    (Join-Path $ProjectRoot "src\record_transcript_resume\gui.py")

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed."
}

# PyInstaller may also discover some NVIDIA DLLs under their wheel paths.
# Keep the explicitly bundled root copies and omit identical duplicates.
$InternalDir = Join-Path $AppDistDir "_internal"
foreach ($component in @("cublas", "cudnn", "cuda_nvrtc")) {
    $nestedDir = Join-Path $InternalDir "nvidia\$component\bin"
    if (-not (Test-Path -LiteralPath $nestedDir)) { continue }
    foreach ($duplicate in Get-ChildItem -LiteralPath $nestedDir -File -Filter "*.dll") {
        $primary = Join-Path $InternalDir $duplicate.Name
        if ((Test-Path -LiteralPath $primary) -and
            (Get-FileHash -LiteralPath $duplicate.FullName -Algorithm SHA256).Hash -eq
            (Get-FileHash -LiteralPath $primary -Algorithm SHA256).Hash) {
            Remove-Item -LiteralPath $duplicate.FullName -Force
        }
    }
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
