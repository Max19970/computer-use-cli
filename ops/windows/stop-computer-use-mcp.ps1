$ErrorActionPreference = "Stop"

$projectDir = "C:\Users\maxsh\Documents\Codex\computer-use-cli"
$python = Join-Path $projectDir ".venv\Scripts\python.exe"
$tunnelClient = "C:\Users\maxsh\Documents\Codex\tools\openai-tunnel-client\tunnel-client.exe"
$runtimeDir = Join-Path $PSScriptRoot "runtime"
$profilePath = Join-Path $runtimeDir "computer-use-mcp.yaml"
$tunnelHealthUrlFile = Join-Path $runtimeDir "tunnel-health.url"

function Get-ProcessPathSafe {
  param([Parameter(Mandatory)][Diagnostics.Process]$Process)

  try {
    return $Process.MainModule.FileName
  } catch {
    return $null
  }
}

function Stop-OwnedPortListener {
  param(
    [Parameter(Mandatory)][int]$Port,
    [Parameter(Mandatory)][string]$ExpectedPath,
    [Parameter(Mandatory)][string]$Name
  )

  if (-not (Test-Path -LiteralPath $ExpectedPath)) {
    return
  }

  $expectedFullPath = [IO.Path]::GetFullPath($ExpectedPath)
  $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  foreach ($listener in $listeners) {
    $ownerPid = [int]$listener.OwningProcess
    if ($ownerPid -eq $PID) {
      continue
    }

    $process = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
    if (-not $process) {
      continue
    }

    $actualPath = Get-ProcessPathSafe -Process $process
    if ($actualPath -and ([IO.Path]::GetFullPath($actualPath) -ieq $expectedFullPath)) {
      Write-Host "Stopping stale $Name listener on port $Port (PID $ownerPid)." -ForegroundColor Yellow
      Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
    }
  }
}

function Stop-ProfileProcess {
  param(
    [Parameter(Mandatory)][string]$ExecutablePath,
    [Parameter(Mandatory)][string]$ProfilePath,
    [Parameter(Mandatory)][string]$Name
  )

  if (-not (Test-Path -LiteralPath $ExecutablePath)) {
    return
  }
  if (-not (Test-Path -LiteralPath $ProfilePath)) {
    return
  }

  $expectedFullPath = [IO.Path]::GetFullPath($ExecutablePath)
  $profileFullPath = [IO.Path]::GetFullPath($ProfilePath)
  $escapedProfilePath = [Management.Automation.WildcardPattern]::Escape($profileFullPath)
  $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
      $_.ExecutablePath -and
      ([IO.Path]::GetFullPath($_.ExecutablePath) -ieq $expectedFullPath) -and
      $_.CommandLine -and
      ($_.CommandLine -like "*$escapedProfilePath*")
    }

  foreach ($process in $processes) {
    if ([int]$process.ProcessId -eq $PID) {
      continue
    }
    Write-Host "Stopping stale $Name for this profile (PID $($process.ProcessId))." -ForegroundColor Yellow
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
  }
}

foreach ($name in @("tunnel-client.pid", "server.pid", "server-launcher.pid")) {
  $pidFile = Join-Path $runtimeDir $name
  if (-not (Test-Path -LiteralPath $pidFile)) {
    continue
  }
  $savedPid = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue
  if ($savedPid) {
    Stop-Process -Id $savedPid -Force -ErrorAction SilentlyContinue
  }
  Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

Stop-ProfileProcess -ExecutablePath $tunnelClient -ProfilePath $profilePath -Name "Secure MCP Tunnel"
Stop-OwnedPortListener -Port 7678 -ExpectedPath $python -Name "Computer Use MCP server"
Remove-Item -LiteralPath $tunnelHealthUrlFile -Force -ErrorAction SilentlyContinue

Write-Host "Computer Use MCP processes stopped."
