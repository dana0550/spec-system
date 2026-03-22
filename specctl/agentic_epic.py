from __future__ import annotations

from dataclasses import dataclass
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from specctl.constants import AGENTIC_DESIGN_REQUIRED_SECTIONS, AGENTIC_QUALITY_MINIMUMS
from specctl.io_utils import now_date, now_timestamp, read_text, write_text
from specctl.models import FeatureRow
from specctl.runner_adapter import resolve_runner_command as resolve_runner_command_impl


@dataclass
class AgenticQuestion:
    question_id: str
    text: str
    required: bool = True
    source: str = "system"


def resolve_runner_command(
    runner: str,
    *,
    codex_surface: str = "auto",
    codex_profile: str = "spec-agentic",
) -> str:
    return resolve_runner_command_impl(
        runner,
        codex_surface=codex_surface,
        codex_profile=codex_profile,
    )


def load_answers_file(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    data: Any
    if path.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(raw)
    else:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        return {}
    answers: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, (str, int, float, bool)):
            answers[key] = str(value).strip()
    return answers


def collect_repo_findings(root: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    docs = root / "docs"
    for idx, path in enumerate([docs / "MASTER_SPEC.md", docs / "STEERING.md"], start=1):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        first_heading = _first_heading(text) or path.name
        findings.append(
            {
                "finding_id": f"FIND-LOCAL-{idx:03d}",
                "source": str(path.relative_to(root)),
                "summary": f"Key context extracted from {first_heading}",
                "source_type": "repo",
            }
        )
    return findings


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return None


def build_adaptive_nodes(
    *,
    brief_sections: dict[str, str],
    root_feature_name: str,
    root_feature_id: str,
    source_refs: list[str],
) -> list[dict[str, Any]]:
    outcomes = _extract_bullets(brief_sections.get("Outcomes", ""))
    journeys = _extract_bullets(brief_sections.get("User Journeys", ""))
    seed_names = journeys if journeys else outcomes
    if not seed_names:
        seed_names = ["Core Capability"]

    nodes: list[dict[str, Any]] = [
        {
            "temp_id": "N-ROOT",
            "parent_temp_id": "",
            "name": root_feature_name,
            "node_type": "epic_root",
            "rationale": "Root planning anchor for epic scope and traceability.",
            "confidence": 0.85,
            "source_refs": list(source_refs),
        }
    ]

    for idx, seed in enumerate(seed_names, start=1):
        journey_temp = f"N-J{idx:03d}"
        nodes.append(
            {
                "temp_id": journey_temp,
                "parent_temp_id": "N-ROOT",
                "name": seed,
                "node_type": "journey",
                "rationale": "Derived from epic user journey/outcome decomposition.",
                "confidence": 0.8,
                "source_refs": list(source_refs),
            }
        )
        capabilities = infer_capabilities(seed + "\n" + brief_sections.get("Constraints", ""))
        for c_idx, capability in enumerate(capabilities, start=1):
            nodes.append(
                {
                    "temp_id": f"N-J{idx:03d}-C{c_idx:03d}",
                    "parent_temp_id": journey_temp,
                    "name": f"{seed} - {capability}",
                    "node_type": "capability",
                    "rationale": "Adaptive capability inferred from brief language and constraints.",
                    "confidence": 0.72,
                    "source_refs": list(source_refs),
                }
            )

    # Ensure root feature ID is represented explicitly for downstream mapping.
    nodes[0]["feature_id_hint"] = root_feature_id
    return nodes


def infer_capabilities(text: str) -> list[str]:
    lower = text.lower()
    capabilities: list[str] = []

    keyword_capabilities = [
        ({"api", "contract", "endpoint"}, "Contract/API Control Plane"),
        ({"data", "storage", "schema", "database"}, "Domain Data Model"),
        ({"integration", "queue", "webhook", "sync", "job"}, "Integration Execution Flow"),
        ({"metric", "observability", "monitor", "log", "alert"}, "Observability and Reliability"),
        ({"ui", "frontend", "dashboard", "screen", "workflow", "form"}, "UX Interaction and States"),
        ({"security", "auth", "privacy", "compliance"}, "Security and Compliance Controls"),
    ]
    for keywords, capability in keyword_capabilities:
        if any(re.search(rf"\b{re.escape(token)}\b", lower) for token in keywords):
            capabilities.append(capability)

    if not capabilities:
        capabilities = [
            "Core Domain Workflow",
            "Integration Execution Flow",
            "Observability and Reliability",
        ]

    return _dedupe_preserve_order(capabilities)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _extract_bullets(section_text: str) -> list[str]:
    bullets: list[str] = []
    for line in section_text.splitlines():
        match = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
        if match:
            bullets.append(match.group(1).strip())
    return bullets


def default_questions(root_name: str, brief_sections: dict[str, str]) -> list[AgenticQuestion]:
    questions = [
        AgenticQuestion(
            question_id="Q-AGENTIC-001",
            text=f"What is the single most important KPI for epic '{root_name}'?",
            required=True,
            source="kpi",
        ),
        AgenticQuestion(
            question_id="Q-AGENTIC-002",
            text="List any security/compliance constraints not already covered in the brief.",
            required=True,
            source="constraints",
        ),
    ]

    journeys = _extract_bullets(brief_sections.get("User Journeys", ""))
    for idx, journey in enumerate(journeys, start=1):
        questions.append(
            AgenticQuestion(
                question_id=f"Q-AGENTIC-J{idx:03d}",
                text=f"Any edge-case acceptance criteria to enforce for journey '{journey}'?",
                required=False,
                source="journey",
            )
        )
    return questions


def merge_questions(base: list[AgenticQuestion], runner_questions: list[dict[str, Any]]) -> list[AgenticQuestion]:
    merged = list(base)
    known_ids = {q.question_id for q in merged}
    for idx, item in enumerate(runner_questions, start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        question_id = str(item.get("question_id", f"Q-RUNNER-{idx:03d}")).strip() or f"Q-RUNNER-{idx:03d}"
        if question_id in known_ids:
            continue
        required = bool(item.get("required", True))
        merged.append(AgenticQuestion(question_id=question_id, text=text, required=required, source="runner"))
        known_ids.add(question_id)
    return merged


def resolve_questions(
    *,
    questions: list[AgenticQuestion],
    seed_answers: dict[str, str],
    interactive: bool,
) -> tuple[dict[str, str], list[AgenticQuestion]]:
    answers = dict(seed_answers)
    pending: list[AgenticQuestion] = []

    for question in questions:
        existing = answers.get(question.question_id, "").strip()
        if existing:
            continue
        if interactive:
            response = _prompt_question(question)
            if response:
                answers[question.question_id] = response
                continue
        if question.required:
            pending.append(question)

    return answers, pending


def _prompt_question(question: AgenticQuestion) -> str:
    print(f"[QUESTION] {question.question_id}: {question.text}")
    try:
        return input("> ").strip()
    except EOFError:
        return ""


def ask_approval_gate(*, gate_id: str, prompt: str, interactive: bool, seed_answers: dict[str, str]) -> tuple[bool, dict[str, str]]:
    answers = dict(seed_answers)
    existing = answers.get(gate_id, "").strip().lower()
    if existing in {"y", "yes", "approved", "true", "1"}:
        return True, answers
    if existing in {"n", "no", "false", "0", "rejected"}:
        return False, answers
    if not interactive:
        return False, answers

    print(f"[APPROVAL] {prompt} [y/N]")
    try:
        response = input("> ").strip().lower()
    except EOFError:
        response = ""
    answers[gate_id] = response
    return response in {"y", "yes"}, answers


def is_interactive_mode(force_on: bool, force_off: bool) -> bool:
    if force_on:
        return True
    if force_off:
        return False
    return sys.stdin.isatty()


def write_question_pack(path: Path, *, epic_name: str, questions: list[AgenticQuestion], answers: dict[str, str]) -> None:
    payload = {
        "epic_name": epic_name,
        "generated_at": now_timestamp(),
        "questions": [
            {
                "question_id": question.question_id,
                "text": question.text,
                "required": question.required,
                "source": question.source,
            }
            for question in questions
        ],
        "answers": answers,
    }
    write_text(path, yaml.safe_dump(payload, sort_keys=True, allow_unicode=False))


def write_agentic_artifacts(
    epic_dir: Path,
    *,
    findings: list[dict[str, str]],
    questions: list[AgenticQuestion],
    answers: dict[str, str],
    pending_questions: list[AgenticQuestion],
    state: dict[str, Any],
) -> None:
    research_path = epic_dir / "research.md"
    questions_path = epic_dir / "questions.yaml"
    answers_path = epic_dir / "answers.yaml"
    state_path = epic_dir / "agentic_state.json"

    write_text(research_path, render_research_log(findings))

    question_payload = {
        "generated_at": now_timestamp(),
        "questions": [
            {
                "question_id": q.question_id,
                "text": q.text,
                "required": q.required,
                "source": q.source,
                "status": "pending" if any(p.question_id == q.question_id for p in pending_questions) else "answered",
            }
            for q in questions
        ],
    }
    write_text(questions_path, yaml.safe_dump(question_payload, sort_keys=True, allow_unicode=False))
    write_text(answers_path, yaml.safe_dump(answers, sort_keys=True, allow_unicode=False))
    write_text(state_path, json.dumps(state, indent=2, sort_keys=True) + "\n")


def render_research_log(findings: list[dict[str, str]]) -> str:
    lines = [
        "# Research Log",
        "",
        "This file is the canonical source attribution log for agentic epic synthesis.",
        "",
        "| Finding ID | Source | Type | Summary |",
        "|---|---|---|---|",
    ]
    if not findings:
        lines.append("| FIND-LOCAL-000 | brief.md | brief | No external findings recorded. |")
    else:
        for finding in findings:
            finding_id = str(finding.get("finding_id", "")).strip() or "FIND-UNKNOWN"
            source = str(finding.get("source", "")).strip() or "unknown"
            source_type = str(finding.get("source_type", "")).strip() or "unknown"
            summary = str(finding.get("summary", "")).strip() or "No summary"
            lines.append(f"| {finding_id} | {source} | {source_type} | {summary} |")
    lines.append("")
    return "\n".join(lines)


def synthesize_feature_artifacts(
    *,
    row: FeatureRow,
    owner: str,
    root_feature_name: str,
    findings: list[dict[str, str]],
    answers: dict[str, str],
) -> dict[str, str]:
    digits = row.feature_id.replace("-", "")
    status = row.status
    feature_name = row.name
    answer_kpi = answers.get("Q-AGENTIC-001", "Primary KPI to be confirmed during implementation")
    answer_constraints = answers.get("Q-AGENTIC-002", "No additional constraints provided")

    r1 = f"R-{digits}-001"
    r2 = f"R-{digits}-002"
    r3 = f"R-{digits}-003"
    s1 = f"S-{digits}-001"
    s2 = f"S-{digits}-002"
    d1 = f"D-{digits}-001"
    d2 = f"D-{digits}-002"
    t1 = f"T-{digits}-001"
    t2 = f"T-{digits}-002"
    t3 = f"T-{digits}-003"

    finding_refs = ", ".join(finding.get("finding_id", "") for finding in findings[:3] if finding.get("finding_id"))
    finding_note = finding_refs or "FIND-LOCAL-000"

    requirements = "\n".join(
        [
            "---",
            "doc_type: feature_requirements",
            f"feature_id: {row.feature_id}",
            f"name: {feature_name}",
            f"status: {status}",
            f"owner: {owner}",
            f"last_updated: {now_date()}",
            "---",
            f"# {feature_name} Requirements",
            "",
            f"- {r1}: WHEN a user triggers {feature_name.lower()}, the system MUST complete the core flow and report outcome success state.",
            f"- {r2}: IF a downstream dependency fails during {feature_name.lower()}, the system MUST preserve state integrity and return a recoverable failure signal.",
            f"- {r3}: WHILE {feature_name.lower()} is executing, the system SHOULD emit observable progress events aligned to KPI '{answer_kpi}'.",
            f"- {s1}: Given valid prerequisites When {feature_name.lower()} is submitted Then the system completes successfully with expected observable outputs.",
            f"- {s2}: Given a downstream fault When {feature_name.lower()} is executed Then the system returns a recoverable error and keeps persistent state consistent.",
            "",
            "## Notes",
            f"- Root Epic: {root_feature_name}",
            f"- Additional Constraints: {answer_constraints}",
            f"- Research References: {finding_note}",
            "",
        ]
    )

    design = "\n".join(
        [
            "---",
            "doc_type: feature_design",
            f"feature_id: {row.feature_id}",
            f"status: {status}",
            f"last_updated: {now_date()}",
            "---",
            f"# {feature_name} Design",
            "",
            "## Architecture",
            f"- {d1}: Implement {r1} through an explicit orchestrator boundary with idempotent command handling.",
            "",
            "## Contracts and Data",
            f"- {d2}: Implement {r2} using typed request/response envelopes with failure categories and persisted checkpoint metadata.",
            "",
            "## UX Behavior",
            f"- Surface deterministic user-visible state transitions tied to {r3}.",
            "",
            "## Observability",
            f"- Emit metrics and structured logs for {r3} with correlation IDs and outcome counters.",
            "",
            "## Risks and Tradeoffs",
            "- Strong consistency paths may increase latency; prefer correctness over throughput for critical flows.",
            "",
            "## Requirement Mapping",
            f"- {r1} -> {d1}",
            f"- {r2} -> {d2}",
            f"- {r3} -> {d1}, {d2}",
            "",
        ]
    )

    tasks = "\n".join(
        [
            "---",
            "doc_type: feature_tasks",
            f"feature_id: {row.feature_id}",
            f"status: {status}",
            f"last_updated: {now_date()}",
            "---",
            f"# {feature_name} Tasks",
            "",
            f"- [ ] {t1} Implement orchestrated success path (R: {r1}, D: {d1})",
            f"- [ ] {t2} Implement recoverable failure handling and state protection (R: {r2}, D: {d2})",
            f"- [ ] {t3} Implement metrics/logging and acceptance instrumentation (R: {r3}, D: {d1})",
            "",
        ]
    )

    verification = "\n".join(
        [
            "---",
            "doc_type: feature_verification",
            f"feature_id: {row.feature_id}",
            f"status: {status}",
            f"last_updated: {now_date()}",
            "---",
            f"# {feature_name} Verification",
            "",
            f"- {s1}: Given valid prerequisites When {feature_name.lower()} is submitted Then the system completes successfully with expected observable outputs.",
            f"Evidence: {s1} -> planned:test/{s1.lower()}-happy-path",
            f"- {s2}: Given a downstream fault When {feature_name.lower()} is executed Then the system returns a recoverable error and keeps persistent state consistent.",
            f"Evidence: {s2} -> planned:test/{s2.lower()}-failure-path",
            "",
        ]
    )

    return {
        "requirements.md": requirements,
        "design.md": design,
        "tasks.md": tasks,
        "verification.md": verification,
    }


def count_requirements(requirements_text: str) -> tuple[int, int]:
    req_count = 0
    scenario_count = 0
    for line in requirements_text.splitlines():
        if re.match(r"^\s*[-*]\s*R-F\d{3}(?:\.\d{2,})*-\d{3}\s*:", line):
            req_count += 1
        if re.match(r"^\s*[-*]\s*S-F\d{3}(?:\.\d{2,})*-\d{3}\s*:", line):
            scenario_count += 1
    return req_count, scenario_count


def count_design_decisions(design_text: str) -> int:
    count = 0
    for line in design_text.splitlines():
        if re.match(r"^\s*[-*]\s*D-F\d{3}(?:\.\d{2,})*-\d{3}\s*:", line):
            count += 1
    return count


def count_tasks(tasks_text: str) -> int:
    count = 0
    for line in tasks_text.splitlines():
        if re.match(r"^\s*[-*]\s*\[[ xX]\]\s*T-F\d{3}(?:\.\d{2,})*-\d{3}\b", line):
            count += 1
    return count


def verify_design_sections(design_text: str) -> list[str]:
    missing: list[str] = []
    for section in AGENTIC_DESIGN_REQUIRED_SECTIONS:
        if f"## {section}" not in design_text:
            missing.append(section)
    return missing


def has_tbd_evidence(verification_text: str) -> bool:
    for line in verification_text.splitlines():
        if not line.strip().startswith("Evidence:"):
            continue
        if "TBD" in line.upper():
            return True
    return False


def validate_feature_quality(feature_dir: Path) -> list[str]:
    issues: list[str] = []
    req_path = feature_dir / "requirements.md"
    design_path = feature_dir / "design.md"
    tasks_path = feature_dir / "tasks.md"
    verification_path = feature_dir / "verification.md"

    if not req_path.exists() or not design_path.exists() or not tasks_path.exists() or not verification_path.exists():
        return ["Missing one or more required feature files"]

    req_text = req_path.read_text(encoding="utf-8")
    design_text = design_path.read_text(encoding="utf-8")
    tasks_text = tasks_path.read_text(encoding="utf-8")
    verification_text = verification_path.read_text(encoding="utf-8")

    req_count, scenario_count = count_requirements(req_text)
    if req_count < AGENTIC_QUALITY_MINIMUMS["requirements"]:
        issues.append(f"requirements count {req_count} < {AGENTIC_QUALITY_MINIMUMS['requirements']}")
    if scenario_count < AGENTIC_QUALITY_MINIMUMS["scenarios"]:
        issues.append(f"scenarios count {scenario_count} < {AGENTIC_QUALITY_MINIMUMS['scenarios']}")

    decision_count = count_design_decisions(design_text)
    if decision_count < AGENTIC_QUALITY_MINIMUMS["design_decisions"]:
        issues.append(
            f"design decisions count {decision_count} < {AGENTIC_QUALITY_MINIMUMS['design_decisions']}"
        )

    task_count = count_tasks(tasks_text)
    if task_count < AGENTIC_QUALITY_MINIMUMS["tasks"]:
        issues.append(f"tasks count {task_count} < {AGENTIC_QUALITY_MINIMUMS['tasks']}")

    missing_sections = verify_design_sections(design_text)
    if missing_sections:
        issues.append("design missing sections: " + ", ".join(missing_sections))

    if has_tbd_evidence(verification_text):
        issues.append("verification evidence contains TBD markers")

    return issues
