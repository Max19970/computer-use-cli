from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from computer_use_cli import actions, automation, capture, observe as observe_module, policy as safety_policy, uia, vision, windows
from computer_use_cli.output import fail, ok, set_log_path, set_pretty

app = typer.Typer(
    name="cu",
    help="Local computer-use CLI: screenshots, vision, mouse, keyboard, windows, and UIA.",
    no_args_is_help=True,
)
window_app = typer.Typer(help="Window discovery, focus, and window screenshots.", no_args_is_help=True)
uia_app = typer.Typer(help="Windows UI Automation commands.", no_args_is_help=True)
app.add_typer(window_app, name="windows")
app.add_typer(uia_app, name="uia")


def _guarded(action: str, fn, *args, **kwargs) -> None:
    try:
        data = fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - CLI must return JSON errors for agent callers.
        fail(action, str(exc), type=exc.__class__.__name__)
    else:
        ok(action, **data)


def _backend(value: str) -> capture.Backend:
    if value not in {"pyautogui", "mss", "ffmpeg"}:
        raise ValueError("backend must be one of: pyautogui, mss, ffmpeg")
    return value  # type: ignore[return-value]


def _uia_backend(value: str) -> uia.Backend:
    if value not in {"uia", "win32"}:
        raise ValueError("backend must be one of: uia, win32")
    return value  # type: ignore[return-value]


def _region_or_fail(
    action: str,
    x: int | None,
    y: int | None,
    width: int | None,
    height: int | None,
) -> capture.Region | None:
    try:
        return capture.normalize_region(x, y, width, height)
    except ValueError as exc:
        fail(action, str(exc), type=exc.__class__.__name__)
        return None


@app.callback()
def callback(
    pretty: Annotated[bool, typer.Option("--pretty", help="Pretty-print JSON output.")] = False,
    log: Annotated[Path | None, typer.Option("--log", help="Append emitted JSON payloads to this JSONL file.")] = None,
) -> None:
    set_pretty(pretty)
    set_log_path(log)


@app.command()
def observe(
    screenshot: Annotated[Path, typer.Option("--screenshot", "-s", help="Screenshot path to write.")] = Path("observe-screen.png"),
    json_output: Annotated[Path | None, typer.Option("--json", help="Optional state JSON file to write.")] = None,
    backend: Annotated[str, typer.Option("--backend", help="pyautogui, mss, or ffmpeg.")] = "mss",
    monitor: Annotated[int, typer.Option("--monitor", help="MSS monitor index. 0 is the full virtual desktop.")] = 0,
    include_screenshot: Annotated[bool, typer.Option("--include-screenshot/--no-screenshot", help="Capture a screenshot.")] = True,
    include_windows: Annotated[bool, typer.Option("--include-windows/--no-windows", help="Include top-level windows.")] = True,
    include_minimized: Annotated[bool, typer.Option("--include-minimized", help="Include minimized windows in window list.")] = False,
    include_uia: Annotated[bool, typer.Option("--include-uia", help="Include UI Automation tree.")] = False,
    uia_depth: Annotated[int, typer.Option("--uia-depth", help="UIA tree depth.")] = 2,
    uia_title: Annotated[str | None, typer.Option("--uia-title", help="UIA window title substring. Defaults to active window.")] = None,
    uia_backend: Annotated[str, typer.Option("--uia-backend", help="uia or win32.")] = "uia",
) -> None:
    """Collect a single agent-friendly snapshot: cursor, screen, windows, screenshot, optional UIA."""
    try:
        selected_backend = _backend(backend)
        selected_uia_backend = _uia_backend(uia_backend)
    except ValueError as exc:
        fail("observe", str(exc), type=exc.__class__.__name__)
    def run() -> dict[str, object]:
        state = observe_module.observe_state(
            screenshot,
            selected_backend,
            monitor,
            include_screenshot,
            include_windows,
            include_uia,
            uia_depth,
            uia_title,
            selected_uia_backend,
            include_minimized,
        )
        if json_output is not None:
            json_output.parent.mkdir(parents=True, exist_ok=True)
            json_output.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            state["stateJson"] = str(json_output.resolve())
        return state

    _guarded("observe", run)


@app.command()
def act(
    action_file: Annotated[Path, typer.Argument(help="JSON action file path. Use '-' to read stdin.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Return what would happen for mutating actions.")] = False,
    policy_preset: Annotated[str, typer.Option("--policy-preset", help="Safety preset: permissive, guarded, observe-only.")] = "permissive",
    policy_file: Annotated[Path | None, typer.Option("--policy", help="Safety policy JSON file. Overrides --policy-preset.")] = None,
) -> None:
    """Execute one structured JSON action, optionally guarded by a safety policy."""
    def run() -> dict[str, object]:
        action = actions.load_action(action_file)
        kind = action.get("type") or action.get("action")
        policy = safety_policy.resolve_policy(policy_preset, policy_file)
        result = actions.run_action(action, dry_run=dry_run, policy=policy)
        return {"type": kind, "dryRun": dry_run, "policy": policy.to_dict(), "result": result}

    _guarded("act", run)


@app.command("actions")
def list_actions() -> None:
    """List supported structured action types for `cu act`."""
    _guarded("actions", lambda: {"supportedActions": actions.supported_actions()})


@app.command("policy")
def policy_command(
    preset: Annotated[str, typer.Option("--preset", help="Policy preset: permissive, guarded, observe-only.")] = "guarded",
    policy_file: Annotated[Path | None, typer.Option("--policy", help="Policy JSON file to load instead of a preset.")] = None,
) -> None:
    """Print a resolved safety policy."""
    _guarded("policy", lambda: {"policy": safety_policy.resolve_policy(preset, policy_file).to_dict()})


@app.command()
def screenshot(
    output: Annotated[Path, typer.Option("--output", "-o", help="PNG path to write.")] = Path("screen.png"),
    backend: Annotated[str, typer.Option("--backend", help="pyautogui, mss, or ffmpeg.")] = "mss",
    monitor: Annotated[int, typer.Option("--monitor", help="MSS monitor index. 0 is the full virtual desktop.")] = 0,
    x: Annotated[int | None, typer.Option(help="Region left coordinate.")] = None,
    y: Annotated[int | None, typer.Option(help="Region top coordinate.")] = None,
    width: Annotated[int | None, typer.Option(help="Region width.")] = None,
    height: Annotated[int | None, typer.Option(help="Region height.")] = None,
) -> None:
    """Capture the screen or a rectangular region."""
    region = _region_or_fail("screenshot", x, y, width, height)
    try:
        selected_backend = _backend(backend)
    except ValueError as exc:
        fail("screenshot", str(exc), type=exc.__class__.__name__)
    _guarded("screenshot", capture.capture_screen, output, region, selected_backend, monitor)


@app.command("screenshot-window")
def screenshot_window(
    title: Annotated[str, typer.Argument(help="Case-insensitive window title substring.")],
    output: Annotated[Path, typer.Option("--output", "-o", help="PNG path to write.")] = Path("window.png"),
    backend: Annotated[str, typer.Option("--backend", help="pyautogui, mss, or ffmpeg.")] = "mss",
) -> None:
    """Capture the first non-minimized window matching a title substring."""
    try:
        selected_backend = _backend(backend)
    except ValueError as exc:
        fail("screenshot-window", str(exc), type=exc.__class__.__name__)
    _guarded("screenshot-window", windows.screenshot_window, title, output, selected_backend)


@app.command("screen-size")
def screen_size(
    backend: Annotated[str, typer.Option("--backend", help="pyautogui or mss.")] = "pyautogui",
    monitor: Annotated[int, typer.Option("--monitor", help="MSS monitor index. 0 is the full virtual desktop.")] = 0,
) -> None:
    """Return screen size for PyAutoGUI or an MSS monitor."""
    try:
        selected_backend = _backend(backend)
    except ValueError as exc:
        fail("screen-size", str(exc), type=exc.__class__.__name__)
    _guarded("screen-size", capture.screen_size, selected_backend, monitor)


@app.command("monitors")
def monitors() -> None:
    """List MSS monitors."""
    _guarded("monitors", lambda: {"monitors": capture.list_monitors()})


@app.command("position")
def position() -> None:
    """Return current mouse position."""
    _guarded("position", automation.mouse_position)


@app.command()
def move(
    x: Annotated[int, typer.Argument(help="Target X coordinate.")],
    y: Annotated[int, typer.Argument(help="Target Y coordinate.")],
    duration: Annotated[float | None, typer.Option("--duration", "-d", help="Move duration in seconds. Overrides --speed.")] = None,
    speed: Annotated[float | None, typer.Option("--speed", help="Cursor speed in pixels per second when --duration is omitted.")] = None,
) -> None:
    """Move mouse to screen coordinates."""
    _guarded("move", automation.move, x, y, duration, speed)


@app.command("move-between")
def move_between(
    from_x: Annotated[int, typer.Argument(help="Start X coordinate.")],
    from_y: Annotated[int, typer.Argument(help="Start Y coordinate.")],
    to_x: Annotated[int, typer.Argument(help="Target X coordinate.")],
    to_y: Annotated[int, typer.Argument(help="Target Y coordinate.")],
    duration: Annotated[float | None, typer.Option("--duration", "-d", help="Move duration in seconds. Overrides --speed.")] = None,
    speed: Annotated[float | None, typer.Option("--speed", help="Cursor speed in pixels per second when --duration is omitted.")] = None,
    hold: Annotated[bool, typer.Option("--hold/--no-hold", help="Hold a mouse button while moving.")] = False,
    button: Annotated[str, typer.Option("--button", "-b", help="left, middle, or right.")] = "left",
) -> None:
    """Move cursor from one coordinate to another, optionally holding a mouse button."""
    if button not in {"left", "middle", "right"}:
        fail("move-between", "button must be one of: left, middle, right")
    _guarded("move-between", automation.move_between, from_x, from_y, to_x, to_y, duration, speed, hold, button)


@app.command()
def click(
    x: Annotated[int | None, typer.Argument(help="Optional X coordinate.")] = None,
    y: Annotated[int | None, typer.Argument(help="Optional Y coordinate.")] = None,
    button: Annotated[str, typer.Option("--button", "-b", help="left, middle, or right.")] = "left",
    clicks: Annotated[int, typer.Option("--clicks", "-c", help="Number of clicks.")] = 1,
    interval: Annotated[float, typer.Option("--interval", "-i", help="Delay between clicks.")] = 0.0,
) -> None:
    """Click at coordinates or at current mouse position."""
    if button not in {"left", "middle", "right"}:
        fail("click", "button must be one of: left, middle, right")
    _guarded("click", automation.click, x, y, button, clicks, interval)


@app.command("double-click")
def double_click(
    x: Annotated[int | None, typer.Argument(help="Optional X coordinate.")] = None,
    y: Annotated[int | None, typer.Argument(help="Optional Y coordinate.")] = None,
    button: Annotated[str, typer.Option("--button", "-b", help="left, middle, or right.")] = "left",
) -> None:
    """Double-click at coordinates or at current mouse position."""
    if button not in {"left", "middle", "right"}:
        fail("double-click", "button must be one of: left, middle, right")
    _guarded("double-click", automation.click, x, y, button, 2, 0.0)


@app.command("right-click")
def right_click(
    x: Annotated[int | None, typer.Argument(help="Optional X coordinate.")] = None,
    y: Annotated[int | None, typer.Argument(help="Optional Y coordinate.")] = None,
) -> None:
    """Right-click at coordinates or at current mouse position."""
    _guarded("right-click", automation.click, x, y, "right", 1, 0.0)


@app.command()
def drag(
    x: Annotated[int, typer.Argument(help="Target X coordinate.")],
    y: Annotated[int, typer.Argument(help="Target Y coordinate.")],
    duration: Annotated[float | None, typer.Option("--duration", "-d", help="Drag duration in seconds. Overrides --speed.")] = None,
    button: Annotated[str, typer.Option("--button", "-b", help="left, middle, or right.")] = "left",
    from_x: Annotated[int | None, typer.Option("--from-x", help="Optional drag start X coordinate.")] = None,
    from_y: Annotated[int | None, typer.Option("--from-y", help="Optional drag start Y coordinate.")] = None,
    speed: Annotated[float | None, typer.Option("--speed", help="Cursor speed in pixels per second when --duration is omitted.")] = None,
) -> None:
    """Drag mouse from current or supplied start position to target coordinates."""
    if button not in {"left", "middle", "right"}:
        fail("drag", "button must be one of: left, middle, right")
    _guarded("drag", automation.drag, x, y, duration, button, from_x, from_y, speed)


@app.command()
def scroll(
    clicks: Annotated[int, typer.Argument(help="Scroll amount. Positive is up, negative is down.")],
    x: Annotated[int | None, typer.Option(help="Optional X coordinate.")] = None,
    y: Annotated[int | None, typer.Option(help="Optional Y coordinate.")] = None,
    steps: Annotated[int | None, typer.Option("--steps", help="Split the scroll into smaller wheel events.")] = None,
    interval: Annotated[float, typer.Option("--interval", "-i", help="Delay between split scroll events.")] = 0.0,
) -> None:
    """Scroll at current or supplied mouse position."""
    _guarded("scroll", automation.scroll, clicks, x, y, steps, interval)


@app.command("type")
def type_command(
    text: Annotated[str, typer.Argument(help="Text to type into the focused app.")],
    interval: Annotated[float, typer.Option("--interval", "-i", help="Delay between characters.")] = 0.0,
) -> None:
    """Type text into the focused application."""
    _guarded("type", automation.type_text, text, interval)


@app.command()
def press(
    key: Annotated[str, typer.Argument(help="Key name, for example enter, esc, tab, f5.")],
    presses: Annotated[int, typer.Option("--presses", "-n", help="Number of presses.")] = 1,
    interval: Annotated[float, typer.Option("--interval", "-i", help="Delay between presses.")] = 0.0,
) -> None:
    """Press a keyboard key."""
    _guarded("press", automation.press_key, key, presses, interval)


@app.command()
def hotkey(
    keys: Annotated[list[str], typer.Argument(help="Keys to press together, e.g. ctrl l.")],
) -> None:
    """Press a key combination."""
    _guarded("hotkey", automation.hotkey, tuple(keys))


@app.command("match-image")
def match_image(
    image: Annotated[Path, typer.Option("--image", "-i", help="Screenshot/image path.")],
    template: Annotated[Path, typer.Option("--template", "-t", help="Template image path.")],
    threshold: Annotated[float, typer.Option("--threshold", help="Minimum confidence score.")] = 0.85,
) -> None:
    """Find a template image inside a larger image."""
    _guarded("match-image", vision.match_image, image, template, threshold)


@app.command("wait-image")
def wait_image(
    template: Annotated[Path, typer.Option("--template", "-t", help="Template image path.")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Repeated screenshot output path.")] = Path("wait-screen.png"),
    timeout: Annotated[float, typer.Option("--timeout", help="Max wait time in seconds.")] = 10.0,
    interval: Annotated[float, typer.Option("--interval", help="Delay between screenshots.")] = 0.5,
    threshold: Annotated[float, typer.Option("--threshold", help="Minimum confidence score.")] = 0.85,
    backend: Annotated[str, typer.Option("--backend", help="pyautogui, mss, or ffmpeg.")] = "mss",
    monitor: Annotated[int, typer.Option("--monitor", help="MSS monitor index. 0 is the full virtual desktop.")] = 0,
    x: Annotated[int | None, typer.Option(help="Region left coordinate.")] = None,
    y: Annotated[int | None, typer.Option(help="Region top coordinate.")] = None,
    width: Annotated[int | None, typer.Option(help="Region width.")] = None,
    height: Annotated[int | None, typer.Option(help="Region height.")] = None,
) -> None:
    """Poll screenshots until a template image appears or timeout expires."""
    region = _region_or_fail("wait-image", x, y, width, height)
    try:
        selected_backend = _backend(backend)
    except ValueError as exc:
        fail("wait-image", str(exc), type=exc.__class__.__name__)
    _guarded("wait-image", vision.wait_image, template, timeout, interval, threshold, output, selected_backend, monitor, region)


@app.command()
def crop(
    image: Annotated[Path, typer.Argument(help="Source image path.")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Cropped image path.")],
    x: Annotated[int, typer.Option(help="Region left coordinate.")],
    y: Annotated[int, typer.Option(help="Region top coordinate.")],
    width: Annotated[int, typer.Option(help="Region width.")],
    height: Annotated[int, typer.Option(help="Region height.")],
) -> None:
    """Crop an image region. Useful for creating templates."""
    region = _region_or_fail("crop", x, y, width, height)
    _guarded("crop", vision.crop_image, image, output, region)


@app.command()
def ocr(
    image: Annotated[Path, typer.Argument(help="Image path to OCR.")],
    language: Annotated[str, typer.Option("--language", "-l", help="Tesseract language code.")] = "eng",
) -> None:
    """Run OCR with pytesseract/Tesseract when available."""
    _guarded("ocr", vision.ocr_image, image, language)


@window_app.command("list")
def windows_list(
    include_empty: Annotated[bool, typer.Option("--include-empty", help="Include windows with empty titles.")] = False,
    include_minimized: Annotated[bool, typer.Option("--include-minimized/--no-minimized", help="Include minimized windows.")] = True,
) -> None:
    """List visible and hidden top-level windows."""
    _guarded("windows list", lambda: {"windows": windows.list_windows(include_empty, include_minimized)})


@window_app.command("active")
def windows_active() -> None:
    """Return the active top-level window."""
    _guarded("windows active", lambda: {"window": windows.active_window()})


@window_app.command("focus")
def windows_focus(
    title: Annotated[str, typer.Argument(help="Case-insensitive title substring.")],
) -> None:
    """Focus the first window matching a title substring."""
    _guarded("windows focus", windows.focus_window, title)


@window_app.command("screenshot")
def windows_screenshot(
    title: Annotated[str, typer.Argument(help="Case-insensitive title substring.")],
    output: Annotated[Path, typer.Option("--output", "-o", help="PNG path to write.")] = Path("window.png"),
    backend: Annotated[str, typer.Option("--backend", help="pyautogui, mss, or ffmpeg.")] = "mss",
) -> None:
    """Capture the first non-minimized window matching a title substring."""
    try:
        selected_backend = _backend(backend)
    except ValueError as exc:
        fail("windows screenshot", str(exc), type=exc.__class__.__name__)
    _guarded("windows screenshot", windows.screenshot_window, title, output, selected_backend)


@uia_app.command("tree")
def uia_tree(
    title: Annotated[str | None, typer.Option("--title", help="Window title substring. Defaults to active window.")] = None,
    depth: Annotated[int, typer.Option("--depth", help="Tree depth.")] = 2,
    backend: Annotated[str, typer.Option("--backend", help="uia or win32.")] = "uia",
    include_text: Annotated[bool, typer.Option("--include-text", help="Include control texts where available.")] = False,
) -> None:
    """Dump a UI Automation tree for a window."""
    try:
        selected_backend = _uia_backend(backend)
    except ValueError as exc:
        fail("uia tree", str(exc), type=exc.__class__.__name__)
    _guarded("uia tree", uia.element_tree, title, max(depth, 0), selected_backend, include_text)


@uia_app.command("find")
def uia_find(
    title: Annotated[str | None, typer.Option("--title", help="Window title substring. Defaults to active window.")] = None,
    name: Annotated[str | None, typer.Option("--name", help="Name substring.")] = None,
    automation_id: Annotated[str | None, typer.Option("--automation-id", help="Exact automation id.")] = None,
    control_type: Annotated[str | None, typer.Option("--control-type", help="Exact control type.")] = None,
    backend: Annotated[str, typer.Option("--backend", help="uia or win32.")] = "uia",
    limit: Annotated[int, typer.Option("--limit", help="Maximum number of results.")] = 20,
) -> None:
    """Find controls by UIA properties."""
    try:
        selected_backend = _uia_backend(backend)
    except ValueError as exc:
        fail("uia find", str(exc), type=exc.__class__.__name__)
    _guarded("uia find", lambda: {"controls": uia.find_controls(title, name, automation_id, control_type, selected_backend, max(limit, 1))})


@uia_app.command("click")
def uia_click(
    title: Annotated[str | None, typer.Option("--title", help="Window title substring. Defaults to active window.")] = None,
    name: Annotated[str | None, typer.Option("--name", help="Name substring.")] = None,
    automation_id: Annotated[str | None, typer.Option("--automation-id", help="Exact automation id.")] = None,
    control_type: Annotated[str | None, typer.Option("--control-type", help="Exact control type.")] = None,
    backend: Annotated[str, typer.Option("--backend", help="uia or win32.")] = "uia",
    index: Annotated[int, typer.Option("--index", help="Zero-based match index.")] = 0,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Return target control without clicking.")] = False,
) -> None:
    """Click a control by UIA properties."""
    try:
        selected_backend = _uia_backend(backend)
    except ValueError as exc:
        fail("uia click", str(exc), type=exc.__class__.__name__)
    _guarded("uia click", uia.click_control, title, name, automation_id, control_type, selected_backend, max(index, 0), dry_run)
