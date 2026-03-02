from __future__ import annotations

from pathlib import Path

from specctl.io_utils import now_date, write_text


def run(args) -> int:
    root = Path(args.root).resolve()
    docs = root / "docs"
    features = docs / "features"
    decisions = docs / "DECISIONS"

    for directory in [docs, features, decisions]:
        directory.mkdir(parents=True, exist_ok=True)

    write_text(
        docs / "MASTER_SPEC.md",
        "\n".join(
            [
                "---",
                "doc_type: master_spec",
                "product_name: TBD",
                "version: 2.0.0",
                "status: active",
                "owners: []",
                f"last_reviewed: {now_date()}",
                "---",
                "# Master Spec",
                "",
                "## Vision",
            ]
        )
        + "\n",
    )

    write_text(
        docs / "STEERING.md",
        "\n".join(
            [
                "---",
                "doc_type: steering",
                "version: 2.0.0",
                f"last_reviewed: {now_date()}",
                "---",
                "# Steering",
                "",
                "## Product Constraints",
                "",
                "## Design Principles",
            ]
        )
        + "\n",
    )

    write_text(
        docs / "FEATURES.md",
        "\n".join(
            [
                "---",
                "doc_type: feature_index",
                "version: 2.0.0",
                f"last_synced: {now_date()}",
                "---",
                "# Features Index",
                "",
                "| ID | Name | Status | Parent ID | Spec Path | Owner | Aliases |",
                "|----|------|--------|-----------|-----------|-------|---------|",
            ]
        )
        + "\n",
    )

    write_text(
        docs / "PRODUCT_MAP.md",
        "\n".join(
            [
                "---",
                "doc_type: product_map",
                "from_index: ./FEATURES.md",
                f"last_rendered: {now_date()}",
                "---",
                "# Product Map",
            ]
        )
        + "\n",
    )

    write_text(
        docs / "TRACEABILITY.md",
        "\n".join(
            [
                "---",
                "doc_type: traceability",
                "version: 2.0.0",
                f"last_rendered: {now_date()}",
                "---",
                "# Traceability Report",
                "",
                "| Metric | Value |",
                "|---|---:|",
            ]
        )
        + "\n",
    )

    write_text(
        decisions / "ADR_TEMPLATE.md",
        "\n".join(
            [
                "---",
                "doc_type: adr",
                "adr_id: ADR-0000",
                "title: TBD",
                "status: proposed",
                "date: TBD",
                "related_features: []",
                "---",
                "# ADR Template",
            ]
        )
        + "\n",
    )

    print(f"Initialized Spec System v2 at {docs}")
    return 0
