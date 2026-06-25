param(
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = "C:\willind"
$entry = Join-Path $root "scripts\operations\providers\willind_provider_entry.py"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

if (-not (Test-Path -LiteralPath $entry)) {
  throw "Willind provider entry script not found: $entry"
}

$documentsRoot = [Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments)
$profileFromShell = $null
try {
  $profileFromShell = $PROFILE.CurrentUserAllHosts
} catch {
  $profileFromShell = $null
}

$profiles = @(
  $profileFromShell,
  (Join-Path $documentsRoot "PowerShell\Microsoft.PowerShell_profile.ps1"),
  (Join-Path $documentsRoot "WindowsPowerShell\Microsoft.PowerShell_profile.ps1")
) | Where-Object { $_ } | Select-Object -Unique

$shimDir = Join-Path $env:APPDATA "npm"
$watchShimProviders = @("codex", "claude", "gemini")

$block = @"
# >>> willind provider bootstrap entrypoints >>>
# Managed by C:\new_willind\scripts\operations\providers\install-provider-entrypoints.ps1
function Invoke-WillindProviderEntrypoint {
  param(
    [Parameter(Mandatory=`$true)][string]`$Provider,
    [Parameter(ValueFromRemainingArguments=`$true)][object[]]`$Rest
  )
  & python "C:\new_willind\scripts\operations\providers\willind_provider_entry.py" `$Provider @Rest
}
function Invoke-WillindProviderWatchPane {
  param(
    [Parameter(Mandatory=`$true)][string]`$Provider,
    [ValidateSet("bottom", "right")][string]`$Layout = "right"
  )
  `$launcherArgs = @("-Provider", `$Provider, "-Layout", `$Layout)
  if (`$env:WILLIND_PROVIDER_SPLIT_PANE_DRY_RUN -eq "1") {
    `$launcherArgs += "-DryRun"
  }
  & powershell -NoProfile -ExecutionPolicy Bypass -File "C:\new_willind\scripts\operations\usage\start-ai-terminal-with-usage-pane.ps1" @launcherArgs
}
function codex {
  Invoke-WillindProviderEntrypoint -Provider codex @args
}
function claude {
  Invoke-WillindProviderEntrypoint -Provider claude @args
}
function gemini {
  Invoke-WillindProviderEntrypoint -Provider gemini @args
}
function opencode {
  Invoke-WillindProviderEntrypoint -Provider opencode @args
}
function openhands {
  Invoke-WillindProviderEntrypoint -Provider openhands @args
}
function codex-watch {
  Invoke-WillindProviderWatchPane -Provider codex @args
}
function claude-watch {
  Invoke-WillindProviderWatchPane -Provider claude @args
}
function gemini-watch {
  Invoke-WillindProviderWatchPane -Provider gemini @args
}
function willind-codex {
  & python "C:\new_willind\scripts\operations\providers\willind_provider_entry.py" codex @args
}
function willind-claude {
  & python "C:\new_willind\scripts\operations\providers\willind_provider_entry.py" claude @args
}
function willind-provider-bootstrap {
  param(
    [Parameter(Mandatory=`$true)][string]`$Provider,
    [Parameter(ValueFromRemainingArguments=`$true)][string[]]`$Rest
  )
  & python "C:\new_willind\scripts\operations\providers\willind_provider_entry.py" `$Provider --willind-print-bootstrap-only @Rest
}
function codex-raw {
  `$env:WILLIND_PROVIDER_BOOTSTRAP_DISABLE = "1"
  try {
    `$cmd = Get-Command codex.ps1, codex.cmd, codex.exe -CommandType ExternalScript,Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not `$cmd) { throw "codex raw executable not found" }
    & `$cmd.Source @args
  } finally {
    Remove-Item Env:\WILLIND_PROVIDER_BOOTSTRAP_DISABLE -ErrorAction SilentlyContinue
  }
}
function claude-raw {
  `$env:WILLIND_PROVIDER_BOOTSTRAP_DISABLE = "1"
  try {
    `$cmd = Get-Command claude.exe, claude.cmd, claude.ps1 -CommandType ExternalScript,Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not `$cmd) { throw "claude raw executable not found" }
    & `$cmd.Source @args
  } finally {
    Remove-Item Env:\WILLIND_PROVIDER_BOOTSTRAP_DISABLE -ErrorAction SilentlyContinue
  }
}
# <<< willind provider bootstrap entrypoints <<<
"@

$begin = "# >>> willind provider bootstrap entrypoints >>>"
$end = "# <<< willind provider bootstrap entrypoints <<<"
$pattern = "(?s)\r?\n?# >>> willind provider bootstrap entrypoints >>>.*?# <<< willind provider bootstrap entrypoints <<<\r?\n?"

$written = @()
foreach ($profilePath in $profiles) {
  $dir = Split-Path -Parent $profilePath
  if (-not (Test-Path -LiteralPath $dir)) {
    if ($DryRun) {
      $written += [ordered]@{ profile = $profilePath; action = "would_create_parent" }
      continue
    }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
  }

  $existing = ""
  if (Test-Path -LiteralPath $profilePath) {
    $existing = Get-Content -LiteralPath $profilePath -Raw -Encoding UTF8
  }
  $updated = [regex]::Replace($existing, $pattern, "`r`n")
  $updated = $updated.TrimEnd() + "`r`n`r`n" + $block + "`r`n"

  if ($DryRun) {
    $written += [ordered]@{ profile = $profilePath; action = "would_update" }
    continue
  }

  if (Test-Path -LiteralPath $profilePath) {
    Copy-Item -LiteralPath $profilePath -Destination "$profilePath.bak.$timestamp" -Force
  }
  Set-Content -LiteralPath $profilePath -Value $updated -Encoding UTF8
  $written += [ordered]@{ profile = $profilePath; action = "updated"; backup = "$profilePath.bak.$timestamp" }
}

$shims = @()
if (-not (Test-Path -LiteralPath $shimDir)) {
  if ($DryRun) {
    $shims += [ordered]@{ path = $shimDir; action = "would_create_parent" }
  } else {
    New-Item -ItemType Directory -Force -Path $shimDir | Out-Null
  }
}

foreach ($provider in $watchShimProviders) {
  $shimPath = Join-Path $shimDir "$provider-watch.cmd"
  $cmdContent = @"
@echo off
setlocal
set WILLIND_WATCH_ARGS=-Provider $provider -Layout right
if "%WILLIND_PROVIDER_SPLIT_PANE_DRY_RUN%"=="1" set WILLIND_WATCH_ARGS=%WILLIND_WATCH_ARGS% -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\new_willind\scripts\operations\usage\start-ai-terminal-with-usage-pane.ps1" %WILLIND_WATCH_ARGS% %*
"@

  if ($DryRun) {
    $shims += [ordered]@{ path = $shimPath; action = "would_update" }
    continue
  }

  if (Test-Path -LiteralPath $shimPath) {
    Copy-Item -LiteralPath $shimPath -Destination "$shimPath.bak.$timestamp" -Force
  }
  Set-Content -LiteralPath $shimPath -Value $cmdContent -Encoding ASCII
  $shims += [ordered]@{ path = $shimPath; action = "updated" }
}

[pscustomobject]@{
  ok = $true
  dry_run = [bool]$DryRun
  profiles = $written
  shims = $shims
} | ConvertTo-Json -Depth 5

