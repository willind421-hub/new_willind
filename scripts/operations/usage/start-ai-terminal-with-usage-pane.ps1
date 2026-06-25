param(
  [ValidateSet("codex", "claude", "gemini", "opencode", "openhands")]
  [string]$Provider = "codex",

  [string]$Workdir = "C:\willind",

  [ValidateSet("today", "week", "month", "manual", "current", "all")]
  [string]$Period = "today",

  [ValidateSet("subscriptions", "all")]
  [string]$View = "subscriptions",

  [ValidateSet("compact", "overview", "single")]
  [string]$UsageLayout = "compact",

  [ValidateSet("bottom", "right")]
  [string]$Layout = "bottom",

  [double]$WatcherSize = 0.28,

  [double]$Interval = 60,

  [ValidateSet("clear", "ansi", "append")]
  [string]$RedrawMode = "clear",

  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$wt = Get-Command wt.exe -ErrorAction SilentlyContinue
if (-not $wt) {
  throw "Windows Terminal(wt.exe)을 찾지 못했습니다. scripts\operations\usage\start-ai-usage-watch.ps1 로 별도 창 watcher를 사용하세요."
}

$providerEntry = "C:\new_willind\scripts\operations\providers\willind_provider_entry.py"
$providerPaneScript = "C:\new_willind\scripts\operations\providers\start-ai-provider-pane.ps1"
$watchScript = "C:\new_willind\scripts\operations\usage\watch-ai-usage.ps1"
$title = "Willind $Provider + Usage"

if (-not (Test-Path $providerEntry)) {
  throw "Provider entry를 찾지 못했습니다: $providerEntry"
}
if (-not (Test-Path $providerPaneScript)) {
  throw "Provider pane launcher를 찾지 못했습니다: $providerPaneScript"
}
if (-not (Test-Path $watchScript)) {
  throw "Usage watcher를 찾지 못했습니다: $watchScript"
}

$splitDirection = if ($Layout -eq "right") { "--horizontal" } else { "--vertical" }
$watcherSizeText = [string]::Format(
  [System.Globalization.CultureInfo]::InvariantCulture,
  "{0:0.##}",
  $WatcherSize
)

$argsList = @(
  "-w", "new",
  "new-tab",
  "--title", $title,
  "powershell.exe",
  "-NoExit",
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", $providerPaneScript,
  "-Provider", $Provider,
  "-Workdir", $Workdir,
  ";",
  "split-pane",
  $splitDirection,
  "--size", $watcherSizeText,
  "powershell.exe",
  "-NoExit",
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", $watchScript,
  "-Period", $Period,
  "-View", $View,
  "-Layout", $UsageLayout,
  "-Interval", "$Interval",
  "-RedrawMode", $RedrawMode
)

if ($DryRun) {
  Write-Output ("wt.exe " + ($argsList -join " "))
  exit 0
}

& $wt.Source @argsList

