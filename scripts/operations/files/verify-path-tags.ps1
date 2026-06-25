param(
  [string]$Root = "C:\willind",
  [string]$TagFile = "C:\new_willind\registry\files\path-tags.yaml"
)

$ErrorActionPreference = "Stop"

function Read-ListBlock {
  param(
    [string[]]$Lines,
    [string]$BlockName
  )

  $items = New-Object System.Collections.Generic.List[string]
  $inBlock = $false
  $blockIndent = $null

  foreach ($line in $Lines) {
    if ($line -match "^(\s*)$([regex]::Escape($BlockName)):\s*$") {
      $inBlock = $true
      $blockIndent = $matches[1].Length
      continue
    }
    if (!$inBlock) {
      continue
    }
    if ($line -match "^(\s*)[A-Za-z0-9_.-]+:\s*" -and $matches[1].Length -le $blockIndent) {
      break
    }
    if ($line -match "^\s*-\s+(.+?)\s*$") {
      $items.Add($matches[1].Trim('"').Trim("'"))
    }
  }

  return @($items)
}

function Read-PathEntries {
  param([string[]]$Lines)

  $items = New-Object System.Collections.Generic.List[string]
  $inPaths = $false

  foreach ($line in $Lines) {
    if ($line -match "^paths:\s*$") {
      $inPaths = $true
      continue
    }
    if ($inPaths -and $line -match "^[A-Za-z0-9_.-]+:\s*" -and $line -notmatch "^paths:\s*$") {
      break
    }
    if ($inPaths -and $line -match "^\s*-\s+path:\s+(.+?)\s*$") {
      $items.Add($matches[1].Trim('"').Trim("'"))
    }
  }

  return @($items)
}

$rootPath = (Resolve-Path -LiteralPath $Root).Path
$tagPath = (Resolve-Path -LiteralPath $TagFile).Path
$lines = Get-Content -LiteralPath $tagPath -Encoding UTF8

$expectedDirs = Read-ListBlock -Lines $lines -BlockName "root_directories_expected"
$expectedFiles = Read-ListBlock -Lines $lines -BlockName "root_files_expected"
$pathEntries = Read-PathEntries -Lines $lines

$actualDirs = Get-ChildItem -LiteralPath $rootPath -Force -Directory |
  Select-Object -ExpandProperty Name |
  Sort-Object
$actualFiles = Get-ChildItem -LiteralPath $rootPath -Force -File |
  Select-Object -ExpandProperty Name |
  Sort-Object

$missingDirs = @($actualDirs | Where-Object { $expectedDirs -notcontains $_ })
$staleDirs = @($expectedDirs | Where-Object { $actualDirs -notcontains $_ })
$missingFiles = @($actualFiles | Where-Object { $expectedFiles -notcontains $_ })
$staleFiles = @($expectedFiles | Where-Object { $actualFiles -notcontains $_ })
$unregisteredExpectedDirs = @($expectedDirs | Where-Object { $pathEntries -notcontains $_ })
$unregisteredExpectedFiles = @($expectedFiles | Where-Object { $pathEntries -notcontains $_ })

$ok = $missingDirs.Count -eq 0 -and
  $staleDirs.Count -eq 0 -and
  $missingFiles.Count -eq 0 -and
  $staleFiles.Count -eq 0 -and
  $unregisteredExpectedDirs.Count -eq 0 -and
  $unregisteredExpectedFiles.Count -eq 0

$report = [pscustomobject]@{
  ok = $ok
  root = $rootPath
  tag_file = $tagPath
  counts = [pscustomobject]@{
    actual_dirs = $actualDirs.Count
    expected_dirs = $expectedDirs.Count
    actual_files = $actualFiles.Count
    expected_files = $expectedFiles.Count
    path_entries = $pathEntries.Count
  }
  mismatches = [pscustomobject]@{
    actual_dirs_missing_from_expected = $missingDirs
    expected_dirs_not_on_disk = $staleDirs
    actual_files_missing_from_expected = $missingFiles
    expected_files_not_on_disk = $staleFiles
    expected_dirs_without_path_entry = $unregisteredExpectedDirs
    expected_files_without_path_entry = $unregisteredExpectedFiles
  }
}

$report | ConvertTo-Json -Depth 8
if (!$ok) {
  exit 1
}

