from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import yaml

from specctl.agentic_epic import validate_feature_quality
from specctl.cli import main
from specctl.constants import NEEDS_INPUT_EXIT_CODE
from specctl.feature_index import read_feature_rows


def test_real_project_agentic_codex_strict_runner_end_to_end(tmp_path: Path, monkeypatch, capsys) -> None:
    root = tmp_path / "workspace"
    _init_workspace(root)
    brief_path = root / "platform-brief.md"
    _write_real_project_brief(brief_path, include_ui=True)

    runner_script = root / "fake_codex_runner.py"
    _write_fake_codex_runner_script(runner_script)
    _configure_fake_codex_runner(
        monkeypatch,
        runner_script=runner_script,
        mode="stable",
        log_path=root / "runner-log.jsonl",
    )

    answers_path = root / "answers.yaml"
    _write_answers(
        answers_path,
        {
            "Q-RUNNER-001": "Retain audit events for 365 days.",
        },
    )

    capsys.readouterr()
    rc = main(
        [
            "epic",
            "create",
            "--root",
            str(root),
            "--name",
            "Platform Revamp",
            "--owner",
            "owner@example.com",
            "--brief",
            str(brief_path),
            "--runner",
            "codex",
            "--codex-surface",
            "app",
            "--codex-profile",
            "spec-agentic",
            "--research-depth",
            "deep",
            "--no-interactive",
            "--answers-file",
            str(answers_path),
            "--json",
        ]
    )
    assert rc == 0
    payload = _parse_json_payload(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["phase"] == "commit"
    assert payload["runner_policy"] == "strict"

    epic_dir = _first_epic_dir(root)
    oneshot = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    assert oneshot["codex"]["surface"] == "app"
    assert oneshot["codex"]["profile"] == "spec-agentic"
    assert oneshot["codex"]["runner_policy"] == "strict"
    assert oneshot["synthesis_quality_profile"]["research_depth"] == "deep"

    state = json.loads((epic_dir / "agentic_state.json").read_text(encoding="utf-8"))
    assert state["runner_meta"]["thread_id"] == "th_fake"
    assert state["runner_meta"]["session_id"] == "se_fake"
    assert {"adaptive_decomposition", "research", "question_loop"} <= {
        row["phase"] for row in state["phase_history"]
    }

    rows = read_feature_rows(root / "docs" / "FEATURES.md")
    assert any("Runner-Inferred Hardening Track" in row.name for row in rows)

    assert main(["impact", "refresh", "--root", str(root)]) == 0
    assert main(["check", "--root", str(root)]) == 0
    assert main(["oneshot", "run", "--root", str(root), "--epic-id", "E-001"]) == 0
    epics_text = (root / "docs" / "EPICS.md").read_text(encoding="utf-8")
    assert "| E-001 | Platform Revamp | implementing | F-001 |" in epics_text


def test_research_depth_changes_runner_iteration_budget_in_real_flow(tmp_path: Path, monkeypatch) -> None:
    runner_script = tmp_path / "fake_codex_runner.py"
    _write_fake_codex_runner_script(runner_script)

    deep_root = tmp_path / "deep-workspace"
    lean_root = tmp_path / "lean-workspace"
    deep_entries, deep_oneshot = _run_depth_case(
        root=deep_root,
        brief_name="DeepDepthEpic",
        depth="deep",
        runner_script=runner_script,
        monkeypatch=monkeypatch,
    )
    lean_entries, lean_oneshot = _run_depth_case(
        root=lean_root,
        brief_name="LeanDepthEpic",
        depth="lean",
        runner_script=runner_script,
        monkeypatch=monkeypatch,
    )

    assert len(deep_entries) == 9
    assert len(lean_entries) == 3
    assert {entry["phase"] for entry in deep_entries} == {"adaptive_decomposition", "research", "question_loop"}
    assert {entry["phase"] for entry in lean_entries} == {"adaptive_decomposition", "research", "question_loop"}

    assert deep_oneshot["synthesis_quality_profile"]["reasoning_effort"] == "high"
    assert deep_oneshot["synthesis_quality_profile"]["max_phase_iterations"] == 3
    assert lean_oneshot["synthesis_quality_profile"]["reasoning_effort"] == "low"
    assert lean_oneshot["synthesis_quality_profile"]["max_phase_iterations"] == 1


def test_real_project_migration_strict_missing_answers_exits_without_mutation(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _init_workspace(root)
    brief_path = root / "migration-brief.md"
    _write_real_project_brief(brief_path, include_ui=False)
    _create_deterministic_epic(root, name="LegacyDeterministicEpic", brief_path=brief_path)

    first_feature_dir = next((root / "docs" / "features").glob("F-001-*"))
    before = {
        filename: (first_feature_dir / filename).read_text(encoding="utf-8")
        for filename in ["requirements.md", "design.md", "tasks.md", "verification.md"]
    }
    question_pack = root / "pending-migrate-questions.yaml"

    rc = main(
        [
            "epic",
            "migrate-agentic",
            "--root",
            str(root),
            "--epic-id",
            "E-001",
            "--apply",
            "--runner-policy",
            "strict",
            "--no-interactive",
            "--question-pack-out",
            str(question_pack),
        ]
    )
    assert rc == NEEDS_INPUT_EXIT_CODE
    assert question_pack.exists()

    after = {
        filename: (first_feature_dir / filename).read_text(encoding="utf-8")
        for filename in ["requirements.md", "design.md", "tasks.md", "verification.md"]
    }
    assert after == before

    epic_dir = _first_epic_dir(root)
    assert not (epic_dir / "research.md").exists()
    assert not (epic_dir / "agentic_state.json").exists()


def test_real_project_migration_apply_backfills_quality_for_scope_features(tmp_path: Path, capsys) -> None:
    root = tmp_path / "workspace"
    _init_workspace(root)
    brief_path = root / "migration-brief.md"
    _write_real_project_brief(brief_path, include_ui=True)
    _create_deterministic_epic(root, name="LegacyPortalEpic", brief_path=brief_path)

    answers_path = root / "migration-answers.yaml"
    answers_path.write_text(
        "\n".join(
            [
                "Q-AGENTIC-001: Improve enterprise onboarding success rate.",
                "Q-AGENTIC-002: Enforce SOC2, GDPR, and tenant audit retention controls.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    rc = main(
        [
            "epic",
            "migrate-agentic",
            "--root",
            str(root),
            "--epic-id",
            "E-001",
            "--apply",
            "--runner-policy",
            "strict",
            "--no-interactive",
            "--answers-file",
            str(answers_path),
            "--json",
        ]
    )
    assert rc == 0
    payload = _parse_json_payload(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["phase"] == "apply"
    assert payload["runner_policy"] == "strict"
    assert payload["upgrades_count"] > 0

    epic_dir = _first_epic_dir(root)
    oneshot = yaml.safe_load((epic_dir / "oneshot.yaml").read_text(encoding="utf-8"))
    assert oneshot["codex"]["runner_policy"] == "strict"
    assert oneshot["synthesis_quality_profile"]["minimums"]["requirements"] == 3

    rows = {row.feature_id: row for row in read_feature_rows(root / "docs" / "FEATURES.md")}
    for feature_id in oneshot["scope_feature_ids"]:
        feature_dir = (root / "docs" / rows[feature_id].spec_path).parent
        assert validate_feature_quality(feature_dir) == []

    assert main(["impact", "refresh", "--root", str(root)]) == 0
    assert main(["check", "--root", str(root)]) == 0


def _run_depth_case(
    *,
    root: Path,
    brief_name: str,
    depth: str,
    runner_script: Path,
    monkeypatch,
) -> tuple[list[dict[str, object]], dict]:
    _init_workspace(root)
    brief_path = root / "depth-brief.md"
    _write_real_project_brief(brief_path, include_ui=True)

    log_path = root / "runner-depth-log.jsonl"
    _configure_fake_codex_runner(
        monkeypatch,
        runner_script=runner_script,
        mode="growing",
        log_path=log_path,
    )

    answers_path = root / "answers.yaml"
    _write_answers(answers_path, {})

    rc = main(
        [
            "epic",
            "create",
            "--root",
            str(root),
            "--name",
            brief_name,
            "--owner",
            "owner@example.com",
            "--brief",
            str(brief_path),
            "--research-depth",
            depth,
            "--no-interactive",
            "--answers-file",
            str(answers_path),
        ]
    )
    assert rc == 0

    entries = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    oneshot = yaml.safe_load((_first_epic_dir(root) / "oneshot.yaml").read_text(encoding="utf-8"))
    return entries, oneshot


def _init_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    assert main(["init", "--root", str(root)]) == 0


def _create_deterministic_epic(root: Path, *, name: str, brief_path: Path) -> None:
    assert (
        main(
            [
                "epic",
                "create",
                "--root",
                str(root),
                "--name",
                name,
                "--owner",
                "owner@example.com",
                "--brief",
                str(brief_path),
                "--mode",
                "deterministic",
            ]
        )
        == 0
    )


def _write_real_project_brief(path: Path, *, include_ui: bool) -> None:
    ui_line = "- Provide a responsive admin dashboard for onboarding and incident review." if include_ui else "- Avoid UI redesign in this phase."
    path.write_text(
        "\n".join(
            [
                "# Enterprise Platform Upgrade",
                "",
                "## Vision",
                "- Build reliable multi-tenant onboarding and operational control planes.",
                "",
                "## Outcomes",
                "- Reduce enterprise tenant setup failures by 40%.",
                "- Cut incident detection time below 5 minutes.",
                "",
                "## User Journeys",
                "- Admin provisions a new tenant and validates policy configuration.",
                "- Operator monitors onboarding health and resolves failed jobs.",
                "",
                "## Constraints",
                "- Preserve backward compatibility for existing API contracts.",
                "- Enforce SOC2 and GDPR controls for event handling and retention.",
                ui_line,
                "",
                "## Non-Goals",
                "- No billing workflow changes.",
                "- No migration to a new database engine.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_answers(path: Path, extra_answers: dict[str, str]) -> None:
    lines = [
        "Q-AGENTIC-001: Improve onboarding conversion and time-to-value.",
        "Q-AGENTIC-002: SOC2 and GDPR controls are mandatory.",
        "A-AGENTIC-DECOMPOSITION: yes",
        "A-AGENTIC-COMMIT: yes",
    ]
    for key, value in extra_answers.items():
        lines.append(f"{key}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _configure_fake_codex_runner(monkeypatch, *, runner_script: Path, mode: str, log_path: Path) -> None:
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(runner_script))}"
    monkeypatch.setenv("SPECCTL_AGENTIC_RUNNER_COMMAND_CODEX", command)
    monkeypatch.setenv("SPECCTL_FAKE_RUNNER_MODE", mode)
    monkeypatch.setenv("SPECCTL_FAKE_RUNNER_LOG", str(log_path))


def _write_fake_codex_runner_script(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                "",
                "def _emit(payload: dict[str, object]) -> None:",
                "    print(json.dumps({'type': 'thread.started', 'thread_id': 'th_fake', 'session_id': 'se_fake'}))",
                "    print(",
                "        json.dumps(",
                "            {",
                "                'type': 'thread.message',",
                "                'message': {'content': [{'type': 'output_text', 'text': json.dumps(payload, sort_keys=True)}]},",
                "            }",
                "        )",
                "    )",
                "",
                "",
                "def _log(request: dict[str, object], mode: str) -> None:",
                "    log_path = os.environ.get('SPECCTL_FAKE_RUNNER_LOG', '').strip()",
                "    if not log_path:",
                "        return",
                "    behavior = request.get('research_behavior', {})",
                "    if not isinstance(behavior, dict):",
                "        behavior = {}",
                "    entry = {",
                "        'phase': request.get('phase', ''),",
                "        'attempt': request.get('attempt', 0),",
                "        'research_depth': request.get('research_depth', ''),",
                "        'reasoning_effort': behavior.get('reasoning_effort', ''),",
                "        'max_phase_iterations': behavior.get('max_phase_iterations', 0),",
                "        'mode': mode,",
                "    }",
                "    with Path(log_path).open('a', encoding='utf-8') as handle:",
                "        handle.write(json.dumps(entry, sort_keys=True) + '\\n')",
                "",
                "",
                "def main() -> None:",
                "    raw = sys.stdin.read().strip() or '{}'",
                "    request = json.loads(raw)",
                "    phase = str(request.get('phase', ''))",
                "    attempt = int(request.get('attempt', 1))",
                "    mode = os.environ.get('SPECCTL_FAKE_RUNNER_MODE', 'stable').strip() or 'stable'",
                "",
                "    _log(request, mode)",
                "",
                "    response: dict[str, object] = {",
                "        'decomposition_nodes': [],",
                "        'research_findings': [],",
                "        'questions': [],",
                "        'feature_synthesis': [],",
                "    }",
                "",
                "    if mode == 'growing':",
                "        if phase == 'adaptive_decomposition':",
                "            response['decomposition_nodes'] = [",
                "                {",
                "                    'temp_id': f'N-GROW-{attempt:03d}',",
                "                    'parent_temp_id': 'N-ROOT',",
                "                    'name': f'Growth Capability {attempt}',",
                "                    'node_type': 'capability',",
                "                    'rationale': 'Force additional decomposition to exercise iteration budgets.',",
                "                    'confidence': 0.78,",
                "                    'source_refs': ['FIND-RUNNER-GROWTH'],",
                "                }",
                "            ]",
                "        elif phase == 'research':",
                "            response['research_findings'] = [",
                "                {",
                "                    'finding_id': f'FIND-GROW-{attempt:03d}',",
                "                    'source': 'runner',",
                "                    'source_type': 'web',",
                "                    'summary': f'Iterative finding {attempt} for depth behavior tests.',",
                "                }",
                "            ]",
                "        elif phase == 'question_loop':",
                "            response['questions'] = [",
                "                {",
                "                    'question_id': f'Q-OPTIONAL-{attempt:03d}',",
                "                    'text': f'Optional exploratory question {attempt}.',",
                "                    'required': False,",
                "                }",
                "            ]",
                "    else:",
                "        if phase == 'adaptive_decomposition' and attempt == 1:",
                "            response['decomposition_nodes'] = [",
                "                {",
                "                    'temp_id': 'N-RUNNER-001',",
                "                    'parent_temp_id': 'N-ROOT',",
                "                    'name': 'Runner-Inferred Hardening Track',",
                "                    'node_type': 'capability',",
                "                    'rationale': 'Codex runner inferred a dedicated hardening workstream.',",
                "                    'confidence': 0.81,",
                "                    'source_refs': ['FIND-RUNNER-001'],",
                "                }",
                "            ]",
                "        if phase == 'research' and attempt == 1:",
                "            response['research_findings'] = [",
                "                {",
                "                    'finding_id': 'FIND-RUNNER-001',",
                "                    'source': 'runner',",
                "                    'source_type': 'web',",
                "                    'summary': 'External guidance suggests explicit audit retention controls.',",
                "                }",
                "            ]",
                "        if phase == 'question_loop' and attempt == 1:",
                "            response['questions'] = [",
                "                {",
                "                    'question_id': 'Q-RUNNER-001',",
                "                    'text': 'What audit retention duration should be enforced?',",
                "                    'required': True,",
                "                }",
                "            ]",
                "",
                "    _emit(response)",
                "",
                "",
                "if __name__ == '__main__':",
                "    main()",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _first_epic_dir(root: Path) -> Path:
    return next((root / "docs" / "epics").glob("E-001-*"))


def _parse_json_payload(stdout: str) -> dict:
    decoder = json.JSONDecoder()
    idx = 0
    last_payload: dict | None = None
    while True:
        start = stdout.find("{", idx)
        if start == -1:
            break
        try:
            payload, end = decoder.raw_decode(stdout, start)
        except json.JSONDecodeError:
            idx = start + 1
            continue
        if isinstance(payload, dict):
            last_payload = payload
        idx = end
    assert last_payload is not None
    return last_payload
