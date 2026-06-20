# computer-use-cli

Local Windows-oriented computer-use toolkit for screenshots, desktop state observation, mouse/keyboard automation, UI Automation, vision helpers, safety policies, and a private ChatGPT MCP bridge.

The package is JSON-first: commands return machine-readable JSON, and the agent flow is meant to be `observe -> decide -> act -> observe again` rather than blind multi-step automation.

## What it can do

- Capture screenshots with `mss`, PyAutoGUI, or FFmpeg.
- Produce agent-ready desktop observations with screenshot, cursor, screen, window, and optional UI Automation state.
- Execute one structured JSON action through `cu act`.
- Run mouse actions: position, move, smooth move-between, click, double-click, right-click, drag, and split scroll.
- Run keyboard actions: type text, press a key, and hotkey chords.
- Inspect and interact with windows: list, active window, focus, and screenshot by title.
- Inspect and interact with UI Automation trees through pywinauto: tree, find, and click.
- Use OpenCV template matching and wait loops.
- Run OCR through pytesseract/Tesseract when native Tesseract is installed.
- Apply safety policies with presets, JSON files, action allowlists/denylists, window-title filters, coordinate regions, and action limits.
- Expose the desktop to ChatGPT as a private OAuth-protected MCP app with exactly two tools: `observe` and `act`.

## Requirements

- Windows.
- Python 3.11+.
- A normal logged-in, unlocked desktop session for real mouse/keyboard automation.
- Optional: FFmpeg in `PATH` for the FFmpeg screenshot backend.
- Optional: native Tesseract OCR in `PATH` for OCR.
- Optional for ChatGPT MCP: a configured OpenAI Secure MCP Tunnel client and tunnel environment file.

## Install

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .
```

Run the CLI directly from the virtual environment:

```powershell
.\.venv\Scripts\cu.exe --help
```

Or add the venv scripts directory to the current shell session:

```powershell
$env:Path = "$PWD\.venv\Scripts;$env:Path"
cu --help
```

For development and tests:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
```

## Core workflow

```powershell
cu observe --screenshot dev-only/generated/tmp/observe.png --json dev-only/generated/tmp/state.json --include-uia --uia-depth 1
cu actions
cu policy --preset guarded
cu act action.json --dry-run --policy-preset guarded
cu act action.json --policy-preset guarded
```

The intended safe loop is:

1. call `cu observe`;
2. inspect the screenshot and structured state;
3. call `cu act` with one JSON action;
4. call `cu observe` again and verify the result before deciding on another action.

## JSON actions

`cu act` accepts a single JSON object from a file, or `-` for stdin:

```powershell
cu act action.json --policy-preset guarded
Get-Content action.json | cu act - --dry-run --policy-preset guarded
```

Minimal click action:

```json
{
  "type": "click",
  "x": 500,
  "y": 500
}
```

Safe UI Automation dry-run action:

```json
{
  "type": "uiaClick",
  "controlType": "Button",
  "name": "Refresh"
}
```

Supported action types:

```text
click, doubleClick, drag, focusWindow, hotkey, matchImage, move, moveBetween,
observe, ocr, position, press, rightClick, screenshot, screenshotWindow, scroll,
sleep, type, uiaClick, uiaFind, uiaTree, waitImage
```

Useful aliases and action options:

- `move` accepts `speed` or `pixelsPerSecond`.
- `moveBetween` accepts `fromX`/`fromY` or `startX`/`startY`, plus `toX`/`toY`, `endX`/`endY`, or `x`/`y` for the destination.
- `moveBetween` can hold a mouse button during movement with `hold: true` and `button`.
- `drag` accepts `fromX`/`fromY` or `startX`/`startY`, plus `speed` or `pixelsPerSecond`.
- `scroll` accepts `clicks`, `amount`, `delta`, or `dy`.
- `scroll` can be split with `steps`, `scrollSteps`, or `wheelSteps` and delayed with `interval`, `scrollInterval`, or `wheelInterval`.
- `hotkey` accepts a list of keys or a string such as `ctrl+l`.

MCP and `cu act` deliberately execute one action at a time. Batches, sequences, and list-valued `steps` are rejected by the MCP layer.

## Safety policies

By default, direct `cu act` uses the permissive preset to preserve normal CLI behavior. For agent usage, prefer `guarded` or a custom JSON policy.

```powershell
cu policy --preset permissive
cu policy --preset guarded
cu policy --preset observe-only
cu policy --policy policies/guarded.example.json
```

Policy presets:

```text
permissive    Allows direct behavior.
guarded       Blocks common sensitive window titles, limits click/scroll/type/sleep,
              and requires dry-run for uiaClick.
observe-only  Allows read-only/vision actions and blocks mutating desktop actions.
```

Policy JSON files can extend a preset:

```json
{
  "name": "my-agent-policy",
  "base": "guarded",
  "allowedActions": ["observe", "position", "screenshot", "uiaTree", "uiaFind", "click", "move"],
  "deniedActions": [],
  "deniedWindowTitleSubstrings": ["password", "bank", "настройки", "парол"],
  "allowedWindowTitleSubstrings": ["Chrome", "Codex", "проводник"],
  "allowedRegions": [[0, 0, 2560, 1440]],
  "requireDryRunActions": ["uiaClick"],
  "maxClicks": 2,
  "maxScrollAbs": 10,
  "maxTypeLength": 240,
  "maxSleepSeconds": 5,
  "allowTextInput": true,
  "allowKeyboard": true,
  "allowMouse": true,
  "allowWindowFocus": true
}
```

A policy can also be selected for the current shell session:

```powershell
$env:COMPUTER_USE_POLICY = "guarded"
$env:COMPUTER_USE_POLICY = "$PWD\policies\guarded.example.json"
```

`--policy` overrides `--policy-preset`. `COMPUTER_USE_POLICY` is used when no explicit policy file is passed.

## Screen capture and observation

```powershell
cu screenshot --output screen.png
cu screenshot --backend mss --output screen.png
cu screenshot --backend pyautogui --output screen.png
cu screenshot --backend ffmpeg --output screen.png
cu screenshot --output region.png --x 100 --y 100 --width 1280 --height 720
cu monitors
cu screen-size --backend mss --monitor 0
```

`mss` is the default screenshot backend. Monitor `0` means the full virtual desktop for MSS commands.

Observation example:

```powershell
cu observe --screenshot observe.png --json observe.json
cu observe --screenshot observe.png --json observe.json --include-uia --uia-depth 2 --uia-title "Chrome"
cu observe --no-screenshot --include-windows
```

## Windows

```powershell
cu windows list
cu --pretty windows active
cu windows focus "Chrome"
cu windows screenshot "Chrome" --output chrome.png
cu screenshot-window "Chrome" --output chrome.png
```

## Mouse and keyboard

```powershell
cu position
cu move 500 500
cu move 500 500 --speed 900
cu move-between 100 100 800 500 --speed 700 --hold
cu click 500 500
cu double-click 500 500
cu right-click 500 500
cu drag 800 800 --from-x 500 --from-y 500 --speed 700
cu scroll -5 --steps 5 --interval 0.05
cu type "hello world"
cu press enter
cu hotkey ctrl l
```

All mutating desktop actions return JSON. Errors also return JSON and exit with code `1`:

```json
{"ok": false, "action": "hotkey", "error": "hotkey requires at least two keys", "type": "ValueError"}
```

## UI Automation

```powershell
cu --pretty uia tree --depth 2
cu --pretty uia tree --title "Chrome" --depth 3
cu uia find --title "Chrome" --name "Address" --limit 5
cu uia click --title "Chrome" --name "Refresh" --dry-run
cu uia click --title "Chrome" --automation-id "SomeAutomationId"
```

`--dry-run` returns the matched control without clicking it, which is useful for agent planning and policy checks. UI Automation coverage depends heavily on the target application.

## Image matching and OCR

```powershell
cu crop screen.png --output template.png --x 100 --y 100 --width 80 --height 40
cu match-image --image screen.png --template template.png --threshold 0.85
cu wait-image --template template.png --output wait-screen.png --timeout 10 --interval 0.5
cu ocr screen.png --language eng
```

OCR uses the `pytesseract` Python package, but still requires the native Tesseract executable. If Tesseract is missing, the command returns a JSON error instead of pretending OCR worked.

## Logging

Log JSON output for auditing/debugging:

```powershell
cu --log dev-only/generated/tmp/actions.jsonl screenshot --output screen.png
cu --log dev-only/generated/tmp/actions.jsonl position
```

Or set a default log path for the current shell:

```powershell
$env:COMPUTER_USE_LOG = "dev-only/generated/tmp/actions.jsonl"
cu position
```

## ChatGPT MCP

The package includes a private OAuth-protected MCP server for ChatGPT named `Computer Use MCP`.

It exposes exactly two tools:

- `observe` returns a primary-monitor screenshot directly to ChatGPT, plus structured cursor, screen, window, and optional UI Automation state.
- `act` executes exactly one structured action. It is annotated as destructive, and should be configured in ChatGPT to always require confirmation.

The MCP server has three immutable startup modes:

```text
observe-only  Read-only/vision actions only; blocks mutating desktop actions.
guarded       Recommended mode; guarded policy with sensitive-title blocks and action limits.
permissive    Unrestricted local desktop control; requires explicit launcher confirmation.
```

Changing mode requires stopping and restarting the launcher.

### MCP install

Install with test dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

Create `ops/windows/tunnel.env` from the example and fill it with the dedicated tunnel values:

```powershell
Copy-Item ops\windows\tunnel.env.example ops\windows\tunnel.env
notepad ops\windows\tunnel.env
```

Expected fields:

```text
COMPUTER_USE_MCP_TUNNEL_ID=tunnel_REPLACE_ME
COMPUTER_USE_MCP_OAUTH_RESOURCE_URL=https://.../v1/mcp/tunnel_REPLACE_ME
```

The launcher auto-creates `.env.local` with `COMPUTER_USE_MCP_OAUTH_OWNER_TOKEN` on first start. Both `.env.local` and `ops/windows/tunnel.env` are ignored by Git.

### MCP launcher

Start from PowerShell:

```powershell
.\ops\windows\start-computer-use-mcp.ps1
```

The launcher:

1. lets you choose `observe-only`, `guarded`, or `permissive`;
2. starts the local MCP server on loopback;
3. starts the dedicated Secure MCP Tunnel client;
4. writes process/runtime files under `ops/windows/runtime`;
5. writes logs under `ops/windows/logs`;
6. keeps both processes alive until Ctrl+C.

Useful helpers:

```powershell
.\ops\windows\check-computer-use-mcp.ps1
.\ops\windows\copy-oauth-password.ps1
.\ops\windows\stop-computer-use-mcp.ps1
```

OAuth client/token state persists by default under:

```text
%LOCALAPPDATA%\computer-use-cli\oauth-state
```

Override it with `COMPUTER_USE_MCP_STATE_DIR` in `.env.local` if needed.

### ChatGPT setup notes

- Use the hosted MCP resource URL from `ops/windows/tunnel.env` when creating the ChatGPT custom app.
- During authorization, use the owner password generated in `.env.local`; `copy-oauth-password.ps1` copies it to the clipboard.
- Set the `act` action control to always require confirmation.
- Refresh the app/tool schema in ChatGPT after changing MCP tool metadata.
- Keep Windows logged in and unlocked while using the MCP.
- Close or hide sensitive windows before calling `observe`; screenshots expose visible screen contents.

### MCP troubleshooting

If ChatGPT reports that the tunnel MCP server “does not implement OAuth”:

1. check `ops/windows/logs/server.stdout.log`;
2. run `ops/windows/check-computer-use-mcp.ps1`;
3. if `OAuthRegisteredClients = 0` and the logs show `/authorize ... 400 Bad Request`, ChatGPT is probably reusing a stale OAuth `client_id` after local OAuth state was lost;
4. restart the launcher once, then delete/recreate the draft custom app in ChatGPT so it performs dynamic registration again.

If the check script reports `unsupported_country_region_territory`, the current tunnel network route was rejected upstream. Restart the tunnel/launcher from an allowed route.

## Direct MCP server entry point

The package also installs `cu-mcp`:

```powershell
cu-mcp --mode guarded
```

For normal ChatGPT use, prefer the Windows launcher because it loads local env files, starts the tunnel, manages PIDs/logs, and keeps the selected mode immutable for the server process.

## Security model

This project is a local automation tool, not a sandbox.

- PyAutoGUI fail-safe remains enabled: move the mouse cursor to a screen corner to abort uncontrolled automation.
- Policies are guardrails for agent usage, not a security boundary against malicious local code.
- `observe` can reveal anything visible on the desktop.
- The MCP server exposes no generic shell or arbitrary command runner.
- The MCP `act` tool rejects batches and should be set to always require confirmation in ChatGPT.
- Prefer `guarded` for real use and `observe-only` for inspection-only sessions.

## Limitations

- Windows-first project; other operating systems are not the target.
- UI Automation support depends on the target application.
- OCR requires native Tesseract, not only the Python package.
- Template matching is pixel-based and can be sensitive to scaling, theme, animation, and DPI differences.
- FFmpeg capture requires `ffmpeg` in `PATH` and Windows `gdigrab` support.
- `act --dry-run` does not execute mutating mouse/keyboard/window actions; read-only actions may still run because they are safe.
- The MCP observes the primary monitor by default.

## Repository layout

```text
src/computer_use_cli/        Python package and CLI/MCP implementation
ops/windows/                 Windows MCP launcher, checker, stopper, and tunnel env example
policies/                    Example safety policies
docs/superpowers/specs/      Design notes/specs
tests/                       MCP, OAuth, policy, and integration tests
```

## Roadmap

### Done

- [x] Screenshot capture.
- [x] Mouse and keyboard actions.
- [x] Window list/focus/screenshot helpers.
- [x] JSON output and JSONL logs.
- [x] MSS/FFmpeg backend switch.
- [x] UI Automation tree/find/click.
- [x] Image matching, wait-image, crop, and OCR wrapper.
- [x] Agent-level `cu observe` and `cu act`.
- [x] Structured action schema.
- [x] Safety policy presets and JSON policy files.
- [x] Smooth move-between/hold and scroll step aliases.
- [x] Private OAuth-protected ChatGPT MCP wrapper.
- [x] Windows launcher/check/stop helpers for the MCP and tunnel.

### Possible next steps

- [ ] More structured action schema docs/examples.
- [ ] Richer UIA targeting helpers.
- [ ] Better cross-DPI/template-matching guidance.
- [ ] Optional cleanup command for old MCP runtime screenshots/logs.
