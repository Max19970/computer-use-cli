# computer-use-cli

Small local Windows-oriented CLI for computer use:

- agent-level `observe` snapshots and structured `act` JSON actions;
- safety policy presets, JSON policy files, allowlists, denylists, and limits;
- screen screenshots with PyAutoGUI, MSS, or FFmpeg;
- monitor discovery;
- window list, focus, active window, and window screenshots;
- mouse position, move, click, double-click, right-click, drag, scroll;
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
position, move, click, doubleClick, rightClick, drag, scroll, type, press, hotkey,
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
cu click 500 500
cu double-click 500 500
cu right-click 500 500
cu drag 800 800 --duration 0.4
cu scroll -5
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

All commands return JSON:

```json
{"ok": true, "action": "position", "x": 100, "y": 200}
```

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
