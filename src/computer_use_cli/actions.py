from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from computer_use_cli import automation, capture, observe, policy as safety_policy, uia, vision, windows


def _require_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("action must be a JSON object")
    return value


def load_action(path: Path) -> dict[str, Any]:
    if str(path) == "-":
        import sys

        payload = json.load(sys.stdin)
    else:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    return _require_mapping(payload)


def _as_backend(value: Any, default: capture.Backend = "mss") -> capture.Backend:
    backend = str(value or default)
    if backend not in {"pyautogui", "mss", "ffmpeg"}:
        raise ValueError("backend must be one of: pyautogui, mss, ffmpeg")
    return backend  # type: ignore[return-value]


def _as_uia_backend(value: Any, default: uia.Backend = "uia") -> uia.Backend:
    backend = str(value or default)
    if backend not in {"uia", "win32"}:
        raise ValueError("uia backend must be one of: uia, win32")
    return backend  # type: ignore[return-value]


def _region(action: dict[str, Any]) -> capture.Region | None:
    region = action.get("region")
    if region is not None:
        if not isinstance(region, list | tuple) or len(region) != 4:
            raise ValueError("region must be [x, y, width, height]")
        x, y, width, height = region
        return capture.normalize_region(int(x), int(y), int(width), int(height))

    keys = ("x", "y", "width", "height")
    if any(key in action for key in keys):
        return capture.normalize_region(
            action.get("x"),
            action.get("y"),
            action.get("width"),
            action.get("height"),
        )
    return None


def _path(value: Any, default: str) -> Path:
    return Path(str(value or default))


def _keys(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part for part in value.replace("+", " ").split(" ") if part)
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    raise ValueError("keys must be a list or a string like 'ctrl+l'")


def supported_actions() -> list[str]:
    return [
        "click",
        "doubleClick",
        "drag",
        "focusWindow",
        "hotkey",
        "matchImage",
        "move",
        "observe",
        "ocr",
        "position",
        "press",
        "rightClick",
        "screenshot",
        "screenshotWindow",
        "scroll",
        "sleep",
        "type",
        "uiaClick",
        "uiaFind",
        "uiaTree",
        "waitImage",
    ]


def run_action(
    action: dict[str, Any],
    *,
    dry_run: bool = False,
    policy: safety_policy.SafetyPolicy | None = None,
) -> dict[str, Any]:
    action = _require_mapping(action)
    if policy is not None:
        safety_policy.validate_action(policy, action, dry_run=dry_run)
    kind = action.get("type") or action.get("action")
    if not isinstance(kind, str) or not kind.strip():
        raise ValueError("action requires a string 'type' field")
    kind = kind.strip()

    if dry_run and kind not in {"observe", "position", "screenshot", "uiaClick", "uiaFind", "uiaTree"}:
        return {"dryRun": True, "wouldRun": action}

    if kind == "position":
        return automation.mouse_position()

    if kind == "move":
        return automation.move(int(action["x"]), int(action["y"]), float(action.get("duration", 0.0)))

    if kind == "click":
        return automation.click(
            int(action["x"]) if "x" in action else None,
            int(action["y"]) if "y" in action else None,
            str(action.get("button", "left")),  # type: ignore[arg-type]
            int(action.get("clicks", 1)),
            float(action.get("interval", 0.0)),
        )

    if kind == "doubleClick":
        return automation.click(
            int(action["x"]) if "x" in action else None,
            int(action["y"]) if "y" in action else None,
            str(action.get("button", "left")),  # type: ignore[arg-type]
            2,
            0.0,
        )

    if kind == "rightClick":
        return automation.click(
            int(action["x"]) if "x" in action else None,
            int(action["y"]) if "y" in action else None,
            "right",
            1,
            0.0,
        )

    if kind == "drag":
        return automation.drag(
            int(action["x"]),
            int(action["y"]),
            float(action.get("duration", 0.2)),
            str(action.get("button", "left")),  # type: ignore[arg-type]
        )

    if kind == "scroll":
        return automation.scroll(
            int(action["clicks"]),
            int(action["x"]) if "x" in action else None,
            int(action["y"]) if "y" in action else None,
        )

    if kind == "type":
        return automation.type_text(str(action["text"]), float(action.get("interval", 0.0)))

    if kind == "press":
        return automation.press_key(
            str(action["key"]),
            int(action.get("presses", 1)),
            float(action.get("interval", 0.0)),
        )

    if kind == "hotkey":
        return automation.hotkey(_keys(action.get("keys")))

    if kind == "sleep":
        seconds = float(action.get("seconds", 1.0))
        time.sleep(max(seconds, 0.0))
        return {"seconds": seconds}

    if kind == "screenshot":
        return capture.capture_screen(
            _path(action.get("output"), "screen.png"),
            _region(action),
            _as_backend(action.get("backend")),
            int(action.get("monitor", 0)),
        )

    if kind == "screenshotWindow":
        return windows.screenshot_window(
            str(action["title"]),
            _path(action.get("output"), "window.png"),
            _as_backend(action.get("backend")),
        )

    if kind == "focusWindow":
        return windows.focus_window(str(action["title"]))

    if kind == "matchImage":
        return vision.match_image(
            _path(action.get("image"), "screen.png"),
            _path(action.get("template"), "template.png"),
            float(action.get("threshold", 0.85)),
            str(action.get("method", "TM_CCOEFF_NORMED")),
        )

    if kind == "waitImage":
        return vision.wait_image(
            _path(action.get("template"), "template.png"),
            float(action.get("timeout", 10.0)),
            float(action.get("interval", 0.5)),
            float(action.get("threshold", 0.85)),
            _path(action.get("output"), "wait-screen.png"),
            _as_backend(action.get("backend")),
            int(action.get("monitor", 0)),
            _region(action),
        )

    if kind == "ocr":
        return vision.ocr_image(
            _path(action.get("image"), "screen.png"),
            str(action.get("language", "eng")),
        )

    if kind == "uiaTree":
        return uia.element_tree(
            action.get("title"),
            int(action.get("depth", 2)),
            _as_uia_backend(action.get("backend")),
            bool(action.get("includeText", False)),
        )

    if kind == "uiaFind":
        return {
            "controls": uia.find_controls(
                action.get("title"),
                action.get("name"),
                action.get("automationId"),
                action.get("controlType"),
                _as_uia_backend(action.get("backend")),
                int(action.get("limit", 20)),
            )
        }

    if kind == "uiaClick":
        return uia.click_control(
            action.get("title"),
            action.get("name"),
            action.get("automationId"),
            action.get("controlType"),
            _as_uia_backend(action.get("backend")),
            int(action.get("index", 0)),
            bool(action.get("dryRun", dry_run)),
        )

    if kind == "observe":
        return observe.observe_state(
            _path(action.get("screenshot"), "observe-screen.png"),
            _as_backend(action.get("backend")),
            int(action.get("monitor", 0)),
            bool(action.get("includeScreenshot", True)),
            bool(action.get("includeWindows", True)),
            bool(action.get("includeUia", False)),
            int(action.get("uiaDepth", 2)),
            action.get("uiaTitle"),
            _as_uia_backend(action.get("uiaBackend")),
            bool(action.get("includeMinimized", False)),
        )

    raise ValueError(f"unsupported action type: {kind}. Supported: {', '.join(supported_actions())}")
