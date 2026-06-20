from __future__ import annotations

import re
from collections import deque
from typing import Any, Literal

Backend = Literal["uia", "win32"]


def _desktop(backend: Backend = "uia"):
    from pywinauto import Desktop

    return Desktop(backend=backend)


def _rect_to_dict(rect: Any) -> dict[str, int]:
    return {
        "left": int(rect.left),
        "top": int(rect.top),
        "right": int(rect.right),
        "bottom": int(rect.bottom),
        "width": int(rect.width()),
        "height": int(rect.height()),
    }


def _safe_prop(getter, default: object = None) -> object:
    try:
        return getter()
    except Exception:  # noqa: BLE001 - UIA providers often fail individual properties.
        return default


def serialize_element(element: Any, include_text: bool = False) -> dict[str, object]:
    info = element.element_info
    data: dict[str, object] = {
        "name": _safe_prop(lambda: info.name, ""),
        "controlType": _safe_prop(lambda: info.control_type, ""),
        "automationId": _safe_prop(lambda: info.automation_id, ""),
        "className": _safe_prop(lambda: info.class_name, ""),
        "handle": _safe_prop(lambda: int(info.handle), 0),
        "rectangle": _safe_prop(lambda: _rect_to_dict(element.rectangle()), None),
        "isVisible": _safe_prop(lambda: bool(element.is_visible()), None),
        "isEnabled": _safe_prop(lambda: bool(element.is_enabled()), None),
    }
    if include_text:
        data["texts"] = _safe_prop(lambda: element.texts(), [])
    return data


def _window_by_title(title: str, backend: Backend = "uia") -> Any:
    pattern = ".*" + re.escape(title) + ".*"
    window = _desktop(backend).window(title_re=pattern)
    if not window.exists(timeout=2):
        raise LookupError(f"no UIA window matches title substring: {title!r}")
    return window


def _active_window(backend: Backend = "uia") -> Any:
    from computer_use_cli import windows

    active = windows.active_window()
    title = str((active or {}).get("title") or "")
    if not title.strip():
        raise LookupError("no active window title available")
    return _window_by_title(title, backend)


def root_window(title: str | None = None, backend: Backend = "uia") -> Any:
    return _window_by_title(title, backend) if title else _active_window(backend)


def element_tree(
    title: str | None = None,
    depth: int = 2,
    backend: Backend = "uia",
    include_text: bool = False,
) -> dict[str, object]:
    root = root_window(title, backend)

    def build(element: Any, current_depth: int) -> dict[str, object]:
        node = serialize_element(element, include_text=include_text)
        if current_depth >= depth:
            return node
        children = _safe_prop(lambda: element.children(), [])
        node["children"] = [build(child, current_depth + 1) for child in children]
        return node

    return {"backend": backend, "title": title, "tree": build(root, 0)}


def _matches(
    data: dict[str, object],
    name: str | None,
    automation_id: str | None,
    control_type: str | None,
) -> bool:
    if name and name.casefold() not in str(data.get("name") or "").casefold():
        return False
    if automation_id and automation_id.casefold() != str(data.get("automationId") or "").casefold():
        return False
    if control_type and control_type.casefold() != str(data.get("controlType") or "").casefold():
        return False
    return bool(name or automation_id or control_type)


def find_controls(
    title: str | None = None,
    name: str | None = None,
    automation_id: str | None = None,
    control_type: str | None = None,
    backend: Backend = "uia",
    limit: int = 20,
) -> list[dict[str, object]]:
    root = root_window(title, backend)
    found: list[dict[str, object]] = []
    queue: deque[Any] = deque([root])
    while queue:
        element = queue.popleft()
        data = serialize_element(element)
        if _matches(data, name, automation_id, control_type):
            found.append(data)
            if len(found) >= limit:
                break
        children = _safe_prop(lambda: element.children(), [])
        queue.extend(children)
    return found


def _find_control_element(
    title: str | None,
    name: str | None,
    automation_id: str | None,
    control_type: str | None,
    backend: Backend,
    index: int,
) -> Any:
    root = root_window(title, backend)
    found: list[Any] = []
    queue: deque[Any] = deque([root])
    while queue:
        element = queue.popleft()
        data = serialize_element(element)
        if _matches(data, name, automation_id, control_type):
            found.append(element)
            if len(found) > index:
                return element
        children = _safe_prop(lambda: element.children(), [])
        queue.extend(children)
    raise LookupError("no matching control found")


def click_control(
    title: str | None = None,
    name: str | None = None,
    automation_id: str | None = None,
    control_type: str | None = None,
    backend: Backend = "uia",
    index: int = 0,
    dry_run: bool = False,
) -> dict[str, object]:
    element = _find_control_element(title, name, automation_id, control_type, backend, index)
    data = serialize_element(element)
    if not dry_run:
        element.click_input()
    return {"clicked": not dry_run, "dryRun": dry_run, "control": data}
