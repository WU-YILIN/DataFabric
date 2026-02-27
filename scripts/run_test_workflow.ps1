param(
  [switch]$NoFrontend,
  [switch]$NoBackend,
  [string]$BackendPython = "D:\project\DataFabric\genesis_backend\.venv\Scripts\python.exe"
)

$ErrorActionPreference = 'Continue'
$root = "D:\project\DataFabric"
$backend = Join-Path $root "genesis_backend"
$frontend = Join-Path $root "genesis_frontend"
$docsDir = Join-Path $root "docs"
$logsDir = Join-Path $root "logs\test-runs"
$reportPath = Join-Path $docsDir "TEST_FAILURES.md"

New-Item -ItemType Directory -Force -Path $docsDir | Out-Null
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$results = @()

function Run-Step {
  param(
    [string]$Name,
    [string]$WorkDir,
    [string]$Command,
    [string]$LogFile
  )

  Write-Host "[RUN] $Name"
  Push-Location $WorkDir
  try {
    $all = (& cmd /c $Command 2>&1 | Out-String)
    $exit = $LASTEXITCODE
    Set-Content -Path $LogFile -Value $all -Encoding UTF8
    return [pscustomobject]@{
      Name = $Name
      ExitCode = $exit
      LogFile = $LogFile
      Output = $all
      Success = ($exit -eq 0)
    }
  }
  finally {
    Pop-Location
  }
}

if (-not $NoBackend) {
  if (-not (Test-Path $BackendPython)) {
    $results += [pscustomobject]@{
      Name = "backend:pytest"
      ExitCode = 1
      LogFile = "(none)"
      Output = "Backend python not found: $BackendPython"
      Success = $false
    }
  } else {
    $backendLog = Join-Path $logsDir "${stamp}-backend-pytest.log"
    $cmd = '"' + $BackendPython + '" -m pytest -q'
    $results += Run-Step -Name "backend:pytest" -WorkDir $backend -Command $cmd -LogFile $backendLog
  }
}

if (-not $NoFrontend) {
  $lintLog = Join-Path $logsDir "${stamp}-frontend-lint.log"
  $buildLog = Join-Path $logsDir "${stamp}-frontend-build.log"
  $results += Run-Step -Name "frontend:lint" -WorkDir $frontend -Command "npm run lint" -LogFile $lintLog
  $results += Run-Step -Name "frontend:build" -WorkDir $frontend -Command "npm run build" -LogFile $buildLog
}

$failed = @($results | Where-Object { -not $_.Success })
$passed = @($results | Where-Object { $_.Success })

$summary = @()
$summary += "## Test Run - $ts"
$summary += ""
$summary += "- Passed: $($passed.Count)"
$summary += "- Failed: $($failed.Count)"
$summary += ""
$summary += "### Steps"
foreach ($r in $results) {
  $icon = if ($r.Success) { "[OK]" } else { "[FAIL]" }
  $summary += "- $icon **$($r.Name)** (exit=$($r.ExitCode))"
  $summary += "  - Log: $($r.LogFile)"
}
$summary += ""

if ($failed.Count -gt 0) {
  $summary += "### Failure Details"
  foreach ($f in $failed) {
    $summary += ""
    $summary += "#### $($f.Name)"
    $summary += "- ExitCode: $($f.ExitCode)"
    $summary += "- LogFile: $($f.LogFile)"
    $summary += ""
    $snippet = ($f.Output -split [Environment]::NewLine) | Select-Object -First 80
    $summary += '```text'
    $summary += ($snippet -join [Environment]::NewLine)
    $summary += '```'
  }
}

$summary += ""
$summary += "---"
$summary += ""

if (-not (Test-Path $reportPath)) {
  Set-Content -Path $reportPath -Value "# TEST_FAILURES`r`n`r`nAutomated failure records for debugging.`r`n`r`n" -Encoding UTF8
}
Add-Content -Path $reportPath -Value ($summary -join [Environment]::NewLine) -Encoding UTF8

Write-Host "Done. Report: $reportPath"
Write-Host "Failed: $($failed.Count)"

if ($failed.Count -gt 0) { exit 1 } else { exit 0 }
