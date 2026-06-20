from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

_PRETTY = False
_LOG_PATH: Path | None = None


def set_pretty(value: bool) -> None:
    global _PRETTY
    _PRETTY = value


def set_log_path(value: Path | None) -> None:
    global _LOG_PATH
    env_path = os.environ.get("COMPUTER_USE_LOG")
    _LOG_PATH = value or (Path(env_path) if env_path else None)


def _append_log(payload: dict[str, Any]) -> None:
    if _LOG_PATH is None:
        return
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_payload = {"timestamp": datetime.now(UTC).isoformat(), **payload}
    with _LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(log_payload, ensure_ascii=False) + "\n")


def emit(payload: dict[str, Any]) -> None:
    _append_log(payload)
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2 if _PRETTY else None))


def ok(action: str, **data: Any) -> None:
    emit({"ok": True, "action": action, **data})


def fail(action: str, message: str, **data: Any) -> None:
    emit({"ok": False, "action": action, "error": message, **data})
    raise typer.Exit(1)
