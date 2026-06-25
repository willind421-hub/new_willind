param(
    [Parameter(Mandatory = $true)]
    [string[]]$Path,

    [string]$Label = "manual"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$SafeLabel = ($Label -replace "[^A-Za-z0-9._-]", "-").Trim("-")
if ([string]::IsNullOrWhiteSpace($SafeLabel)) {
    $SafeLabel = "manual"
}
$CheckpointRoot = Join-Path $Root "runtime\rollback\$Timestamp-$SafeLabel"
$FilesRoot = Join-Path $CheckpointRoot "files"
New-Item -ItemType Directory -Force -Path $FilesRoot | Out-Null

$BlockedPattern = "(^|[\\/])(\.env|\.secrets)([\\/]|$)|token|credential|secret"
$Entries = @()

foreach ($Item in $Path) {
    $Resolved = Resolve-Path -LiteralPath $Item
    foreach ($ResolvedPath in $Resolved) {
        $FullPath = $ResolvedPath.Path
        if ($FullPath -notlike "$Root*") {
            throw "Refusing to checkpoint outside workspace: $FullPath"
        }
        $Relative = $FullPath.Substring($Root.Length).TrimStart("\", "/")
        if ($Relative -match $BlockedPattern) {
            throw "Refusing to checkpoint sensitive-looking path: $Relative"
        }
        $Destination = Join-Path $FilesRoot $Relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        Copy-Item -LiteralPath $FullPath -Destination $Destination -Force
        $FileInfo = Get-Item -LiteralPath $FullPath
        $Entries += [ordered]@{
            path = ($Relative -replace "\\", "/")
            size_bytes = $FileInfo.Length
            modified_at = $FileInfo.LastWriteTimeUtc.ToString("o")
        }
    }
}

$Manifest = [ordered]@{
    contract = "willind.file_checkpoint"
    version = "0.1.0"
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    label = $Label
    root = $Root
    checkpoint = $CheckpointRoot
    files = $Entries
    restore_command = "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\operations\files\restore-file-checkpoint.ps1 -Checkpoint `"$CheckpointRoot`""
}
$ManifestPath = Join-Path $CheckpointRoot "manifest.json"
$Manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8

[ordered]@{
    ok = $true
    checkpoint = $CheckpointRoot
    files = $Entries.Count
    manifest = $ManifestPath
} | ConvertTo-Json -Depth 5
