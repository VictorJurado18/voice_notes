param(
    [Parameter(Mandatory = $true)]
    [string]$ToolsRoot
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$nodeHome = Join-Path $ToolsRoot "node"
$cliHome = Join-Path $ToolsRoot "cli"
$logPath = Join-Path $ToolsRoot "provider-setup.log"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Write-SetupLog([string]$Message) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $logPath -Value "[$stamp] $Message" -Encoding UTF8
}

function Get-RemoteText([string]$Url) {
    $client = New-Object System.Net.WebClient
    $client.Headers.Add("User-Agent", "VoiceNotesInstaller/1.0")
    try { return $client.DownloadString($Url) }
    finally { $client.Dispose() }
}

function Save-RemoteFile([string]$Url, [string]$Destination) {
    $curl = Get-Command "curl.exe" -ErrorAction SilentlyContinue
    if ($curl) {
        & $curl.Source --fail --location --silent --show-error --user-agent "VoiceNotesInstaller/1.0" $Url --output $Destination
        if ($LASTEXITCODE -ne 0) { throw "curl could not download $Url (exit code $LASTEXITCODE)." }
        return
    }
    $client = New-Object System.Net.WebClient
    $client.Headers.Add("User-Agent", "VoiceNotesInstaller/1.0")
    try { $client.DownloadFile($Url, $Destination) }
    finally { $client.Dispose() }
}

try {
    New-Item -ItemType Directory -Force -Path $ToolsRoot | Out-Null
    Write-SetupLog "Preparing bundled Node.js runtime and summary providers."

    $nodeExe = Join-Path $nodeHome "node.exe"
    if (-not (Test-Path $nodeExe)) {
        $allReleases = Get-RemoteText "https://nodejs.org/dist/index.json" | ConvertFrom-Json
        $release = @(
            $allReleases | Where-Object { $_.lts -and (@($_.files) -contains "win-x64-zip") } |
                Select-Object -First 1
        )[0]
        if (-not $release) {
            throw "Could not find a current Node.js LTS Windows x64 release."
        }

        $archiveName = "node-$($release.version)-win-x64.zip"
        $archivePath = Join-Path $env:TEMP $archiveName
        $extractRoot = Join-Path $env:TEMP "voice-notes-node-$($release.version)"
        $baseUrl = "https://nodejs.org/dist/$($release.version)"
        Save-RemoteFile "$baseUrl/$archiveName" $archivePath

        $checksums = Get-RemoteText "$baseUrl/SHASUMS256.txt"
        $expectedHash = (($checksums -split "`n") |
            Where-Object { $_ -match [regex]::Escape($archiveName) } |
            Select-Object -First 1).Split()[0]
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        $archiveStream = [System.IO.File]::OpenRead($archivePath)
        try {
            $actualHash = ([BitConverter]::ToString($sha256.ComputeHash($archiveStream))).Replace("-", "").ToLowerInvariant()
        }
        finally {
            $archiveStream.Dispose()
            $sha256.Dispose()
        }
        if (-not $expectedHash -or $actualHash -ne $expectedHash.ToLowerInvariant()) {
            throw "The downloaded Node.js archive did not pass checksum verification."
        }

        if (Test-Path $extractRoot) { Remove-Item -LiteralPath $extractRoot -Recurse -Force }
        Expand-Archive -LiteralPath $archivePath -DestinationPath $extractRoot -Force
        $extractedNode = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
        if (-not $extractedNode) { throw "The Node.js archive was empty." }
        if (Test-Path $nodeHome) { Remove-Item -LiteralPath $nodeHome -Recurse -Force }
        Move-Item -LiteralPath $extractedNode.FullName -Destination $nodeHome
        Remove-Item -LiteralPath $archivePath -Force
        Remove-Item -LiteralPath $extractRoot -Recurse -Force
        Write-SetupLog "Bundled Node.js runtime installed: $($release.version)."
    }

    $npmCmd = Join-Path $nodeHome "npm.cmd"
    if (-not (Test-Path $npmCmd)) { throw "Bundled npm.cmd was not found." }
    & $npmCmd --prefix $cliHome install --global "@openai/codex" "@anthropic-ai/claude-code" --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "npm finished with exit code $LASTEXITCODE." }
    Write-SetupLog "Codex CLI and Claude Code were installed for this Windows user."
}
catch {
    try {
        New-Item -ItemType Directory -Force -Path $ToolsRoot | Out-Null
        Write-SetupLog "Provider setup could not finish: $($_.Exception.Message)"
    }
    catch {
        # Keep the application installer successful even when networking is blocked.
    }
}
