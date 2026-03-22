from __future__ import annotations

from dataclasses import dataclass
import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any


SUPPORTED_RUNNER_POLICIES = {"strict", "fallback"}
SUPPORTED_CODEX_SURFACES = {"auto", "app", "cli", "ci"}


@dataclass(frozen=True)
class DepthBehavior:
    reasoning_effort: str
    web_search: str
    max_phase_iterations: int


@dataclass
class RunnerInvocationMeta:
    provider: str
    command: str
    phase: str
    events_count: int = 0
    session_id: str = ""
    thread_id: str = ""
    resumed_from_thread_id: str = ""


DEPTH_BEHAVIORS: dict[str, DepthBehavior] = {
    "deep": DepthBehavior(reasoning_effort="high", web_search="live", max_phase_iterations=3),
    "balanced": DepthBehavior(reasoning_effort="medium", web_search="cached", max_phase_iterations=2),
    "lean": DepthBehavior(reasoning_effort="low", web_search="disabled", max_phase_iterations=1),
}


def behavior_for_depth(depth: str) -> DepthBehavior:
    normalized = (depth or "deep").strip().lower()
    return DEPTH_BEHAVIORS.get(normalized, DEPTH_BEHAVIORS["deep"])


def default_runner_policy(mode: str, runner: str, explicit: str | None) -> str:
    if explicit:
        normalized = explicit.strip().lower()
        if normalized in SUPPORTED_RUNNER_POLICIES:
            return normalized
    if (mode or "").strip().lower() == "agentic" and (runner or "").strip().lower() == "codex":
        return "strict"
    return "fallback"


def validate_codex_surface(surface: str) -> str:
    normalized = (surface or "auto").strip().lower()
    if normalized not in SUPPORTED_CODEX_SURFACES:
        return "auto"
    return normalized


def build_codex_exec_command(*, codex_surface: str, codex_profile: str) -> str:
    surface = validate_codex_surface(codex_surface)
    parts = ["codex", "exec", "--json", "-o"]
    if codex_profile:
        parts.extend(["--profile", codex_profile])
    if surface == "ci":
        parts.extend(["--no-interactive"])
    return " ".join(parts)


def resolve_runner_command(
    runner: str,
    *,
    codex_surface: str = "auto",
    codex_profile: str = "spec-agentic",
) -> str:
    normalized_runner = (runner or "").strip().lower()
    by_runner = os.environ.get(
        f"SPECCTL_AGENTIC_RUNNER_COMMAND_{normalized_runner.upper()}",
        "",
    ).strip()
    if by_runner:
        return by_runner
    global_override = os.environ.get("SPECCTL_AGENTIC_RUNNER_COMMAND", "").strip()
    if global_override:
        return global_override
    if normalized_runner == "codex":
        profile = (codex_profile or "spec-agentic").strip()
        return build_codex_exec_command(codex_surface=codex_surface, codex_profile=profile)
    return ""


def ensure_runner_available(*, runner: str, runner_policy: str, command: str) -> str | None:
    if runner_policy != "strict":
        return None
    if command.strip():
        return None
    return (
        f"Runner command missing for strict policy (runner={runner}). "
        "Set SPECCTL_AGENTIC_RUNNER_COMMAND_<RUNNER> or use --runner-policy fallback."
    )


def invoke_runner_adapter(
    *,
    runner: str,
    command: str,
    payload: dict[str, Any],
    root: Path,
    phase: str,
) -> tuple[dict[str, Any] | None, RunnerInvocationMeta, str | None]:
    meta = RunnerInvocationMeta(provider=runner, command=command, phase=phase)
    stripped = command.strip()
    if not stripped:
        return None, meta, "Runner command is empty"

    try:
        argv = shlex.split(stripped)
    except ValueError as exc:
        return None, meta, f"Invalid runner command syntax: {exc}"

    try:
        proc = subprocess.run(
            argv,
            cwd=root,
            shell=False,
            input=json.dumps(payload, sort_keys=True),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        return None, meta, f"Unable to execute runner command '{argv[0]}': {exc}"

    output = proc.stdout or ""
    stderr_output = proc.stderr or ""
    if proc.returncode != 0:
        failure_output = stderr_output or output
        return None, meta, f"Runner command failed ({proc.returncode}): {failure_output[-2000:]}"

    if runner == "codex":
        normalized, codex_meta, err = parse_codex_jsonl_output(output)
        codex_meta.phase = phase
        codex_meta.command = command
        return normalized, codex_meta, err
    normalized, err = parse_runner_json(output)
    return normalized, meta, err


def parse_runner_json(output: str) -> tuple[dict[str, Any] | None, str | None]:
    output = output.strip()
    if not output:
        return None, "Runner produced empty output"

    payload: Any
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        start = output.find("{")
        end = output.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None, "Runner output does not contain valid JSON"
        try:
            payload = json.loads(output[start : end + 1])
        except json.JSONDecodeError as exc:
            return None, f"Runner JSON parse failure: {exc}"

    if not isinstance(payload, dict):
        return None, "Runner JSON root must be an object"
    return normalize_runner_payload(payload), None


def normalize_runner_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "decomposition_nodes": payload.get("decomposition_nodes", []),
        "research_findings": payload.get("research_findings", []),
        "questions": payload.get("questions", []),
        "feature_synthesis": payload.get("feature_synthesis", []),
    }
    if not isinstance(normalized["decomposition_nodes"], list):
        normalized["decomposition_nodes"] = []
    if not isinstance(normalized["research_findings"], list):
        normalized["research_findings"] = []
    if not isinstance(normalized["questions"], list):
        normalized["questions"] = []
    if not isinstance(normalized["feature_synthesis"], list):
        normalized["feature_synthesis"] = []
    return normalized


def parse_codex_jsonl_output(output: str) -> tuple[dict[str, Any] | None, RunnerInvocationMeta, str | None]:
    meta = RunnerInvocationMeta(provider="codex", command="", phase="")
    lines = [line for line in output.splitlines() if line.strip()]
    meta.events_count = len(lines)

    candidate_message = ""
    for line in lines:
        event: Any
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        _update_codex_meta(meta, event)
        text = _extract_text_candidate(event)
        if text:
            candidate_message = text

    if candidate_message:
        parsed, err = parse_runner_json(candidate_message)
        if err is None and parsed is not None:
            return parsed, meta, None

    parsed, err = parse_runner_json(output)
    return parsed, meta, err


def _update_codex_meta(meta: RunnerInvocationMeta, event: dict[str, Any]) -> None:
    thread_id = _extract_first_str(event, ("thread_id", "threadId"))
    session_id = _extract_first_str(event, ("session_id", "sessionId"))
    resumed_from = _extract_first_str(event, ("resumed_from_thread_id", "resumedFromThreadId"))

    if thread_id:
        meta.thread_id = thread_id
    if session_id:
        meta.session_id = session_id
    if resumed_from:
        meta.resumed_from_thread_id = resumed_from

    thread = event.get("thread")
    if isinstance(thread, dict):
        nested_thread = _extract_first_str(thread, ("id", "thread_id"))
        if nested_thread:
            meta.thread_id = nested_thread
    session = event.get("session")
    if isinstance(session, dict):
        nested_session = _extract_first_str(session, ("id", "session_id"))
        if nested_session:
            meta.session_id = nested_session


def _extract_first_str(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_text_candidate(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        candidate = ""
        for item in value:
            nested = _extract_text_candidate(item)
            if nested:
                candidate = nested
        return candidate
    if isinstance(value, dict):
        for key in (
            "output_text",
            "last_message",
            "message",
            "text",
            "content",
            "final_output",
            "output",
            "item",
            "response",
            "data",
        ):
            if key not in value:
                continue
            nested = _extract_text_candidate(value[key])
            if nested:
                return nested
    return ""
