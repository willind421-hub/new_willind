param(
  [ValidateSet("codex", "claude", "gemini", "opencode", "openhands")]
  [string]$Provider = "codex",

  [string]$Workdir = "C:\willind"
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Willind $Provider"
Set-Location $Workdir
python "C:\new_willind\scripts\operations\providers\willind_provider_entry.py" $Provider

