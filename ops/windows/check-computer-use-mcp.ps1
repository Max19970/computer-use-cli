$ErrorActionPreference = "Stop"

$logFile = Join-Path $PSScriptRoot "logs\tunnel-client.stdout.log"
$runtimeDir = Join-Path $PSScriptRoot "runtime"
$tunnelHealthUrlFile = Join-Path $runtimeDir "tunnel-health.url"
$stateRoot = if ($env:LOCALAPPDATA) {
  Join-Path $env:LOCALAPPDATA "computer-use-cli"
} else {
  Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "dev-only\generated\computer-use-cli"
}
$defaultOAuthStateDir = Join-Path $stateRoot "oauth-state"
$oauthStateDir = if ($env:COMPUTER_USE_MCP_STATE_DIR) { $env:COMPUTER_USE_MCP_STATE_DIR } else { $defaultOAuthStateDir }
$maxPollWaitSeconds = 90

function Get-Endpoint {
  param([Parameter(Mandatory)][string]$Uri)

  try {
    return Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
  } catch {
    throw "Cannot reach $Uri`: $($_.Exception.Message)"
  }
}

function Get-TunnelHealthBaseUrl {
  if (-not (Test-Path -LiteralPath $tunnelHealthUrlFile)) {
    throw "Secure MCP Tunnel health URL file not found: $tunnelHealthUrlFile"
  }
  $url = (Get-Content -LiteralPath $tunnelHealthUrlFile -Raw -ErrorAction Stop).Trim()
  if (-not $url) {
    throw "Secure MCP Tunnel health URL file is empty: $tunnelHealthUrlFile"
  }
  return $url.TrimEnd("/")
}

function Get-LastSuccessfulPollTimestamp {
  param([Parameter(Mandatory)][string]$Metrics)

  $patterns = @(
    '(?m)^commands_poll_last_successful_timestamp_seconds(?:\{[^}]*\})?\s+([0-9.eE+-]+)$',
    '(?m)^control_plane_poll_last_successful_timestamp_seconds(?:\{[^}]*\})?\s+([0-9.eE+-]+)$',
    '(?m)^poll_last_successful_timestamp_seconds(?:\{[^}]*\})?\s+([0-9.eE+-]+)$'
  )

  foreach ($pattern in $patterns) {
    $match = [regex]::Match($Metrics, $pattern)
    if ($match.Success) {
      return [double]::Parse(
        $match.Groups[1].Value,
        [Globalization.NumberStyles]::Float,
        [Globalization.CultureInfo]::InvariantCulture
      )
    }
  }
  return 0
}

function Assert-NoKnownTunnelError {
  $tail = Get-Content -LiteralPath $logFile -Tail 300 -ErrorAction SilentlyContinue
  if (-not $tail) {
    return
  }

  $regionError = $tail |
    Select-String -SimpleMatch "unsupported_country_region_territory" |
    Select-Object -Last 1
  if ($regionError) {
    throw "OpenAI rejected the current tunnel network route: unsupported_country_region_territory."
  }

  $authError = $tail |
    Select-String -Pattern '"component":"controlplane".*("level":"ERROR"|"level":"WARN")' |
    Select-Object -Last 1
  if ($authError) {
    throw "Secure MCP Tunnel control-plane error: $($authError.Line)"
  }
}

function Get-OAuthClientCount {
  param([Parameter(Mandatory)][string]$StateDir)

  $clientsPath = Join-Path $StateDir "oauth-clients.json"
  if (-not (Test-Path -LiteralPath $clientsPath)) {
    return 0
  }
  try {
    $clients = Get-Content -LiteralPath $clientsPath -Raw -ErrorAction Stop | ConvertFrom-Json
    if ($null -eq $clients) {
      return 0
    }
    if ($clients -is [array]) {
      return $clients.Count
    }
    return 1
  } catch {
    return 0
  }
}

function Wait-SuccessfulControlPlanePoll {
  param([Parameter(Mandatory)][string]$TunnelHealthBaseUrl)

  $started = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  $lastPoll = 0.0
  $metrics = ""

  while ($true) {
    Assert-NoKnownTunnelError
    $metrics = (Get-Endpoint -Uri "$TunnelHealthBaseUrl/metrics").Content
    $lastPoll = Get-LastSuccessfulPollTimestamp -Metrics $metrics
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

    if ($lastPoll -gt 0) {
      $pollAge = $now - [int64]$lastPoll
      if ($pollAge -le $maxPollWaitSeconds) {
        return [pscustomobject]@{
          LastPoll = $lastPoll
          PollAge = $pollAge
          Waited = $now - $started
        }
      }
    }

    $elapsed = $now - $started
    if ($elapsed -ge $maxPollWaitSeconds) {
      throw "Secure MCP Tunnel has not completed a successful control-plane poll in $maxPollWaitSeconds seconds."
    }

    Start-Sleep -Seconds 2
  }
}

$serverResponse = Get-Endpoint -Uri "http://127.0.0.1:7678/healthz"
$server = $serverResponse.Content | ConvertFrom-Json
$oauthClientCount = Get-OAuthClientCount -StateDir $oauthStateDir
$tunnelHealthBaseUrl = Get-TunnelHealthBaseUrl
$tunnel = Get-Endpoint -Uri "$tunnelHealthBaseUrl/healthz"
Write-Host "Waiting for Secure MCP Tunnel control-plane poll, up to $maxPollWaitSeconds seconds..." -ForegroundColor DarkCyan
$poll = Wait-SuccessfulControlPlanePoll -TunnelHealthBaseUrl $tunnelHealthBaseUrl

[pscustomobject]@{
  ComputerUseMcp = $serverResponse.StatusCode
  AccessMode = $server.mode
  TunnelProcess = $tunnel.StatusCode
  TunnelHealthUrl = $tunnelHealthBaseUrl
  OAuthStateDir = $oauthStateDir
  OAuthRegisteredClients = $oauthClientCount
  OAuthAdvice = if ($oauthClientCount -eq 0) { "No registered OAuth client is persisted yet; if ChatGPT uses an old client_id, delete/recreate the draft app once." } else { "ok" }
  ControlPlanePollAgeSeconds = $poll.PollAge
  ControlPlanePollWaitSeconds = $poll.Waited
  Status = "ready"
} | Format-List
