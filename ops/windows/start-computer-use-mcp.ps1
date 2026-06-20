$ErrorActionPreference = "Stop"

$projectDir = "C:\Users\maxsh\Documents\Codex\computer-use-cli"
$python = Join-Path $projectDir ".venv\Scripts\python.exe"
$projectEnv = Join-Path $projectDir ".env.local"
$openAiEnv = "C:\Users\maxsh\Documents\Codex\2026-06-19\comfyui-1-control-id-api-comfyui\.env.local"
$tunnelEnv = Join-Path $PSScriptRoot "tunnel.env"
$tunnelClient = "C:\Users\maxsh\Documents\Codex\tools\openai-tunnel-client\tunnel-client.exe"
$runtimeDir = Join-Path $PSScriptRoot "runtime"
$logDir = Join-Path $PSScriptRoot "logs"
$stateRoot = if ($env:LOCALAPPDATA) {
  Join-Path $env:LOCALAPPDATA "computer-use-cli"
} else {
  Join-Path $projectDir "dev-only\generated\computer-use-cli"
}
$defaultOAuthStateDir = Join-Path $stateRoot "oauth-state"
$legacyOAuthStateDir = Join-Path $runtimeDir "oauth-state"
$profilePath = Join-Path $runtimeDir "computer-use-mcp.yaml"
$serverPidFile = Join-Path $runtimeDir "server.pid"
$serverLauncherPidFile = Join-Path $runtimeDir "server-launcher.pid"
$tunnelPidFile = Join-Path $runtimeDir "tunnel-client.pid"
$tunnelHealthUrlFile = Join-Path $runtimeDir "tunnel-health.url"

function Import-EnvFile {
  param([Parameter(Mandatory)][string]$Path)

  if (-not (Test-Path -LiteralPath $Path)) {
    throw "Environment file not found: $Path"
  }
  foreach ($line in Get-Content -LiteralPath $Path) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#")) {
      continue
    }
    $separator = $trimmed.IndexOf("=")
    if ($separator -lt 1) {
      continue
    }
    $name = $trimmed.Substring(0, $separator).Trim()
    $value = $trimmed.Substring($separator + 1).Trim()
    if (
      ($value.StartsWith('"') -and $value.EndsWith('"')) -or
      ($value.StartsWith("'") -and $value.EndsWith("'"))
    ) {
      $value = $value.Substring(1, $value.Length - 2)
    }
    [Environment]::SetEnvironmentVariable($name, $value, "Process")
  }
}

function New-OwnerToken {
  $bytes = [byte[]]::new(32)
  [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
  return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Initialize-ProjectEnv {
  $needsToken = $true
  if (Test-Path -LiteralPath $projectEnv) {
    $needsToken = -not (
      Get-Content -LiteralPath $projectEnv |
        Select-String -Pattern '^\s*COMPUTER_USE_MCP_OAUTH_OWNER_TOKEN\s*=' -Quiet
    )
  }
  if (-not $needsToken) {
    return $false
  }

  $token = New-OwnerToken
  $lines = @(
    "COMPUTER_USE_MCP_OAUTH_OWNER_TOKEN=$token",
    "COMPUTER_USE_MCP_HOST=127.0.0.1",
    "COMPUTER_USE_MCP_PORT=7678",
    "COMPUTER_USE_MCP_PUBLIC_BASE_URL=http://127.0.0.1:7678"
  )
  if (Test-Path -LiteralPath $projectEnv) {
    Add-Content -LiteralPath $projectEnv -Value $lines -Encoding utf8
  } else {
    Set-Content -LiteralPath $projectEnv -Value $lines -Encoding utf8
  }
  return $true
}

function Select-AccessMode {
  Write-Host ""
  Write-Host "Computer Use MCP access mode" -ForegroundColor Cyan
  Write-Host "  1. observe-only  - screenshots/UIA only; no desktop mutations"
  Write-Host "  2. guarded       - limited mouse/keyboard with sensitive-window blocks"
  Write-Host "  3. permissive    - full CLI access; use with extreme care"
  while ($true) {
    $choice = Read-Host "Select mode [1-3]"
    switch ($choice) {
      "1" { return "observe-only" }
      "2" { return "guarded" }
      "3" {
        $confirmation = Read-Host "Type PERMISSIVE to confirm unrestricted mode"
        if ($confirmation -ceq "PERMISSIVE") {
          return "permissive"
        }
        Write-Host "Permissive mode was not confirmed." -ForegroundColor Yellow
      }
      default { Write-Host "Enter 1, 2, or 3." -ForegroundColor Yellow }
    }
  }
}

function Test-Endpoint {
  param([Parameter(Mandatory)][string]$Uri)

  try {
    return (Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2).StatusCode -eq 200
  } catch {
    return $false
  }
}

function Wait-Endpoint {
  param(
    [Parameter(Mandatory)][string]$Uri,
    [Parameter(Mandatory)][string]$Name
  )

  foreach ($attempt in 1..40) {
    if (Test-Endpoint -Uri $Uri) {
      return
    }
    Start-Sleep -Milliseconds 500
  }
  throw "$Name did not become ready: $Uri"
}

function Stop-SavedProcess {
  param([Parameter(Mandatory)][string]$PidFile)

  if (-not (Test-Path -LiteralPath $PidFile)) {
    return
  }
  $savedPid = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue
  if ($savedPid) {
    Stop-Process -Id $savedPid -Force -ErrorAction SilentlyContinue
  }
  Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

function Get-SavedProcess {
  param([Parameter(Mandatory)][string]$PidFile)

  if (-not (Test-Path -LiteralPath $PidFile)) {
    return $null
  }
  $savedPid = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue
  if (-not $savedPid) {
    return $null
  }
  return Get-Process -Id $savedPid -ErrorAction SilentlyContinue
}

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

  $expectedFullPath = [IO.Path]::GetFullPath($ExpectedPath)
  $stoppedAny = $false
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
      $stoppedAny = $true
      continue
    }

    $identity = if ($actualPath) {
      "$($process.ProcessName) PID $ownerPid at $actualPath"
    } else {
      "$($process.ProcessName) PID $ownerPid"
    }
    throw "$Name port $Port is already in use by $identity. Stop that process or change the configured port."
  }

  if ($stoppedAny) {
    foreach ($attempt in 1..20) {
      $remaining = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
      if (-not $remaining) {
        return
      }
      Start-Sleep -Milliseconds 250
    }
    throw "$Name port $Port did not become free after stopping stale listener."
  }
}

function Stop-ProfileProcess {
  param(
    [Parameter(Mandatory)][string]$ExecutablePath,
    [Parameter(Mandatory)][string]$ProfilePath,
    [Parameter(Mandatory)][string]$Name
  )

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

function Wait-HealthUrlFile {
  param(
    [Parameter(Mandatory)][string]$Path,
    [Parameter(Mandatory)][string]$Name
  )

  foreach ($attempt in 1..40) {
    if (Test-Path -LiteralPath $Path) {
      $url = (Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue).Trim()
      if ($url) {
        return $url.TrimEnd("/")
      }
    }
    Start-Sleep -Milliseconds 500
  }
  throw "$Name did not write health URL file: $Path"
}

function Show-LogTail {
  param(
    [Parameter(Mandatory)][string]$Path,
    [int]$Tail = 40
  )

  if (-not (Test-Path -LiteralPath $Path)) {
    return
  }
  Write-Host ""
  Write-Host "Last $Tail lines of $Path`:" -ForegroundColor DarkYellow
  Get-Content -LiteralPath $Path -Tail $Tail -ErrorAction SilentlyContinue
}

function Copy-LegacyOAuthStateIfNeeded {
  param(
    [Parameter(Mandatory)][string]$LegacyStateDir,
    [Parameter(Mandatory)][string]$StateDir
  )

  $legacyClients = Join-Path $LegacyStateDir "oauth-clients.json"
  $currentClients = Join-Path $StateDir "oauth-clients.json"
  if ((Test-Path -LiteralPath $legacyClients) -and -not (Test-Path -LiteralPath $currentClients)) {
    Write-Host "Migrating OAuth client registry to stable state directory." -ForegroundColor Cyan
    $legacyFiles = Get-ChildItem -Path (Join-Path $LegacyStateDir "oauth-*.json") -File -ErrorAction SilentlyContinue
    foreach ($file in $legacyFiles) {
      Copy-Item -LiteralPath $file.FullName -Destination $StateDir -Force -ErrorAction SilentlyContinue
    }
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
    Write-Host "Could not read OAuth client registry: $clientsPath" -ForegroundColor Yellow
    return 0
  }
}

New-Item -ItemType Directory -Force -Path $runtimeDir, $logDir, $defaultOAuthStateDir | Out-Null

$createdOwnerToken = Initialize-ProjectEnv
Import-EnvFile -Path $projectEnv
Import-EnvFile -Path $openAiEnv
Import-EnvFile -Path $tunnelEnv

if (-not (Test-Path -LiteralPath $python)) {
  throw "Python virtual environment is missing: $python"
}
if (-not (Test-Path -LiteralPath $tunnelClient)) {
  throw "OpenAI tunnel client is missing: $tunnelClient"
}
if (-not $env:OPENAI_MCP_TUNNEL_API_KEY) {
  throw "OPENAI_MCP_TUNNEL_API_KEY is missing."
}
if ($env:COMPUTER_USE_MCP_TUNNEL_ID -notmatch '^tunnel_[A-Za-z0-9]+$') {
  throw "COMPUTER_USE_MCP_TUNNEL_ID is missing or invalid."
}
if (-not $env:COMPUTER_USE_MCP_OAUTH_RESOURCE_URL) {
  throw "COMPUTER_USE_MCP_OAUTH_RESOURCE_URL is missing."
}
if ($env:COMPUTER_USE_MCP_OAUTH_OWNER_TOKEN.Length -lt 24) {
  throw "COMPUTER_USE_MCP_OAUTH_OWNER_TOKEN is invalid."
}

$mode = Select-AccessMode
if (-not $env:COMPUTER_USE_MCP_STATE_DIR) {
  $env:COMPUTER_USE_MCP_STATE_DIR = $defaultOAuthStateDir
}
New-Item -ItemType Directory -Force -Path $env:COMPUTER_USE_MCP_STATE_DIR | Out-Null
Copy-LegacyOAuthStateIfNeeded -LegacyStateDir $legacyOAuthStateDir -StateDir $env:COMPUTER_USE_MCP_STATE_DIR
$oauthClientCount = Get-OAuthClientCount -StateDir $env:COMPUTER_USE_MCP_STATE_DIR
$env:COMPUTER_USE_MCP_RUNTIME_DIR = Join-Path $runtimeDir "screens"
$env:HARPOON_ALLOW_PLAINTEXT_HTTP = "true"

Write-Host ""
Write-Host "Selected immutable mode: $mode" -ForegroundColor Green
Write-Host "OAuth state directory: $($env:COMPUTER_USE_MCP_STATE_DIR)" -ForegroundColor DarkCyan
if ($oauthClientCount -eq 0) {
  Write-Host "OAuth client registry is empty. If ChatGPT reuses an old client_id, delete/recreate the draft app once after this restart." -ForegroundColor Yellow
}
Write-Host "Close or hide passwords, banking apps, and other sensitive information." -ForegroundColor Yellow
Write-Host "The Windows desktop must remain logged in and unlocked." -ForegroundColor Yellow

if ($createdOwnerToken) {
  Set-Clipboard -Value $env:COMPUTER_USE_MCP_OAUTH_OWNER_TOKEN
  Write-Host "A new OAuth owner password was created and copied to the clipboard." -ForegroundColor Cyan
}

Stop-SavedProcess -PidFile $tunnelPidFile
Stop-SavedProcess -PidFile $serverPidFile
Stop-SavedProcess -PidFile $serverLauncherPidFile
Stop-ProfileProcess -ExecutablePath $tunnelClient -ProfilePath $profilePath -Name "Secure MCP Tunnel"
Stop-OwnedPortListener -Port 7678 -ExpectedPath $python -Name "Computer Use MCP server"
Remove-Item -LiteralPath $tunnelHealthUrlFile -Force -ErrorAction SilentlyContinue

@"
config_version: 1
control_plane:
  base_url: "https://api.openai.com"
  tunnel_id: "$($env:COMPUTER_USE_MCP_TUNNEL_ID)"
  api_key: "env:OPENAI_MCP_TUNNEL_API_KEY"
health:
  listen_addr: "127.0.0.1:0"
  url_file: "$($tunnelHealthUrlFile.Replace("\", "/"))"
admin_ui:
  open_browser: false
log:
  level: info
  format: json
mcp:
  server_urls:
    - channel: main
      url: "http://127.0.0.1:7678/mcp"
"@ | Set-Content -LiteralPath $profilePath -Encoding utf8

try {
  $serverProcess = Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "computer_use_cli.mcp_server", "--mode", $mode) `
    -WorkingDirectory $projectDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDir "server.stdout.log") `
    -RedirectStandardError (Join-Path $logDir "server.stderr.log") `
    -PassThru
  Set-Content -LiteralPath $serverLauncherPidFile -Value $serverProcess.Id
  Wait-Endpoint -Uri "http://127.0.0.1:7678/healthz" -Name "Computer Use MCP"
  $serverOwnerPid = Get-NetTCPConnection `
    -LocalPort 7678 `
    -State Listen `
    -ErrorAction Stop |
    Select-Object -First 1 -ExpandProperty OwningProcess
  Set-Content -LiteralPath $serverPidFile -Value $serverOwnerPid

  $tunnelProcess = Start-Process `
    -FilePath $tunnelClient `
    -ArgumentList @("run", "--profile-file", $profilePath) `
    -WorkingDirectory $PSScriptRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDir "tunnel-client.stdout.log") `
    -RedirectStandardError (Join-Path $logDir "tunnel-client.stderr.log") `
    -PassThru
  Set-Content -LiteralPath $tunnelPidFile -Value $tunnelProcess.Id
  $tunnelHealthBaseUrl = Wait-HealthUrlFile -Path $tunnelHealthUrlFile -Name "Secure MCP Tunnel"
  Wait-Endpoint -Uri "$tunnelHealthBaseUrl/healthz" -Name "Secure MCP Tunnel"

  & (Join-Path $PSScriptRoot "check-computer-use-mcp.ps1")
  Write-Host ""
  Write-Host "Computer Use MCP is running. Press Ctrl+C to stop it." -ForegroundColor Green
  Write-Host "OAuth owner password helper: copy-oauth-password.ps1"

  while ($true) {
    if (-not (Get-SavedProcess -PidFile $serverPidFile)) {
      Show-LogTail -Path (Join-Path $logDir "server.stderr.log")
      Show-LogTail -Path (Join-Path $logDir "server.stdout.log")
      throw "Computer Use MCP server exited unexpectedly."
    }
    if (-not (Get-SavedProcess -PidFile $tunnelPidFile)) {
      Show-LogTail -Path (Join-Path $logDir "tunnel-client.stderr.log")
      Show-LogTail -Path (Join-Path $logDir "tunnel-client.stdout.log")
      throw "Secure MCP Tunnel exited unexpectedly."
    }
    Start-Sleep -Seconds 2
  }
} finally {
  Stop-SavedProcess -PidFile $tunnelPidFile
  Stop-SavedProcess -PidFile $serverPidFile
  Stop-SavedProcess -PidFile $serverLauncherPidFile
  Write-Host "Computer Use MCP stopped." -ForegroundColor Yellow
}
