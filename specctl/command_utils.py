from __future__ import annotations

from pathlib import Path

from specctl.models import LintMessage


def project_root(path_arg: str | None) -> Path:
    return Path(path_arg or ".").resolve()


def format_message(msg: LintMessage) -> str:
    location = ""
    if msg.path:
        location = str(msg.path)
        if msg.line:
            location = f"{location}:{msg.line}"
        location = f" ({location})"
    return f"[{msg.severity}] {msg.code}: {msg.message}{location}"


def print_messages(messages: list[LintMessage]) -> None:
    for msg in messages:
        print(format_message(msg))


def has_errors(messages: list[LintMessage], strict: bool = False) -> bool:
    if strict:
        return any(msg.severity in {"ERROR", "WARN"} for msg in messages)
    return any(msg.severity == "ERROR" for msg in messages)
