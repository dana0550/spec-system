from __future__ import annotations

import ast
import datetime as dt
import re
from pathlib import Path
from typing import Any


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def set_frontmatter_value(path: Path, key: str, value: str) -> None:
    text = read_text(path)
    data, body = parse_frontmatter(text)
    data[key] = value
    write_text(path, dump_frontmatter(data) + body.lstrip("\n"))


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "feature"


def now_date() -> str:
    return dt.date.today().isoformat()


def now_timestamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    frontmatter_text = text[4:end]
    body = text[end + 5 :]
    data: dict[str, Any] = {}
    for line in frontmatter_text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        value = raw.strip()
        data[key] = _parse_scalar(value)
    return data, body


def dump_frontmatter(data: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in data.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _parse_scalar(value: str) -> Any:
    if not value:
        return ""
    if value.startswith(("'", '"')) and value.endswith(("'", '"')):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value
