from __future__ import annotations

from pathlib import Path

from specctl.feature_index import read_feature_rows
from specctl.io_utils import now_date, write_text
from specctl.renderers.product_map import render_product_map
from specctl.renderers.traceability import render_traceability
from specctl.validators.project import lint_project


def run(args) -> int:
    root = Path(args.root).resolve()
    docs = root / "docs"
    rows = read_feature_rows(docs / "FEATURES.md")
    _, stats = lint_project(root)

    product_map = render_product_map(rows).replace("last_rendered: TBD", f"last_rendered: {now_date()}")
    traceability = render_traceability(stats).replace("last_rendered: TBD", f"last_rendered: {now_date()}")

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
