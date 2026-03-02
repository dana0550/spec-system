from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from specctl.models import FeatureRow


def render_product_map(rows: Iterable[FeatureRow]) -> str:
    rows = list(rows)
    by_parent: dict[str, list[FeatureRow]] = defaultdict(list)
    for row in rows:
        by_parent[row.parent_id].append(row)

    for key in by_parent:
        by_parent[key].sort(key=lambda r: r.feature_id)

    lines = [
        "---",
        "doc_type: product_map",
        "from_index: ./FEATURES.md",
        "last_rendered: TBD",
        "---",
        "# Product Map",
        "",
    ]

    def walk(parent: str, depth: int) -> None:
        for row in by_parent.get(parent, []):
            indent = "  " * depth
            lines.append(f"{indent}- [{row.feature_id}] {row.name} ({row.status})")
            walk(row.feature_id, depth + 1)

    walk("", 0)
    lines.extend(["", "<!-- AUTOGEN: generated from FEATURES.md hierarchy -->", ""])
    return "\n".join(lines)
