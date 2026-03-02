from __future__ import annotations

from pathlib import Path

from specctl.feature_index import read_feature_rows
from specctl.io_utils import parse_frontmatter, write_text
from specctl.renderers.product_map import render_product_map
from specctl.renderers.traceability import render_traceability
from specctl.validators.project import lint_project


def run(args) -> int:
    root = Path(args.root).resolve()
    docs = root / "docs"
    features_index_path = docs / "FEATURES.md"
    rows = read_feature_rows(features_index_path)
    _, stats = lint_project(root)
    render_stamp = _deterministic_render_stamp(features_index_path)

    product_map = render_product_map(rows).replace("last_rendered: TBD", f"last_rendered: {render_stamp}")
    traceability = render_traceability(stats).replace("last_rendered: TBD", f"last_rendered: {render_stamp}")

    product_map_path = docs / "PRODUCT_MAP.md"
    traceability_path = docs / "TRACEABILITY.md"

    if args.check:
        mismatches: list[str] = []
        if not product_map_path.exists() or product_map_path.read_text(encoding="utf-8") != product_map:
            mismatches.append(str(product_map_path))
        if not traceability_path.exists() or traceability_path.read_text(encoding="utf-8") != traceability:
            mismatches.append(str(traceability_path))
        if mismatches:
            for path in mismatches:
                print(f"[ERROR] RENDER_MISMATCH: {path} is stale")
            return 1
        return 0

    write_text(product_map_path, product_map)
    write_text(traceability_path, traceability)
    print(f"Rendered {product_map_path} and {traceability_path}")
    return 0


def _deterministic_render_stamp(features_index_path: Path) -> str:
    if not features_index_path.exists():
        return "TBD"
    data, _ = parse_frontmatter(features_index_path.read_text(encoding="utf-8"))
    stamp = data.get("last_synced")
    if isinstance(stamp, str) and stamp:
        return stamp
    return "TBD"
