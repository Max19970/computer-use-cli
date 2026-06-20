$ErrorActionPreference = "Stop"

$runtimeDir = Join-Path $PSScriptRoot "runtime"
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

Write-Host "Computer Use MCP processes stopped."
