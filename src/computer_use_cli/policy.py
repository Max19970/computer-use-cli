from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from computer_use_cli import windows

READ_ONLY_ACTIONS = {
    "matchImage",
    "observe",
    "ocr",
    "position",
    "screenshot",
    "screenshotWindow",
    "uiaFind",
    "uiaTree",
    "waitImage",
}

MUTATING_ACTIONS = {
    "click",
    "doubleClick",
    "drag",
    "focusWindow",
    "hotkey",
    "move",
    "moveBetween",
    "press",
    "rightClick",
    "scroll",
    "sleep",
    "type",
    "uiaClick",
}

ALL_POLICY_ACTIONS = READ_ONLY_ACTIONS | MUTATING_ACTIONS

SENSITIVE_WINDOW_SUBSTRINGS = [
    "1password",
    "bank",
    "bitwarden",
    "keepass",
    "password",
    "paypal",
    "settings",
    "вход",
    "настройки",
    "парол",
    "сбер",
    "тинькофф",
]


@dataclass(slots=True)
class SafetyPolicy:
    name: str = "permissive"
    allowed_actions: set[str] | None = None
    denied_actions: set[str] = field(default_factory=set)
    require_dry_run_actions: set[str] = field(default_factory=set)
    allowed_window_title_substrings: list[str] = field(default_factory=list)
    denied_window_title_substrings: list[str] = field(default_factory=list)
    allowed_regions: list[tuple[int, int, int, int]] = field(default_factory=list)
    max_clicks: int = 3
    max_scroll_abs: int = 20
    max_type_length: int = 500
    max_sleep_seconds: float = 10.0
    allow_text_input: bool = True
    allow_keyboard: bool = True
    allow_mouse: bool = True
    allow_window_focus: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "allowedActions": (
                sorted(self.allowed_actions) if self.allowed_actions is not None else None
            ),
            "deniedActions": sorted(self.denied_actions),
            "requireDryRunActions": sorted(self.require_dry_run_actions),
            "allowedWindowTitleSubstrings": self.allowed_window_title_substrings,
            "deniedWindowTitleSubstrings": self.denied_window_title_substrings,
            "allowedRegions": [list(region) for region in self.allowed_regions],
            "maxClicks": self.max_clicks,
            "maxScrollAbs": self.max_scroll_abs,
            "maxTypeLength": self.max_type_length,
            "maxSleepSeconds": self.max_sleep_seconds,
            "allowTextInput": self.allow_text_input,
            "allowKeyboard": self.allow_keyboard,
            "allowMouse": self.allow_mouse,
            "allowWindowFocus": self.allow_window_focus,
        }


def _string_set(value: Any, default: set[str] | None = None) -> set[str] | None:
    if value is None:
        return default
    if not isinstance(value, list):
        raise ValueError("expected a JSON list of strings")
    return {str(item) for item in value}


def _string_list(value: Any, default: list[str] | None = None) -> list[str]:
    if value is None:
        return list(default or [])
    if not isinstance(value, list):
        raise ValueError("expected a JSON list of strings")
    return [str(item) for item in value]


def _regions(value: Any) -> list[tuple[int, int, int, int]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("allowedRegions must be a list")
    regions: list[tuple[int, int, int, int]] = []
    for item in value:
        if not isinstance(item, list | tuple) or len(item) != 4:
            raise ValueError("each allowed region must be [x, y, width, height]")
        x, y, width, height = (int(item[0]), int(item[1]), int(item[2]), int(item[3]))
        if width <= 0 or height <= 0:
            raise ValueError("allowed region width and height must be positive")
        regions.append((x, y, width, height))
    return regions


def preset_policy(name: str) -> SafetyPolicy:
    normalized = name.strip().casefold()
    if normalized in {"off", "none", "permissive"}:
        return SafetyPolicy(name="permissive")
    if normalized == "observe-only":
        return SafetyPolicy(
            name="observe-only",
            allowed_actions=set(READ_ONLY_ACTIONS),
            denied_actions=set(MUTATING_ACTIONS),
            allow_text_input=False,
            allow_keyboard=False,
            allow_mouse=False,
            allow_window_focus=False,
        )
    if normalized == "guarded":
        return SafetyPolicy(
            name="guarded",
            denied_window_title_substrings=list(SENSITIVE_WINDOW_SUBSTRINGS),
            require_dry_run_actions={"uiaClick"},
            max_clicks=2,
            max_scroll_abs=10,
            max_type_length=240,
            max_sleep_seconds=5.0,
        )
    raise ValueError("unknown policy preset. Use permissive, guarded, or observe-only")


def load_policy_file(path: Path) -> SafetyPolicy:
    with path.open("r", encoding="utf-8") as file:
        raw = json.load(file)
    if not isinstance(raw, dict):
        raise ValueError("policy file must contain a JSON object")

    base = preset_policy(str(raw.get("base", raw.get("preset", "permissive"))))
    base.name = str(raw.get("name", base.name))
    base.allowed_actions = _string_set(raw.get("allowedActions"), base.allowed_actions)
    base.denied_actions = _string_set(raw.get("deniedActions"), base.denied_actions) or set()
    base.require_dry_run_actions = (
        _string_set(raw.get("requireDryRunActions"), base.require_dry_run_actions) or set()
    )
    base.allowed_window_title_substrings = _string_list(
        raw.get("allowedWindowTitleSubstrings"),
        base.allowed_window_title_substrings,
    )
    base.denied_window_title_substrings = _string_list(
        raw.get("deniedWindowTitleSubstrings"),
        base.denied_window_title_substrings,
    )
    base.allowed_regions = _regions(raw.get("allowedRegions")) or base.allowed_regions
    base.max_clicks = int(raw.get("maxClicks", base.max_clicks))
    base.max_scroll_abs = int(raw.get("maxScrollAbs", base.max_scroll_abs))
    base.max_type_length = int(raw.get("maxTypeLength", base.max_type_length))
    base.max_sleep_seconds = float(raw.get("maxSleepSeconds", base.max_sleep_seconds))
    base.allow_text_input = bool(raw.get("allowTextInput", base.allow_text_input))
    base.allow_keyboard = bool(raw.get("allowKeyboard", base.allow_keyboard))
    base.allow_mouse = bool(raw.get("allowMouse", base.allow_mouse))
    base.allow_window_focus = bool(raw.get("allowWindowFocus", base.allow_window_focus))
    return base


def resolve_policy(preset: str = "permissive", path: Path | None = None) -> SafetyPolicy:
    env_policy = os.environ.get("COMPUTER_USE_POLICY")
    if path is not None:
        return load_policy_file(path)
    if env_policy:
        maybe_path = Path(env_policy)
        if maybe_path.exists():
            return load_policy_file(maybe_path)
        return preset_policy(env_policy)
    return preset_policy(preset)


def _action_kind(action: dict[str, Any]) -> str:
    kind = action.get("type") or action.get("action")
    if not isinstance(kind, str) or not kind.strip():
        raise ValueError("action requires a string 'type' field")
    return kind.strip()


def _matches_any(text: str, needles: list[str]) -> str | None:
    folded = text.casefold()
    for needle in needles:
        if needle and needle.casefold() in folded:
            return needle
    return None


def _action_window_title(action: dict[str, Any]) -> str | None:
    title = action.get("title") or action.get("uiaTitle")
    return str(title) if title is not None else None


def _current_window_title() -> str:
    active = windows.active_window() or {}
    return str(active.get("title") or "")


def _coordinate_points(action: dict[str, Any]) -> list[tuple[int, int]]:
    kind = _action_kind(action)
    points: list[tuple[int, int]] = []
    if kind in {"click", "doubleClick", "rightClick", "move", "drag", "scroll"}:
        if "x" in action and "y" in action:
            points.append((int(action["x"]), int(action["y"])))
    if kind in {"drag", "moveBetween"}:
        from_x = action.get("fromX", action.get("startX"))
        from_y = action.get("fromY", action.get("startY"))
        to_x = action.get("toX", action.get("endX", action.get("x")))
        to_y = action.get("toY", action.get("endY", action.get("y")))
        if from_x is not None and from_y is not None:
            points.append((int(from_x), int(from_y)))
        if to_x is not None and to_y is not None:
            points.append((int(to_x), int(to_y)))
    return points


def _point_in_region(point: tuple[int, int], region: tuple[int, int, int, int]) -> bool:
    x, y = point
    left, top, width, height = region
    return left <= x < left + width and top <= y < top + height


def _check_window(policy: SafetyPolicy, action: dict[str, Any]) -> None:
    action_title = _action_window_title(action)
    title = action_title or _current_window_title()
    if not title:
        return

    denied = _matches_any(title, policy.denied_window_title_substrings)
    if denied:
        raise PermissionError(
            f"blocked by policy: window title matches denied substring {denied!r}"
        )

    if policy.allowed_window_title_substrings:
        allowed = _matches_any(title, policy.allowed_window_title_substrings)
        if not allowed:
            raise PermissionError(
                "blocked by policy: window title is not in allowedWindowTitleSubstrings"
            )


def validate_action(
    policy: SafetyPolicy,
    action: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    kind = _action_kind(action)
    if kind not in ALL_POLICY_ACTIONS:
        return {
            "policy": policy.to_dict(),
            "allowed": True,
            "reason": "unknown action validation deferred to dispatcher",
        }

    if policy.allowed_actions is not None and kind not in policy.allowed_actions:
        raise PermissionError(f"blocked by policy: action {kind!r} is not allowed")
    if kind in policy.denied_actions:
        raise PermissionError(f"blocked by policy: action {kind!r} is denied")
    if (
        kind in policy.require_dry_run_actions
        and not dry_run
        and not bool(action.get("dryRun", False))
    ):
        raise PermissionError(f"blocked by policy: action {kind!r} requires dryRun=true")

    if kind in {
        "click",
        "doubleClick",
        "rightClick",
        "move",
        "moveBetween",
        "drag",
        "scroll",
    }:
        if not policy.allow_mouse:
            raise PermissionError("blocked by policy: mouse actions are disabled")
        clicks = int(action.get("clicks", 1))
        if kind in {"click", "doubleClick", "rightClick"} and clicks > policy.max_clicks:
            raise PermissionError("blocked by policy: click count exceeds maxClicks")
        scroll_amount = action.get(
            "clicks",
            action.get("amount", action.get("delta", action.get("dy", 0))),
        )
        if kind == "scroll" and abs(int(scroll_amount)) > policy.max_scroll_abs:
            raise PermissionError("blocked by policy: scroll amount exceeds maxScrollAbs")

    if kind in {"type", "press", "hotkey"}:
        if not policy.allow_keyboard:
            raise PermissionError("blocked by policy: keyboard actions are disabled")
        if kind == "type":
            if not policy.allow_text_input:
                raise PermissionError("blocked by policy: text input is disabled")
            if len(str(action.get("text", ""))) > policy.max_type_length:
                raise PermissionError("blocked by policy: text length exceeds maxTypeLength")

    if kind == "sleep" and float(action.get("seconds", 1.0)) > policy.max_sleep_seconds:
        raise PermissionError("blocked by policy: sleep duration exceeds maxSleepSeconds")

    if kind == "focusWindow" and not policy.allow_window_focus:
        raise PermissionError("blocked by policy: window focus actions are disabled")

    if kind in MUTATING_ACTIONS:
        _check_window(policy, action)

    if policy.allowed_regions:
        for point in _coordinate_points(action):
            if not any(_point_in_region(point, region) for region in policy.allowed_regions):
                raise PermissionError("blocked by policy: coordinates are outside allowedRegions")

    return {"policy": policy.to_dict(), "allowed": True, "action": kind}
