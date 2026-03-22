from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised in py3.10 only
    import tomli as tomllib  # type: ignore[no-redef]


REQUIRED_FILES = [
    "AGENTS.md",
    ".codex/config.toml",
    "scripts/codex/worktree-setup.sh",
    "scripts/codex/project-actions.sh",
    "assets/codex/automations/spec-quality-check.md",
    "assets/codex/automations/migration-audit.md",
]

REQUIRED_PROFILE_NAMES = ["spec-agentic", "spec-ci", "spec-review"]
REQUIRED_PROFILE_KEYS = ["model", "model_reasoning_effort", "sandbox_mode", "approval_policy", "web_search"]


def run(args) -> int:
    root = Path(args.root).resolve()
    json_mode = bool(getattr(args, "json", False))

    missing: list[str] = []
    warnings: list[str] = []
    for rel in REQUIRED_FILES:
        if not (root / rel).exists():
            missing.append(rel)

    agents_path = root / "AGENTS.md"
    if agents_path.exists():
        agents_text = agents_path.read_text(encoding="utf-8")
        if "## Review guidelines" not in agents_text:
            warnings.append("AGENTS.md missing '## Review guidelines' section")

    config_path = root / ".codex" / "config.toml"
    if config_path.exists():
        _validate_config_file(config_path, missing)

    payload = {
        "status": "ok" if not missing else "error",
        "missing": sorted(set(missing)),
        "warnings": warnings,
        "root": str(root),
    }

    if json_mode:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if missing:
            print("Codex compatibility check failed:")
            for item in payload["missing"]:
                print(f"- missing: {item}")
        else:
            print("Codex compatibility check passed.")
        if warnings:
            print("Warnings:")
            for item in warnings:
                print(f"- {item}")

    return 1 if missing else 0


def _validate_config_file(path: Path, missing: list[str]) -> None:
    raw = path.read_bytes()
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        missing.append(f".codex/config.toml must be UTF-8 encoded ({exc})")
        return
    except Exception as exc:  # tomllib and tomli raise parser-specific decode errors
        missing.append(f".codex/config.toml parse error: {exc}")
        return

    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        missing.append(".codex/config.toml missing table [profiles]")
        return

    for profile_name in REQUIRED_PROFILE_NAMES:
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            missing.append(f".codex/config.toml missing table [profiles.{profile_name}]")
            continue
        _validate_profile(profile, profile_name, missing)


def _validate_profile(profile: dict[str, Any], profile_name: str, missing: list[str]) -> None:
    for key in REQUIRED_PROFILE_KEYS:
        value = profile.get(key)
        if not isinstance(value, str) or not value.strip():
            missing.append(f".codex/config.toml [profiles.{profile_name}] missing non-empty '{key}'")
