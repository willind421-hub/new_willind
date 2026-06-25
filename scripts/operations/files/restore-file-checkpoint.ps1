param(
    [Parameter(Mandatory = $true)]
    [string]$Checkpoint,

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$CheckpointRoot = (Resolve-Path -LiteralPath $Checkpoint).Path
$ManifestPath = Join-Path $CheckpointRoot "manifest.json"
$FilesRoot = Join-Path $CheckpointRoot "files"

if (-not (Test-Path -LiteralPath $ManifestPath)) {
    throw "Checkpoint manifest not found: $ManifestPath"
}
if (-not (Test-Path -LiteralPath $FilesRoot)) {
    throw "Checkpoint files directory not found: $FilesRoot"
}

$Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Manifest.contract -ne "willind.file_checkpoint") {
    throw "Unsupported checkpoint contract: $($Manifest.contract)"
}

$BlockedPattern = "(^|[\\/])(\.env|\.secrets)([\\/]|$)|token|credential|secret"
$Restored = @()

foreach ($Entry in $Manifest.files) {
    $Relative = [string]$Entry.path
    if ($Relative -match $BlockedPattern) {
        throw "Refusing to restore sensitive-looking path: $Relative"
    }
    $Source = Join-Path $FilesRoot ($Relative -replace "/", "\")
    $Destination = Join-Path $Root ($Relative -replace "/", "\")
    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Checkpoint source missing: $Source"
    }
    if (-not $DryRun) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
    }
    $Restored += $Relative
}

[ordered]@{
    ok = $true
    dry_run = [bool]$DryRun
    checkpoint = $CheckpointRoot
    restored = $Restored
} | ConvertTo-Json -Depth 5
