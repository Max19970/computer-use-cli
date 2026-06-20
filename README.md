# computer-use-cli

Small local Windows-oriented CLI for computer use:

- agent-level `observe` snapshots and structured `act` JSON actions;
- safety policy presets, JSON policy files, allowlists, denylists, and limits;
- screen screenshots with PyAutoGUI, MSS, or FFmpeg;
- monitor discovery;
- window list, focus, active window, and window screenshots;
- mouse position, move, click, double-click, right-click, drag, smooth move-between/hold, scroll;
- keyboard text, key press, hotkey;
- UI Automation tree/search/click through pywinauto;
- template image matching and wait-image loops through OpenCV;
- optional OCR through pytesseract/Tesseract;
- JSONL action logging.

The CLI is JSON-first so an LLM/agent can call it in a loop:

1. `cu observe`;
2. inspect the screenshot and state JSON;
3. `cu act action.json --policy-preset guarded`;
4. observe again and verify.

## Install

```powershell
cd C:\Users\maxsh\Documents\Codex\computer-use-cli
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .
```

Then use:

```powershell
.\.venv\Scripts\cu.exe --help
```

or add `.venv\Scripts` to PATH for the current shell:

```powershell
$env:Path = "$PWD\.venv\Scripts;$env:Path"
cu --help
```

## Examples

### Agent loop

```powershell
cu observe --screenshot dev-only/generated/tmp/observe.png --json dev-only/generated/tmp/state.json --include-uia --uia-depth 1
cu actions
cu policy --preset guarded
cu act action.json --policy-preset guarded
cu act action.json --policy policies/guarded.example.json
cu act action.json --dry-run --policy-preset guarded
```

Example action file:

```json
{
  "type": "click",
  "x": 500,
  "y": 500
}
```

Safe dry-run UIA action:

```json
{
  "type": "uiaClick",
  "controlType": "Button",
  "name": "Refresh",
  "dryRun": true
}
```

Supported action types:

```text
position, move, moveBetween, click, doubleClick, rightClick, drag, scroll, type, press, hotkey,
sleep, screenshot, screenshotWindow, focusWindow, matchImage, waitImage, ocr,
uiaTree, uiaFind, uiaClick, observe
```

### Safety policies

By default, `cu act` uses the permissive preset to preserve direct CLI behavior. For agent usage, prefer `guarded` or a custom policy file.

```powershell
cu policy --preset permissive
cu policy --preset guarded
cu policy --preset observe-only
cu policy --policy policies/guarded.example.json
```

Policy presets:

```text
permissive   Allows existing direct behavior.
guarded      Blocks common sensitive window titles, limits click/scroll/type/sleep, and requires dry-run for uiaClick.
observe-only Allows read-only/vision actions and blocks mutating mouse/keyboard/window actions.
```

Custom policy example:

```json
{
  "name": "my-agent-policy",
  "base": "guarded",
  "allowedActions": ["observe", "position", "screenshot", "uiaTree", "uiaFind", "click", "move"],
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

You can also set a policy globally for a shell session:

```powershell
$env:COMPUTER_USE_POLICY = "guarded"
# or:
$env:COMPUTER_USE_POLICY = "C:\Users\maxsh\Documents\Codex\computer-use-cli\policies\guarded.example.json"
```

### Screen capture

```powershell
cu screenshot --output screen.png
cu screenshot --backend pyautogui --output screen.png
cu screenshot --backend ffmpeg --output screen.png
cu screenshot --output region.png --x 100 --y 100 --width 1280 --height 720
cu monitors
cu screen-size --backend mss --monitor 0
```

`mss` is the default screenshot backend. Monitor `0` is the full virtual desktop.

### Windows

```powershell
cu windows list
cu --pretty windows active
cu windows focus "Chrome"
cu windows screenshot "Chrome" --output chrome.png
cu screenshot-window "Chrome" --output chrome.png
```

### Mouse and keyboard

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

### UI Automation

```powershell
cu --pretty uia tree --depth 2
cu --pretty uia tree --title "Chrome" --depth 3
cu uia find --title "Chrome" --name "Address" --limit 5
cu uia click --title "Chrome" --name "Refresh" --dry-run
cu uia click --title "Chrome" --automation-id "SomeAutomationId"
```

`--dry-run` is useful for agent planning because it returns the matched control without clicking.

### Image matching

```powershell
cu crop screen.png --output template.png --x 100 --y 100 --width 80 --height 40
cu match-image --image screen.png --template template.png --threshold 0.85
cu wait-image --template template.png --output wait-screen.png --timeout 10 --interval 0.5
```

### OCR

```powershell
cu ocr screen.png --language eng
```

OCR uses `pytesseract`, but it still requires the native Tesseract OCR executable to be installed and available in PATH. If it is missing, the command returns a JSON error instead of pretending OCR worked.

### Logging

```powershell
cu --log dev-only/generated/tmp/actions.jsonl screenshot --output screen.png
cu --log dev-only/generated/tmp/actions.jsonl position
```

or with an environment variable:

```powershell
$env:COMPUTER_USE_LOG = "dev-only/generated/tmp/actions.jsonl"
cu position
```

For MCP/`cu act`, smooth cursor movement can be sent as one confirmed action:

```json
{
  "type": "moveBetween",
  "fromX": 100,
  "fromY": 100,
  "toX": 800,
  "toY": 500,
  "speed": 700,
  "hold": true,
  "button": "left"
}
```

`move` and `drag` also accept `speed`/`pixelsPerSecond`. `drag` also accepts `fromX`/`fromY` or `startX`/`startY`. `scroll` accepts `clicks`, plus aliases `amount`, `delta`, or `dy`, and can be split with `steps` and `interval`.

All commands return JSON:

```json
{"ok": true, "action": "position", "x": 100, "y": 200}
```

## ChatGPT MCP

The package includes a private, OAuth-protected MCP server for ChatGPT with exactly
two tools:

- `observe` returns the primary-monitor screenshot directly to ChatGPT together
  with structured cursor, window, screen, and optional UI Automation state.
- `act` executes exactly one structured action and is marked as destructive so it
  can be configured to always require confirmation in ChatGPT.

Install the MCP and test dependencies:

```powershell
cd C:\Users\maxsh\Documents\Codex\computer-use-cli
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

The Windows launcher is installed from `ops/windows`. It shows an interactive mode
menu each time it starts:

```text
observe-only
guarded
permissive
```

The mode is immutable until the launcher is stopped and restarted. The launcher
keeps the local server and OpenAI Secure MCP Tunnel alive and stops both when you
press Ctrl+C.

Configuration files and local state:

- `.env.local` contains the generated
  `COMPUTER_USE_MCP_OAUTH_OWNER_TOKEN` and is ignored by Git.
- `ops/windows/tunnel.env` contains the dedicated tunnel ID and exact hosted MCP
  resource URL and is ignored by Git.
- OAuth client/token state is stored in a stable local app-data directory by
  default: `%LOCALAPPDATA%\computer-use-cli\oauth-state`. You can override it
  with `COMPUTER_USE_MCP_STATE_DIR` in `.env.local`.
- The shared OpenAI tunnel runtime key remains in the existing private
  `.env.local` used by the other local MCP launchers.

After creating the ChatGPT custom app, open its Action control and set `act` to
always require confirmation. If the tool schema changes, use Refresh in ChatGPT
before testing.

If ChatGPT reports that the tunnel MCP server "does not implement OAuth", check
`ops/windows/logs/server.stdout.log`. When it contains `/authorize ... 400 Bad
Request` and the launcher/check output says `OAuthRegisteredClients = 0`, ChatGPT
is likely reusing a stale OAuth `client_id` after the local OAuth registry was
lost. Restart the launcher once, then delete/recreate the draft custom app in
ChatGPT so it performs dynamic registration again. The new stable state directory
prevents that registration from being lost on later restarts.

Security notes:

- Keep Windows logged in and unlocked while using the MCP.
- Close or hide sensitive content before calling `observe`.
- `guarded` is the recommended mode.
- PyAutoGUI's upper-left-corner fail-safe remains enabled.
- The MCP never exposes a generic shell or arbitrary CLI command runner.

Errors also return JSON and exit with code 1:

```json
{"ok": false, "action": "hotkey", "error": "hotkey requires at least two keys", "type": "ValueError"}
```

## Safety

PyAutoGUI fail-safe is enabled: move the mouse cursor to a screen corner to abort uncontrolled automation.

For agent usage, prefer:

```powershell
cu act action.json --dry-run --policy-preset guarded
cu act action.json --policy-preset guarded
```

before using permissive direct execution.

## Limitations

- UI Automation availability depends on the target application. Some apps expose a rich tree, some expose almost nothing useful.
- OCR requires native Tesseract OCR, not only the Python package.
- Template matching is pixel-based and can be sensitive to scaling, theme, animation, and DPI differences.
- FFmpeg capture requires `ffmpeg` in PATH and Windows `gdigrab` support.
- Policy checks are guardrails, not a security boundary against malicious local code.
- `act --dry-run` does not execute mutating mouse/keyboard/window actions; some read-only actions still run because they are safe.

## Roadmap

### Stage 1: MVP

- [x] Screenshot
- [x] Mouse actions
- [x] Keyboard actions
- [x] Basic window list/focus
- [x] JSON output

### Stage 2: good level

- [x] MSS/FFmpeg screenshot backend switch
- [x] Window screenshot by title
- [x] pywinauto UIA tree
- [x] Click control by name/automation id
- [x] Image matching / wait-image
- [x] OCR integration wrapper
- [x] Action logs

### Stage 3: agent-level observe/act

- [x] `cu observe --screenshot screen.png`
- [x] `cu act action.json`
- [x] Structured action schema
- [x] Safety policies / allowlists
- [ ] MCP wrapper
