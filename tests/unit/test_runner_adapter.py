from __future__ import annotations

import json
from pathlib import Path

from specctl.runner_adapter import (
    behavior_for_depth,
    build_codex_exec_command,
    default_runner_policy,
    invoke_runner_adapter,
    parse_codex_jsonl_output,
    parse_runner_json,
    resolve_runner_command,
)


def test_behavior_for_depth_maps_profiles() -> None:
    deep = behavior_for_depth("deep")
    balanced = behavior_for_depth("balanced")
    lean = behavior_for_depth("lean")
    fallback = behavior_for_depth("unknown")

    assert deep.reasoning_effort == "high"
    assert deep.web_search == "live"
    assert deep.max_phase_iterations == 3
    assert balanced.reasoning_effort == "medium"
    assert lean.reasoning_effort == "low"
    assert fallback == deep


def test_default_runner_policy_prefers_strict_for_agentic_codex() -> None:
    assert default_runner_policy("agentic", "codex", None) == "strict"
    assert default_runner_policy("agentic", "claude", None) == "fallback"
    assert default_runner_policy("deterministic", "codex", None) == "fallback"
    assert default_runner_policy("agentic", "codex", "fallback") == "fallback"


def test_build_codex_exec_command_uses_profile_and_surface() -> None:
    assert build_codex_exec_command(codex_surface="auto", codex_profile="spec-agentic") == "codex exec --json -o --profile spec-agentic"
    assert "--no-interactive" in build_codex_exec_command(codex_surface="ci", codex_profile="spec-ci")


def test_resolve_runner_command_precedence(monkeypatch) -> None:
    monkeypatch.delenv("SPECCTL_AGENTIC_RUNNER_COMMAND_CODEX", raising=False)
    monkeypatch.delenv("SPECCTL_AGENTIC_RUNNER_COMMAND", raising=False)
    assert resolve_runner_command("codex", codex_surface="ci", codex_profile="spec-ci") == (
        "codex exec --json -o --profile spec-ci --no-interactive"
    )

    monkeypatch.setenv("SPECCTL_AGENTIC_RUNNER_COMMAND", "global-runner")
    assert resolve_runner_command("codex", codex_surface="ci", codex_profile="spec-ci") == "global-runner"

    monkeypatch.setenv("SPECCTL_AGENTIC_RUNNER_COMMAND_CODEX", "runner-specific")
    assert resolve_runner_command("codex", codex_surface="ci", codex_profile="spec-ci") == "runner-specific"

    monkeypatch.delenv("SPECCTL_AGENTIC_RUNNER_COMMAND_CODEX", raising=False)
    monkeypatch.delenv("SPECCTL_AGENTIC_RUNNER_COMMAND", raising=False)
    assert resolve_runner_command("claude", codex_surface="ci", codex_profile="spec-ci") == ""
def test_parse_codex_jsonl_output_extracts_runner_payload_and_state() -> None:
    payload = {
        "decomposition_nodes": [{"temp_id": "N-ROOT", "name": "Root"}],
        "research_findings": [{"finding_id": "FIND-001", "summary": "Summary"}],
        "questions": [{"question_id": "Q-001", "text": "Question"}],
        "feature_synthesis": [],
    }
    output = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "th_123", "session_id": "se_123"}),
            json.dumps(
                {
                    "type": "thread.message",
                    "message": {
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(payload),
                            }
                        ]
                    },
                }
            ),
        ]
    )

    normalized, meta, err = parse_codex_jsonl_output(output)
    assert err is None
    assert normalized is not None
    assert normalized["decomposition_nodes"][0]["temp_id"] == "N-ROOT"
    assert meta.thread_id == "th_123"
    assert meta.session_id == "se_123"


def test_parse_codex_jsonl_output_handles_variant_event_shapes_and_noise() -> None:
    payload = {
        "decomposition_nodes": [{"temp_id": "N-ALT", "name": "AltRoot"}],
        "research_findings": [{"finding_id": "FIND-ALT-001", "summary": "Alt Summary"}],
        "questions": [{"question_id": "Q-ALT-001", "text": "Alt Question"}],
        "feature_synthesis": [],
    }
    output = "\n".join(
        [
            "non-json line",
            json.dumps({"type": "thread.started", "threadId": "th_camel", "sessionId": "se_camel"}),
            json.dumps({"type": "thread.message", "data": {"item": {"response": {"output_text": json.dumps(payload)}}}}),
            json.dumps({"type": "thread.message", "thread": {"id": "th_nested"}, "session": {"id": "se_nested"}}),
        ]
    )

    normalized, meta, err = parse_codex_jsonl_output(output)
    assert err is None
    assert normalized is not None
    assert normalized["decomposition_nodes"][0]["temp_id"] == "N-ALT"
    assert meta.thread_id == "th_nested"
    assert meta.session_id == "se_nested"
    assert meta.events_count == 4


def test_parse_codex_jsonl_output_uses_last_valid_payload_from_mixed_stream() -> None:
    first = {
        "decomposition_nodes": [{"temp_id": "N-OLD", "name": "Old"}],
        "research_findings": [],
        "questions": [],
        "feature_synthesis": [],
    }
    last = {
        "decomposition_nodes": [{"temp_id": "N-NEW", "name": "New"}],
        "research_findings": [{"finding_id": "FIND-NEW-001", "summary": "Newest"}],
        "questions": [],
        "feature_synthesis": [],
    }
    output = "\n".join(
        [
            json.dumps({"type": "thread.message", "message": {"content": [{"type": "output_text", "text": json.dumps(first)}]}}),
            json.dumps({"type": "thread.message", "message": {"content": [{"type": "output_text", "text": "not-json"}]}}),
            json.dumps({"type": "thread.message", "message": {"content": [{"type": "output_text", "text": json.dumps(last)}]}}),
            "trailing noise",
        ]
    )
    normalized, _, err = parse_codex_jsonl_output(output)
    assert err is None
    assert normalized is not None
    assert normalized["decomposition_nodes"][0]["temp_id"] == "N-NEW"
    assert normalized["research_findings"][0]["finding_id"] == "FIND-NEW-001"


def test_parity_normalization_between_json_and_codex_jsonl() -> None:
    payload = {
        "decomposition_nodes": [{"temp_id": "N-ROOT", "name": "Root"}],
        "research_findings": [{"finding_id": "FIND-001", "summary": "Summary"}],
        "questions": [{"question_id": "Q-001", "text": "Question"}],
        "feature_synthesis": [{"feature_id": "F-001", "requirements": []}],
    }

    direct, direct_err = parse_runner_json(json.dumps(payload))
    codex, _, codex_err = parse_codex_jsonl_output(
        json.dumps(
            {
                "type": "thread.message",
                "message": {"content": [{"type": "output_text", "text": json.dumps(payload)}]},
            }
        )
    )
    assert direct_err is None
    assert codex_err is None
    assert codex == direct


def test_invoke_runner_adapter_preserves_codex_meta_on_parse_error(monkeypatch) -> None:
    command = "codex exec --json -o"
    output = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "th_123", "session_id": "se_123"}),
            json.dumps(
                {
                    "type": "thread.message",
                    "message": {"content": [{"type": "output_text", "text": "not-json"}]},
                }
            ),
        ]
    )

    class _Proc:
        returncode = 0
        stdout = output
        stderr = ""

    def _fake_run(*_args, **_kwargs):
        return _Proc()

    monkeypatch.setattr("specctl.runner_adapter.subprocess.run", _fake_run)

    normalized, meta, err = invoke_runner_adapter(
        runner="codex",
        command=command,
        payload={"phase": "requirements"},
        root=Path("."),
        phase="requirements",
    )

    assert normalized is None
    assert err is not None
    assert meta.thread_id == "th_123"
    assert meta.session_id == "se_123"
    assert meta.events_count == 2
    assert meta.phase == "requirements"
    assert meta.command == command


def test_invoke_runner_adapter_ignores_stderr_when_parsing_json(monkeypatch) -> None:
    payload = {
        "decomposition_nodes": [{"temp_id": "N-ROOT", "name": "Root"}],
        "research_findings": [],
        "questions": [],
        "feature_synthesis": [],
    }

    class _Proc:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = "warning: debug {noise}"

    def _fake_run(*_args, **_kwargs):
        return _Proc()

    monkeypatch.setattr("specctl.runner_adapter.subprocess.run", _fake_run)

    normalized, _, err = invoke_runner_adapter(
        runner="claude",
        command="runner",
        payload={"phase": "design"},
        root=Path("."),
        phase="design",
    )

    assert err is None
    assert normalized is not None
    assert normalized["decomposition_nodes"][0]["temp_id"] == "N-ROOT"
