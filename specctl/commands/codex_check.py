from __future__ import annotations

import json
from pathlib import Path


REQUIRED_FILES = [
    "AGENTS.md",
    ".codex/config.toml",
    "scripts/codex/worktree-setup.sh",
    "scripts/codex/project-actions.sh",
    "assets/codex/automations/spec-quality-check.md",
    "assets/codex/automations/migration-audit.md",
]


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
        text = config_path.read_text(encoding="utf-8")
        for section in ["[profiles.spec-agentic]", "[profiles.spec-ci]", "[profiles.spec-review]"]:
            if section not in text:
                missing.append(f".codex/config.toml section {section}")
        for key in ["sandbox_mode", "approval_policy", "web_search"]:
            if key not in text:
                warnings.append(f".codex/config.toml missing key '{key}'")

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
