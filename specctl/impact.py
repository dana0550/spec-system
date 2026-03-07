from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from specctl.feature_index import read_feature_rows
from specctl.io_utils import now_timestamp, read_text, write_text
from specctl.models import FeatureRow, ImpactScanResult, ImpactSuspect, LintMessage
from specctl.validators.ids import DESIGN_ID_RE, REQ_ID_RE, SCENARIO_ID_RE, TASK_ID_RE


BASELINE_SCHEMA_VERSION = "1"
BASELINE_RELATIVE_PATH = Path("docs/.specctl/impact-baseline.json")

REQ_LINE_RE = re.compile(r"^\s*[-*]\s*(R-F\d{3}(?:\.\d{2})*-\d{3})\s*:\s*(.+)$")
SCENARIO_LINE_RE = re.compile(r"^\s*[-*]\s*(S-F\d{3}(?:\.\d{2})*-\d{3})\s*:\s*(.+)$")
DESIGN_LINE_RE = re.compile(r"^\s*[-*]\s*(D-F\d{3}(?:\.\d+)*-\d{3,})\s*:\s*(.+)$")
EVIDENCE_LINE_RE = re.compile(r"^\s*Evidence:\s*(S-F\d{3}(?:\.\d{2})*-\d{3})\s*->\s*(.+)$")

PROPAGATION_ELIGIBLE_TYPES = {"design", "task", "evidence"}
UPSTREAM_MISSING_SENTINEL = "__MISSING__"


def impact_baseline_path(root: Path) -> Path:
    return root / BASELINE_RELATIVE_PATH


def scan_impact(root: Path, feature_ids: set[str] | None = None) -> ImpactScanResult:
    rows = read_feature_rows(root / "docs" / "FEATURES.md")
    if feature_ids is None:
        selected_rows = rows
    else:
        selected_rows = [row for row in rows if row.feature_id in feature_ids]
    selected_feature_ids = {row.feature_id for row in selected_rows}
    current_graph = _build_current_graph(root, selected_rows)

    baseline_path = impact_baseline_path(root)
    baseline_payload, baseline_error = _load_baseline_payload(baseline_path)
    if baseline_payload is None:
        status = "missing" if baseline_error == "missing" else "invalid"
        error_text = (
            "Impact baseline missing. Run `specctl impact refresh --root .`."
            if status == "missing"
            else f"Impact baseline is invalid: {baseline_error}"
        )
        return ImpactScanResult(
            baseline_status=status,
            features_scanned=len(selected_feature_ids),
            features_tracked=0,
            suspects=(),
            baseline_error=error_text,
        )

    baseline_features = _coerce_baseline_features(baseline_payload.get("features", {}))
    suspects = _compute_suspects(
        current_graph=current_graph,
        baseline_features=baseline_features,
        selected_feature_ids=selected_feature_ids,
        include_removed_features=(feature_ids is None),
    )
    return ImpactScanResult(
        baseline_status="ok",
        features_scanned=len(selected_feature_ids),
        features_tracked=len(baseline_features),
        suspects=tuple(suspects),
        baseline_error=None,
    )


def refresh_impact_baseline(
    root: Path,
    *,
    feature_ids: set[str] | None = None,
    ack_upstream: bool = False,
) -> tuple[int, str, tuple[ImpactSuspect, ...], int]:
    rows = read_feature_rows(root / "docs" / "FEATURES.md")
    row_by_id = {row.feature_id: row for row in rows}
    target_feature_ids = set(row_by_id) if feature_ids is None else set(feature_ids)
    missing_features = sorted(fid for fid in target_feature_ids if fid not in row_by_id)
    if missing_features:
        return 1, f"Feature ID not found: {missing_features[0]}", (), 0

    selected_rows = [row_by_id[fid] for fid in sorted(target_feature_ids)]
    current_graph = _build_current_graph(root, selected_rows)
    baseline_path = impact_baseline_path(root)

    existing_payload, baseline_error = _load_baseline_payload(baseline_path)
    if existing_payload is None and baseline_error not in {None, "missing"}:
        return 2, f"Impact baseline is invalid: {baseline_error}", (), 0
    existing_features = (
        _coerce_baseline_features(existing_payload.get("features", {}))
        if existing_payload is not None
        else {}
    )

    bootstrap_mode = existing_payload is None
    candidate_features: dict[str, dict[str, Any]] = {}

    if feature_ids is not None:
        for feature_id, feature_payload in existing_features.items():
            if feature_id in target_feature_ids:
                continue
            candidate_features[feature_id] = _normalize_feature_payload(feature_payload)

    for feature_id in sorted(target_feature_ids):
        nodes = current_graph.get(feature_id, {})
        old_nodes = existing_features.get(feature_id, {}).get("nodes", {})
        candidate_nodes: dict[str, dict[str, Any]] = {}
        for entity_id in sorted(nodes):
            node = nodes[entity_id]
            old_node = old_nodes.get(entity_id, {})
            old_reviewed = old_node.get("reviewed_upstream_hashes", {})
            reviewed_hashes = _build_reviewed_hashes(
                node=node,
                current_nodes=nodes,
                old_node=old_node,
                old_reviewed=old_reviewed,
                bootstrap_mode=bootstrap_mode,
                ack_upstream=ack_upstream,
            )
            candidate_nodes[entity_id] = {
                "entity_type": node["entity_type"],
                "hash": node["hash"],
                "path": node["path"],
                "line": node["line"],
                "references": list(node["references"]),
                "reviewed_upstream_hashes": reviewed_hashes,
            }
        candidate_features[feature_id] = {"nodes": candidate_nodes}

    if feature_ids is None:
        # Full refresh prunes stale features that no longer exist in FEATURES.md.
        candidate_features = {feature_id: candidate_features[feature_id] for feature_id in sorted(target_feature_ids)}

    payload_features = {feature_id: candidate_features[feature_id] for feature_id in sorted(candidate_features)}
    generated_at = now_timestamp()
    if existing_payload is not None:
        existing_normalized = _coerce_baseline_features(existing_payload.get("features", {}))
        payload_normalized = _coerce_baseline_features(payload_features)
        if existing_normalized == payload_normalized:
            existing_generated_at = existing_payload.get("generated_at")
            if isinstance(existing_generated_at, str) and existing_generated_at:
                generated_at = existing_generated_at

    payload = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "features": payload_features,
    }
    write_text(baseline_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")

    post_refresh_suspects = tuple(
        _compute_suspects(
            current_graph=current_graph,
            baseline_features=_coerce_baseline_features(payload.get("features", {})),
            selected_feature_ids=target_feature_ids,
            include_removed_features=False,
        )
    )
    upstream_only = tuple(s for s in post_refresh_suspects if s.reason == "upstream_changed")
    if upstream_only and not ack_upstream:
        return (
            1,
            "Propagated suspects remain. Update downstream artifacts or rerun with --ack-upstream.",
            upstream_only,
            len(target_feature_ids),
        )
    if post_refresh_suspects:
        return (
            1,
            "Impact baseline refresh completed, but suspects remain.",
            post_refresh_suspects,
            len(target_feature_ids),
        )
    return 0, "Impact baseline refreshed.", (), len(target_feature_ids)


def build_gate_messages(root: Path, feature_ids: set[str], command_name: str) -> list[LintMessage]:
    scan = scan_impact(root, feature_ids=feature_ids)
    baseline_path = impact_baseline_path(root)
    if scan.baseline_status != "ok":
        remediation = "Run `specctl impact refresh --root .`."
        baseline_error = scan.baseline_error or "Impact baseline missing or invalid."
        if remediation in baseline_error:
            message = f"{command_name} blocked: {baseline_error}"
        else:
            message = f"{command_name} blocked: {baseline_error} {remediation}"
        return [
            LintMessage(
                severity="ERROR",
                code="IMPACT_BASELINE_MISSING",
                message=message,
                path=baseline_path,
            )
        ]

    if not scan.suspects:
        return []

    messages = [
        LintMessage(
            severity="ERROR",
            code="IMPACT_SUSPECT_OPEN",
            message=(
                f"{command_name} blocked: {len(scan.suspects)} impact suspect(s) open. "
                "Run `specctl impact scan --root .`."
            ),
        )
    ]
    for suspect in scan.suspects:
        upstream_text = ", ".join(suspect.upstream_ids) if suspect.upstream_ids else "none"
        messages.append(
            LintMessage(
                severity="ERROR",
                code="IMPACT_SUSPECT_OPEN",
                message=(
                    f"{suspect.entity_type}:{suspect.entity_id} reason={suspect.reason} "
                    f"upstream={upstream_text}"
                ),
                path=root / suspect.path,
                line=suspect.line,
            )
        )
    return messages


def build_lint_messages(root: Path, scan: ImpactScanResult) -> list[LintMessage]:
    baseline_path = impact_baseline_path(root)
    if scan.baseline_status != "ok":
        return [
            LintMessage(
                severity="WARN",
                code="IMPACT_BASELINE_MISSING",
                message=scan.baseline_error or "Impact baseline missing or invalid.",
                path=baseline_path,
            )
        ]
    if not scan.suspects:
        return []
    return [
        LintMessage(
            severity="WARN",
            code="IMPACT_SUSPECT_OPEN",
            message=(
                f"{len(scan.suspects)} impact suspect(s) open. "
                "Run `specctl impact scan --root .`."
            ),
            path=baseline_path,
        )
    ]


def suspects_to_json(suspects: tuple[ImpactSuspect, ...]) -> list[dict[str, Any]]:
    return [
        {
            "feature_id": suspect.feature_id,
            "entity_type": suspect.entity_type,
            "entity_id": suspect.entity_id,
            "reason": suspect.reason,
            "upstream_ids": list(suspect.upstream_ids),
            "path": suspect.path,
            "line": suspect.line,
        }
        for suspect in suspects
    ]


def _build_reviewed_hashes(
    *,
    node: dict[str, Any],
    current_nodes: dict[str, dict[str, Any]],
    old_node: dict[str, Any],
    old_reviewed: dict[str, Any],
    bootstrap_mode: bool,
    ack_upstream: bool,
) -> dict[str, str]:
    refs = node.get("references", [])
    if not refs:
        return {}

    old_refs_raw = old_node.get("references", [])
    if isinstance(old_refs_raw, list):
        old_refs = sorted({str(ref) for ref in old_refs_raw if isinstance(ref, str)})
    else:
        old_refs = []
    downstream_changed = (
        str(node.get("hash", "")) != str(old_node.get("hash", ""))
        or sorted(set(refs)) != old_refs
    )

    reviewed: dict[str, str] = {}
    for upstream_id in refs:
        upstream_hash = _upstream_hash(current_nodes, upstream_id)
        if bootstrap_mode or ack_upstream or downstream_changed:
            reviewed[upstream_id] = upstream_hash
            continue
        if upstream_id in old_reviewed:
            reviewed[upstream_id] = str(old_reviewed[upstream_id])
        else:
            reviewed[upstream_id] = upstream_hash
    return reviewed


def _upstream_hash(nodes: dict[str, dict[str, Any]], upstream_id: str) -> str:
    upstream_node = nodes.get(upstream_id)
    if upstream_node is None:
        return UPSTREAM_MISSING_SENTINEL
    return str(upstream_node.get("hash", UPSTREAM_MISSING_SENTINEL))


def _compute_suspects(
    *,
    current_graph: dict[str, dict[str, dict[str, Any]]],
    baseline_features: dict[str, dict[str, Any]],
    selected_feature_ids: set[str],
    include_removed_features: bool,
) -> list[ImpactSuspect]:
    suspects: list[ImpactSuspect] = []
    feature_ids = set(selected_feature_ids)
    if include_removed_features:
        feature_ids.update(baseline_features.keys())

    for feature_id in sorted(feature_ids):
        current_nodes = current_graph.get(feature_id, {})
        baseline_nodes = baseline_features.get(feature_id, {}).get("nodes", {})
        direct_entities: set[str] = set()

        for entity_id in sorted(set(current_nodes) - set(baseline_nodes)):
            node = current_nodes[entity_id]
            suspects.append(
                ImpactSuspect(
                    feature_id=feature_id,
                    entity_type=str(node["entity_type"]),
                    entity_id=entity_id,
                    reason="added",
                    upstream_ids=(),
                    path=str(node["path"]),
                    line=_to_int(node.get("line")),
                )
            )
            direct_entities.add(entity_id)

        for entity_id in sorted(set(baseline_nodes) - set(current_nodes)):
            node = baseline_nodes[entity_id]
            suspects.append(
                ImpactSuspect(
                    feature_id=feature_id,
                    entity_type=str(node.get("entity_type", "unknown")),
                    entity_id=entity_id,
                    reason="removed",
                    upstream_ids=(),
                    path=str(node.get("path", "")),
                    line=_to_int(node.get("line")),
                )
            )
            direct_entities.add(entity_id)

        for entity_id in sorted(set(current_nodes) & set(baseline_nodes)):
            current_node = current_nodes[entity_id]
            baseline_node = baseline_nodes[entity_id]
            if str(current_node.get("hash", "")) != str(baseline_node.get("hash", "")):
                suspects.append(
                    ImpactSuspect(
                        feature_id=feature_id,
                        entity_type=str(current_node["entity_type"]),
                        entity_id=entity_id,
                        reason="changed",
                        upstream_ids=(),
                        path=str(current_node["path"]),
                        line=_to_int(current_node.get("line")),
                    )
                )
                direct_entities.add(entity_id)

        for entity_id in sorted(set(current_nodes) & set(baseline_nodes)):
            if entity_id in direct_entities:
                continue
            current_node = current_nodes[entity_id]
            if current_node.get("entity_type") not in PROPAGATION_ELIGIBLE_TYPES:
                continue
            references = list(current_node.get("references", []))
            if not references:
                continue
            baseline_node = baseline_nodes[entity_id]
            reviewed = baseline_node.get("reviewed_upstream_hashes", {})
            changed_upstreams: list[str] = []
            for upstream_id in references:
                if str(reviewed.get(upstream_id, "")) != _upstream_hash(current_nodes, upstream_id):
                    changed_upstreams.append(upstream_id)
            if changed_upstreams:
                suspects.append(
                    ImpactSuspect(
                        feature_id=feature_id,
                        entity_type=str(current_node["entity_type"]),
                        entity_id=entity_id,
                        reason="upstream_changed",
                        upstream_ids=tuple(sorted(set(changed_upstreams))),
                        path=str(current_node["path"]),
                        line=_to_int(current_node.get("line")),
                    )
                )

    return sorted(
        suspects,
        key=lambda s: (
            s.feature_id,
            s.entity_type,
            s.entity_id,
            s.reason,
            ",".join(s.upstream_ids),
            s.path,
            s.line or 0,
        ),
    )


def _build_current_graph(root: Path, rows: list[FeatureRow]) -> dict[str, dict[str, dict[str, Any]]]:
    docs = root / "docs"
    graph: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        feature_dir = (docs / row.spec_path).parent
        graph[row.feature_id] = _extract_feature_nodes(root, feature_dir)
    return graph


def _extract_feature_nodes(root: Path, feature_dir: Path) -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    scenario_values: dict[str, list[str]] = {}
    scenario_meta: dict[str, tuple[str, int]] = {}

    requirements_path = feature_dir / "requirements.md"
    verification_path = feature_dir / "verification.md"
    design_path = feature_dir / "design.md"
    tasks_path = feature_dir / "tasks.md"

    if requirements_path.exists():
        for idx, line in enumerate(read_text(requirements_path).splitlines(), start=1):
            req_match = REQ_LINE_RE.match(line)
            if req_match:
                req_id, statement = req_match.groups()
                nodes[req_id] = _make_node(
                    entity_type="requirement",
                    entity_id=req_id,
                    text=statement,
                    path=_relative_path(root, requirements_path),
                    line=idx,
                    references=[],
                )
            scenario_match = SCENARIO_LINE_RE.match(line)
            if scenario_match:
                scenario_id, statement = scenario_match.groups()
                scenario_values.setdefault(scenario_id, []).append(statement)
                scenario_meta.setdefault(scenario_id, (_relative_path(root, requirements_path), idx))

    if verification_path.exists():
        for idx, line in enumerate(read_text(verification_path).splitlines(), start=1):
            scenario_match = SCENARIO_LINE_RE.match(line)
            if scenario_match:
                scenario_id, statement = scenario_match.groups()
                scenario_values.setdefault(scenario_id, []).append(statement)
                scenario_meta.setdefault(scenario_id, (_relative_path(root, verification_path), idx))
            evidence_match = EVIDENCE_LINE_RE.match(line)
            if evidence_match:
                scenario_id, target = evidence_match.groups()
                evidence_id = f"EVIDENCE({scenario_id})"
                nodes[evidence_id] = _make_node(
                    entity_type="evidence",
                    entity_id=evidence_id,
                    text=target,
                    path=_relative_path(root, verification_path),
                    line=idx,
                    references=[scenario_id],
                )

    if design_path.exists():
        design_text = read_text(design_path)
        global_req_refs = sorted(set(REQ_ID_RE.findall(design_text)))
        for idx, line in enumerate(design_text.splitlines(), start=1):
            design_match = DESIGN_LINE_RE.match(line)
            if not design_match:
                continue
            design_id, statement = design_match.groups()
            req_refs = sorted(set(REQ_ID_RE.findall(line)))
            if not req_refs:
                req_refs = global_req_refs
            nodes[design_id] = _make_node(
                entity_type="design",
                entity_id=design_id,
                text=statement,
                path=_relative_path(root, design_path),
                line=idx,
                references=req_refs,
            )

    if tasks_path.exists():
        for idx, line in enumerate(read_text(tasks_path).splitlines(), start=1):
            task_ids = sorted(set(TASK_ID_RE.findall(line)))
            if not task_ids:
                continue
            refs = sorted(set(REQ_ID_RE.findall(line) + DESIGN_ID_RE.findall(line)))
            for task_id in task_ids:
                nodes[task_id] = _make_node(
                    entity_type="task",
                    entity_id=task_id,
                    text=line.strip(),
                    path=_relative_path(root, tasks_path),
                    line=idx,
                    references=refs,
                )

    for scenario_id in sorted(scenario_values):
        path, line = scenario_meta[scenario_id]
        statement = "\n".join(scenario_values[scenario_id])
        nodes[scenario_id] = _make_node(
            entity_type="scenario",
            entity_id=scenario_id,
            text=statement,
            path=path,
            line=line,
            references=[],
        )

    return nodes


def _make_node(
    *,
    entity_type: str,
    entity_id: str,
    text: str,
    path: str,
    line: int,
    references: list[str],
) -> dict[str, Any]:
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "hash": _hash_text(text),
        "path": path,
        "line": line,
        "references": sorted(set(references)),
    }


def _hash_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _relative_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _load_baseline_payload(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, "root payload must be an object"
    if payload.get("schema_version") != BASELINE_SCHEMA_VERSION:
        return None, (
            f"unsupported schema_version '{payload.get('schema_version')}', "
            f"expected '{BASELINE_SCHEMA_VERSION}'"
        )
    if not isinstance(payload.get("features"), dict):
        return None, "missing or invalid 'features' object"
    return payload, None


def _coerce_baseline_features(features: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(features, dict):
        return {}
    coerced: dict[str, dict[str, Any]] = {}
    for feature_id, payload in features.items():
        if not isinstance(feature_id, str):
            continue
        if not isinstance(payload, dict):
            continue
        coerced[feature_id] = _normalize_feature_payload(payload)
    return coerced


def _normalize_feature_payload(payload: dict[str, Any]) -> dict[str, Any]:
    nodes_payload = payload.get("nodes", {})
    if not isinstance(nodes_payload, dict):
        nodes_payload = {}
    nodes: dict[str, dict[str, Any]] = {}
    for entity_id, node in nodes_payload.items():
        if not isinstance(entity_id, str) or not isinstance(node, dict):
            continue
        refs = node.get("references", [])
        if not isinstance(refs, list):
            refs = []
        reviewed = node.get("reviewed_upstream_hashes", {})
        if not isinstance(reviewed, dict):
            reviewed = {}
        nodes[entity_id] = {
            "entity_type": str(node.get("entity_type", "unknown")),
            "hash": str(node.get("hash", "")),
            "path": str(node.get("path", "")),
            "line": _to_int(node.get("line")),
            "references": sorted(str(ref) for ref in refs if isinstance(ref, str)),
            "reviewed_upstream_hashes": {
                str(key): str(value)
                for key, value in reviewed.items()
                if isinstance(key, str)
            },
        }
    return {"nodes": nodes}


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
