param(
  [string]$Root = "C:\willind",
  [string]$ClassificationCsv = "",
  [string]$OutputDir = "C:\new_willind\runtime\cleanup"
)

$ErrorActionPreference = "Stop"

function Get-LatestClassificationCsv {
  param([string]$Dir)
  Get-ChildItem -LiteralPath $Dir -Filter "file-classification-*.csv" -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 -ExpandProperty FullName
}

if (-not $ClassificationCsv) {
  $ClassificationCsv = Get-LatestClassificationCsv -Dir $OutputDir
}

if (-not (Test-Path -LiteralPath $ClassificationCsv)) {
  throw "Classification CSV not found: $ClassificationCsv"
}

$rootResolved = (Resolve-Path -LiteralPath $Root).Path.TrimEnd('\')
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$planPath = Join-Path $OutputDir "move-plan-$timestamp.csv"
$summaryPath = Join-Path $OutputDir "move-plan-summary-$timestamp.json"

$rows = Import-Csv -LiteralPath $ClassificationCsv

$groups = $rows |
  Group-Object top_folder,category,move_policy |
  Sort-Object Count -Descending

$plan = foreach ($group in $groups) {
  $sample = $group.Group | Select-Object -First 1
  $top = $sample.top_folder
  $category = $sample.category
  $policy = $sample.move_policy
  $target = $sample.recommended_target
  $action = "hold"
  $targetPath = ""
  $reason = "Hold until owner-specific migration"

  if ($top -eq "temp_2d") {
    $action = "move_now"
    $targetPath = "runtime/generated-workspaces/2026-05-23-root-cleanup/legacy-temp_2d"
    $reason = "Old image/vector temp output; reference scan found no live code dependency"
  }
  elseif ($top -eq "tmp") {
    $action = "hold"
    $targetPath = "runtime/temp"
    $reason = "Contains current logs and recent browser/QA captures; move later by TTL, not now"
  }
  elseif ($top -eq "handoff") {
    $action = "hold"
    $targetPath = "runtime/handoff"
    $reason = "Active coding/debate workflow may read C:\new_willind\handoff directly"
  }
  elseif ($top -eq "artifacts") {
    $action = "split_later"
    $targetPath = "outputs or runtime/generated-workspaces"
    $reason = "Contains UI mock artifacts; split final previews from experiments first"
  }
  elseif ($top -eq "workspaces") {
    $action = "hold"
    $targetPath = "runtime/generated-workspaces"
    $reason = "Workspace allocation may be referenced by coding mode"
  }
  elseif ($top -eq "research") {
    $action = "split_later"
    $targetPath = "references or outputs"
    $reason = "Research folder mixes screenshots, reports, and QA outputs"
  }
  elseif ($top -eq "launchers" -or $category -eq "root_launcher") {
    $action = "hold"
    $targetPath = "launchers"
    $reason = "Root launch habits may depend on these batch files; create aliases before moving"
  }
  elseif ($top -eq "scripts" -or $top -eq "tests" -or $top -eq "watchdog") {
    $action = "hold"
    $targetPath = "core or runtime"
    $reason = "Workspace support paths can be referenced by docs or commands"
  }
  elseif ($policy -in @("do_not_move","do_not_move_register_only","do_not_auto_move","never_read_content_never_auto_move","keep","keep_now_register","keep_now_reduce_later")) {
    $action = "do_not_move"
    $targetPath = $target
    $reason = "Policy forbids automatic move"
  }

  [pscustomobject]@{
    top_folder = $top
    category = $category
    move_policy = $policy
    file_count = $group.Count
    action = $action
    target_path = $targetPath
    reason = $reason
  }
}

$plan | Export-Csv -NoTypeInformation -Encoding UTF8 -LiteralPath $planPath

$summary = [pscustomobject]@{
  generated_at = (Get-Date).ToString("s")
  root = $rootResolved
  classification_csv = $ClassificationCsv
  plan_csv = $planPath
  action_counts = $plan | Group-Object action | Sort-Object Count -Descending | ForEach-Object { [pscustomobject]@{ action=$_.Name; count=$_.Count } }
  move_now = $plan | Where-Object { $_.action -eq "move_now" }
}

$summary | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $summaryPath

Write-Output "PLAN=$planPath"
Write-Output "SUMMARY=$summaryPath"
Write-Output "MOVE_NOW_COUNT=$(@($summary.move_now).Count)"


