from __future__ import annotations

import json

from specctl.runner_adapter import (
    behavior_for_depth,
    build_codex_exec_command,
    default_runner_policy,
    parse_codex_jsonl_output,
    parse_runner_json,
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
