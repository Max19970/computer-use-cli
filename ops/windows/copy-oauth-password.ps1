$ErrorActionPreference = "Stop"

$envFile = "C:\Users\maxsh\Documents\Codex\computer-use-cli\.env.local"
if (-not (Test-Path -LiteralPath $envFile)) {
  throw "Computer Use MCP environment file does not exist yet. Start the MCP once."
}

$line = Get-Content -LiteralPath $envFile |
  Where-Object { $_ -match '^\s*COMPUTER_USE_MCP_OAUTH_OWNER_TOKEN\s*=' } |
  Select-Object -Last 1
if (-not $line) {
  throw "COMPUTER_USE_MCP_OAUTH_OWNER_TOKEN was not found."
}

$token = ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
Set-Clipboard -Value $token
Write-Host "Computer Use MCP OAuth owner password copied to the clipboard."
