param(
  [string]$Root = "C:\willind",
  [string]$OutputDir = "C:\new_willind\runtime\cleanup",
  [int]$TextReadLimitBytes = 262144,
  [int]$TextProbeChars = 4096,
  [switch]$SkipTextProbe
)

$ErrorActionPreference = "Stop"

function Get-RelativePathSafe {
  param([string]$Base, [string]$Path)
  $baseFull = [System.IO.Path]::GetFullPath($Base).TrimEnd('\') + '\'
  $pathFull = [System.IO.Path]::GetFullPath($Path)
  if ($pathFull.StartsWith($baseFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    return $pathFull.Substring($baseFull.Length)
  }
  return $pathFull
}

function Test-TextExtension {
  param([string]$Ext, [string]$Name)
  $textExts = @(
    ".md",".txt",".json",".jsonl",".yaml",".yml",".toml",".ini",".cfg",".conf",
    ".py",".ps1",".bat",".cmd",".sh",".js",".jsx",".ts",".tsx",".css",".scss",
    ".html",".htm",".xml",".csv",".tsv",".sql",".env.example",".gitignore",
    ".dockerignore",".editorconfig",".lock",".log"
  )
  if ($textExts -contains $Ext.ToLowerInvariant()) { return $true }
  if ($Name -in @("CLAUDE.md","AGENTS.md","GEMINI.md","SKILL.md","README","LICENSE","VERSION")) { return $true }
  if ($Name -like "*.example") { return $true }
  return $false
}

function Classify-File {
  param([System.IO.FileInfo]$File, [string]$Root)

  $relative = Get-RelativePathSafe -Base $Root -Path $File.FullName
  $relLower = $relative.ToLowerInvariant()
  $segments = $relative -split '[\\/]'
  $top = if ($segments.Count -gt 0) { $segments[0] } else { "" }
  $topLower = $top.ToLowerInvariant()
  $nameLower = $File.Name.ToLowerInvariant()
  $ext = $File.Extension.ToLowerInvariant()

  $category = "uncategorized"
  $target = "review"
  $policy = "review_before_move"
  $risk = "medium"
  $reason = "No clear rule matched; manual review required"
  $readMode = "metadata_only"
  $contentHint = ""

  $sensitiveName = $nameLower -match '(secret|credential|client_secret|token|apikey|api_key|private|\.pem$|\.p12$|\.pfx$|\.key$|\.npmrc$|gcal_token|tokens\.json)'
  $heavyExt = $ext -in @(".gguf",".safetensors",".bin",".pt",".pth",".onnx",".ckpt",".model",".tar",".gz",".7z",".rar",".zip",".mp4",".mov",".mkv",".avi",".wav",".mp3",".flac")
  $generatedSegment = $relLower -match '(^|\\)(node_modules|\.venv|venv|__pycache__|\.pytest_cache|dist|build|coverage|\.next|\.vite|cache|tmp|temp)(\\|$)'

  if ($File.FullName -ieq (Join-Path $Root ".env")) {
    return $null
  }

  if ($topLower -eq ".secrets" -or $sensitiveName) {
    $category = "sensitive"
    $target = "keep_current_or_secrets"
    $policy = "never_read_content_never_auto_move"
    $risk = "critical"
    $reason = "Potential secret, token, or credential"
    $readMode = "metadata_only_sensitive"
  }
  elseif ($topLower -eq "models" -or $heavyExt) {
    $category = "heavy_model_or_binary"
    $target = if ($topLower -eq "models") { "models" } else { "runtime_or_outputs_by_owner" }
    $policy = "do_not_auto_move"
    $risk = "high"
    $reason = "Heavy model, binary, media, or archive candidate"
    $readMode = "metadata_only_heavy"
  }
  elseif ($topLower -eq "backup") {
    $category = "backup"
    $target = "backup"
    $policy = "do_not_move"
    $risk = "high"
    $reason = "Backup-only area"
  }
  elseif ($topLower -eq "projects") {
    $category = "project_internal"
    $target = "projects"
    $policy = "do_not_move_register_only"
    $risk = "high"
    $reason = "Project-internal file; moving can break builds or tests"
  }
  elseif ($topLower -in @("core","registry","reality","workflows","capabilities","outputs","references","archive","data","scripts","launchers")) {
    $category = "canonical_spine"
    $target = $top
    $policy = "keep"
    $risk = "low"
    $reason = "Already in canonical spine structure"
  }
  elseif ($topLower -eq "runtime") {
    $category = "runtime"
    $target = "runtime"
    $policy = "keep_or_cleanup_by_ttl"
    $risk = "low"
    $reason = "Runtime or cleanup output area"
  }
  elseif ($topLower -eq "config") {
    $category = "configuration"
    if ($relLower -match '^config\\willind\\modes\\') {
      $target = "workflows"
      $reason = "Willind mode configuration; workflow mapping candidate"
    }
    elseif ($relLower -match '^config\\willind\\policies\\') {
      $target = "core/policies"
      $reason = "Willind policy configuration"
    }
    elseif ($relLower -match '^config\\willind\\providers\\') {
      $target = "registry/providers"
      $reason = "Provider routing configuration"
    }
    elseif ($relLower -match '^config\\willind\\registries\\') {
      $target = "registry"
      $reason = "Registry configuration"
    }
    else {
      $target = "config"
      $reason = "Configuration file"
    }
    $policy = "keep_now_register"
    $risk = "medium"
  }
  elseif ($topLower -eq "docs") {
    $category = "documentation"
    $target = "docs"
    $policy = "keep"
    $risk = "low"
    $reason = "Documentation area"
  }
  elseif ($top -match '[^\x00-\x7F]') {
    $category = "reality_legacy"
    $target = "reality"
    $policy = "register_then_migrate_later"
    $risk = "high"
    $reason = "Reality/personal material; registry link required before migration"
  }
  elseif ($topLower -eq "data_collector") {
    $category = "absorbed_legacy_data_collector"
    $target = "data"
    $policy = "already_split_20260524"
    $risk = "high"
    $reason = "Legacy collector root was split into data/raw, data/processed, and owner projects on 2026-05-24"
  }
  elseif ($topLower -eq "intake") {
    $category = "capture_legacy"
    $target = "data/raw/capture"
    $policy = "candidate_after_reference_scan"
    $risk = "medium"
    $reason = "Collection or input data area"
  }
  elseif ($topLower -eq "research") {
    $category = "reference_or_research"
    $target = "references"
    $policy = "candidate_after_reference_scan"
    $risk = "medium"
    $reason = "Research material; references absorption candidate"
  }
  elseif ($topLower -eq "roles") {
    $category = "legacy_role_structure"
    $target = "capabilities/deprecated"
    $policy = "freeze_then_migrate"
    $risk = "high"
    $reason = "Legacy role structure; freeze and migrate to capabilities later"
  }
  elseif ($topLower -eq "skills" -or $topLower -eq ".superpowers") {
    $category = "legacy_skill_source"
    $target = "capabilities/imported"
    $policy = "register_then_migrate_later"
    $risk = "high"
    $reason = "Potential skill loading path; verify before imported isolation"
  }
  elseif ($topLower -eq "handoff") {
    $category = "handoff"
    $target = "runtime/handoff"
    $policy = "candidate_after_reference_scan"
    $risk = "medium"
    $reason = "Session or task handoff material"
  }
  elseif ($topLower -in @("logs","tmp","temp_2d","workspaces")) {
    $category = "runtime_legacy"
    $target = "runtime"
    $policy = "candidate_after_reference_scan"
    $risk = "medium"
    $reason = "Runtime trace or temporary workspace candidate"
  }
  elseif ($topLower -eq "artifacts") {
    $category = "artifact_legacy"
    $target = "outputs_or_runtime"
    $policy = "classify_by_content_then_move"
    $risk = "medium"
    $reason = "Could be final output or runtime artifact"
  }
  elseif ($topLower -eq "content") {
    $category = "content_legacy"
    $target = "reality/content"
    $policy = "register_then_migrate_later"
    $risk = "medium"
    $reason = "Content reality material candidate"
  }
  elseif ($topLower -in @("tests","watchdog")) {
    $category = "workspace_support"
    $target = "core_or_runtime"
    $policy = "candidate_after_reference_scan"
    $risk = "medium"
    $reason = "Workspace support file; reference scan required"
  }
  elseif ($topLower -in @(".claude",".browser-profiles",".obsidian","willind-mcp","oss")) {
    $category = "external_or_runtime_state"
    $target = "keep_current_register_only"
    $policy = "do_not_move"
    $risk = "high"
    $reason = "External tool, runtime, profile, or separate project state"
  }
  elseif ($segments.Count -eq 1 -and $ext -eq ".bat") {
    $category = "root_launcher"
    $target = "launchers"
    $policy = "candidate_after_reference_scan"
    $risk = "low"
    $reason = "Root launcher batch file"
  }
  elseif ($segments.Count -eq 1 -and $File.Name -in @("CLAUDE.md","ROLE.md","ROLE-dashboard.md",".gitignore",".env.example")) {
    $category = "root_control_file"
    $target = "core_or_root"
    $policy = "keep_now_reduce_later"
    $risk = "medium"
    $reason = "Agent or root control file"
  }

  if (-not $SkipTextProbe -and $readMode -eq "metadata_only" -and -not $generatedSegment -and -not $heavyExt -and -not $sensitiveName -and $File.Length -le $TextReadLimitBytes -and (Test-TextExtension -Ext $ext -Name $File.Name)) {
    try {
      $stream = [System.IO.StreamReader]::new($File.FullName, [System.Text.Encoding]::UTF8, $true)
      $buffer = New-Object char[] $TextProbeChars
      $count = $stream.Read($buffer, 0, $TextProbeChars)
      $stream.Close()
      $probe = -join $buffer[0..([Math]::Max(0, $count - 1))]
      $readMode = "text_probe_read"
      if ($probe -match '(?im)^---\s*\n.*name:\s*.*\n.*description:') { $contentHint = "skill_frontmatter" }
      elseif ($probe -match '(?i)capability hub|capability') { $contentHint = "capability_doc" }
      elseif ($probe -match '(?i)permission gate|permission') { $contentHint = "permission_doc" }
      elseif ($probe -match '(?i)morning brief|window director') { $contentHint = "second_floor_doc" }
      elseif ($probe -match '(?i)fastapi|uvicorn|router') { $contentHint = "backend_code" }
      elseif ($probe -match '(?i)react|tsx|vite') { $contentHint = "frontend_code" }
      elseif ($probe -match '(?i)TODO|FIXME') { $contentHint = "todo_or_work_item" }
      else { $contentHint = "text" }
    }
    catch {
      $readMode = "text_probe_failed"
      $contentHint = "read_error"
    }
  }
  elseif ($generatedSegment -and $readMode -eq "metadata_only") {
    $readMode = "metadata_only_generated"
  }

  [pscustomobject]@{
    current_path = $File.FullName
    relative_path = $relative
    name = $File.Name
    extension = $ext
    size_bytes = $File.Length
    top_folder = $top
    category = $category
    recommended_target = $target
    move_policy = $policy
    risk = $risk
    read_mode = $readMode
    content_hint = $contentHint
    reason = $reason
    last_write_time = $File.LastWriteTime.ToString("s")
  }
}

$rootResolved = (Resolve-Path -LiteralPath $Root).Path
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$csvPath = Join-Path $OutputDir "file-classification-$timestamp.csv"
$jsonPath = Join-Path $OutputDir "file-classification-summary-$timestamp.json"

$results = New-Object System.Collections.Generic.List[object]
$allFiles = Get-ChildItem -LiteralPath $rootResolved -Recurse -Force -File -ErrorAction SilentlyContinue
foreach ($file in $allFiles) {
  $row = Classify-File -File $file -Root $rootResolved
  if ($null -ne $row) {
    $results.Add($row)
  }
}

$results | Export-Csv -NoTypeInformation -Encoding UTF8 -LiteralPath $csvPath

$summary = [pscustomobject]@{
  generated_at = (Get-Date).ToString("s")
  root = $rootResolved
  excluded = @(".env")
  total_files_classified = $results.Count
  by_category = $results | Group-Object category | Sort-Object Count -Descending | ForEach-Object { [pscustomobject]@{ category=$_.Name; count=$_.Count } }
  by_policy = $results | Group-Object move_policy | Sort-Object Count -Descending | ForEach-Object { [pscustomobject]@{ policy=$_.Name; count=$_.Count } }
  by_risk = $results | Group-Object risk | Sort-Object Count -Descending | ForEach-Object { [pscustomobject]@{ risk=$_.Name; count=$_.Count } }
  by_read_mode = $results | Group-Object read_mode | Sort-Object Count -Descending | ForEach-Object { [pscustomobject]@{ read_mode=$_.Name; count=$_.Count } }
  outputs = [pscustomobject]@{
    csv = $csvPath
    summary_json = $jsonPath
  }
}

$summary | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $jsonPath

Write-Output "CSV=$csvPath"
Write-Output "SUMMARY=$jsonPath"
Write-Output "COUNT=$($results.Count)"

