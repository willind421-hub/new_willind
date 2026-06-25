param(
  [ValidateSet("today", "week", "month", "manual", "current", "all")]
  [string]$Period = "today",

  [ValidateSet("subscriptions", "all")]
  [string]$View = "subscriptions",

  [ValidateSet("compact", "overview", "single")]
  [string]$UsageLayout = "compact",

  [double]$Interval = 60,

  [ValidateSet("clear", "ansi", "append")]
  [string]$RedrawMode = "clear",

  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$watchScript = "C:\new_willind\scripts\operations\usage\watch-ai-usage.ps1"
$command = @(
  "`$Host.UI.RawUI.WindowTitle = 'Willind AI Usage Watch'",
  "Set-Location 'C:\willind'",
  "& '$watchScript' -Period '$Period' -View '$View' -Layout '$UsageLayout' -Interval $Interval -RedrawMode '$RedrawMode'"
) -join "; "

if ($DryRun) {
  Write-Output $command
  exit 0
}

Start-Process -FilePath "powershell.exe" -ArgumentList @(
  "-NoExit",
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-Command", $command
) -WindowStyle Normal

