$ErrorActionPreference = "Stop"

$logFile = Join-Path $PSScriptRoot "logs\tunnel-client.stdout.log"

function Get-Endpoint {
  param([Parameter(Mandatory)][string]$Uri)

  try {
    return Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
  } catch {
    throw "Cannot reach $Uri`: $($_.Exception.Message)"
  }
}

$serverResponse = Get-Endpoint -Uri "http://127.0.0.1:7678/healthz"
$server = $serverResponse.Content | ConvertFrom-Json
$tunnel = Get-Endpoint -Uri "http://127.0.0.1:8082/healthz"
$metrics = (Get-Endpoint -Uri "http://127.0.0.1:8082/metrics").Content
$match = [regex]::Match(
  $metrics,
  '(?m)^commands_poll_last_successful_timestamp_seconds(?:\{[^}]*\})?\s+([0-9.eE+-]+)$'
)
$lastPoll = if ($match.Success) {
  [double]::Parse(
    $match.Groups[1].Value,
    [Globalization.NumberStyles]::Float,
    [Globalization.CultureInfo]::InvariantCulture
  )
} else {
  0
}
$now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$pollAge = if ($lastPoll -gt 0) { $now - $lastPoll } else { [int64]::MaxValue }

if ($pollAge -gt 90) {
  $regionError = Get-Content -LiteralPath $logFile -Tail 300 -ErrorAction SilentlyContinue |
    Select-String -SimpleMatch "unsupported_country_region_territory" |
    Select-Object -Last 1
  if ($regionError) {
    throw "OpenAI rejected the current tunnel network route: unsupported_country_region_territory."
  }
  throw "Secure MCP Tunnel has not completed a successful control-plane poll in 90 seconds."
}

[pscustomobject]@{
  ComputerUseMcp = $serverResponse.StatusCode
  AccessMode = $server.mode
  TunnelProcess = $tunnel.StatusCode
  ControlPlanePollAgeSeconds = $pollAge
  Status = "ready"
} | Format-List
