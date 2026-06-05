"""
generate_picklist.py
--------------------
Generates a BigCommerce picklist JSON from two CSV files:
  1. dropdown_csv  — columns: Parent SKU, Dropdown SKU, Product Name, Dropdown Label, Product ID
  2. parent_csv    — columns: SKU, Product ID, Product Name, Column 1

The dropdown CSV is assumed to be sorted: all rows for the same parent SKU appear
together, and within a parent SKU all rows for the same Dropdown Label appear
together. The script processes the file sequentially and respects that order.

Usage:
    python generate_picklist.py \
        --dropdown  dropdown_products.csv \
        --parents   parent_products.csv \
        --output    picklist.json

Optional flags:
    --dropdown-encoding   utf-8-sig  (default; handles Excel BOM automatically)
    --parents-encoding    utf-8-sig
    --indent              2          (JSON pretty-print indent; 0 = compact)
"""

import argparse
import csv
import json
import sys
from pathlib import Path


# ── helpers ───────────────────────────────────────────────────────────────────

def load_csv(path: Path, encoding: str) -> list[dict]:
    """Read a CSV and return list of row-dicts with stripped keys/values."""
    rows = []
    with path.open(newline="", encoding=encoding) as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({k.strip(): (v.strip() if v else "") for k, v in row.items()})
    return rows


def build_parent_lookup(parent_rows: list[dict]) -> dict[str, int | str | None]:
    """
    Returns dict: parent_sku -> product_id (int when possible, else str, else None).
    Keyed by the 'SKU' column in the parent CSV.
    """
    lookup = {}
    for row in parent_rows:
        sku = row.get("SKU", "").strip()
        if not sku:
            continue
        raw_id = row.get("Product ID", "").strip()
        try:
            lookup[sku] = int(raw_id)
        except (ValueError, TypeError):
            lookup[sku] = raw_id or None
    return lookup


def coerce_id(raw: str) -> int | str:
    try:
        return int(raw)
    except (ValueError, TypeError):
        return raw


def build_picklist(dropdown_rows: list[dict], parent_lookup: dict) -> list[dict]:
    """
    Walks the dropdown CSV sequentially.

    A new parent-product entry is created each time the Parent SKU changes.
    Within a parent-product entry, a new picklist_options entry is created
    each time the Dropdown Label changes.

    This matches the guarantee that the CSV is sorted:
      - all rows for one Parent SKU are contiguous
      - within a Parent SKU, all rows for one Dropdown Label are contiguous
    """
    result: list[dict] = []           # final output list
    warnings: list[str] = []

    # Sentinels for "what are we currently building"
    current_parent_sku: str | None = None
    current_label:      str | None = None
    current_parent_entry: dict | None = None   # the dict being appended to result
    current_label_items:  list | None = None   # the list under the current label

    for row_num, row in enumerate(dropdown_rows, start=2):   # row 1 = header
        parent_sku   = row.get("Parent SKU", "").strip()
        dropdown_sku = row.get("Dropdown SKU", "").strip()
        product_name = row.get("Product Name", "").strip()
        label        = row.get("Dropdown Label", "").strip()
        product_id   = row.get("Product ID", "").strip()

        # ── basic validation ────────────────────────────────────────────────
        if not parent_sku:
            warnings.append(f"Row {row_num}: missing 'Parent SKU', skipping.")
            continue
        if not label:
            warnings.append(f"Row {row_num}: missing 'Dropdown Label' for SKU '{parent_sku}', skipping.")
            continue

        # ── detect parent SKU change ────────────────────────────────────────
        if parent_sku != current_parent_sku:
            # Look up this parent's main product ID
            if parent_sku not in parent_lookup:
                warnings.append(
                    f"Row {row_num}: Parent SKU '{parent_sku}' not found in parent CSV "
                    f"— main_product_id will be null."
                )
                main_id = None
            else:
                main_id = parent_lookup[parent_sku]

            # Start a fresh parent entry
            current_parent_entry = {
                "main_product_id": main_id,
                "picklist_options": []
            }
            result.append(current_parent_entry)

            current_parent_sku = parent_sku
            current_label      = None          # force label block to reset too
            current_label_items = None

        # ── detect label change (within same parent SKU) ────────────────────
        if label != current_label:
            current_label_items = []
            current_parent_entry["picklist_options"].append({label: current_label_items})
            current_label = label

        # ── append this item to the current label block ─────────────────────
        current_label_items.append({
            "id":   coerce_id(product_id),
            "sku":  dropdown_sku,
            "name": product_name,
        })

    # ── print warnings ───────────────────────────────────────────────────────
    if warnings:
        print(f"\n  {len(warnings)} warning(s):", file=sys.stderr)
        for msg in warnings[:20]:
            print(f"   {msg}", file=sys.stderr)
        if len(warnings) > 20:
            print(f"   ... and {len(warnings) - 20} more", file=sys.stderr)

    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a BigCommerce picklist JSON from two CSV files."
    )
    parser.add_argument(
        "--dropdown", required=True,
        help="Dropdown CSV (Parent SKU, Dropdown SKU, Product Name, Dropdown Label, Product ID)"
    )
    parser.add_argument(
        "--parents", required=True,
        help="Parent products CSV (SKU, Product ID, Product Name, ...)"
    )
    parser.add_argument(
        "--output", default="picklist.json",
        help="Output JSON file (default: picklist.json)"
    )
    parser.add_argument(
        "--dropdown-encoding", default="utf-8-sig",
        help="Encoding for the dropdown CSV (default: utf-8-sig)"
    )
    parser.add_argument(
        "--parents-encoding", default="utf-8-sig",
        help="Encoding for the parents CSV (default: utf-8-sig)"
    )
    parser.add_argument(
        "--indent", type=int, default=2,
        help="JSON indent level (default: 2; use 0 for compact)"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    dropdown_path = Path(args.dropdown)
    parents_path  = Path(args.parents)
    output_path   = Path(args.output)

    for p in (dropdown_path, parents_path):
        if not p.exists():
            print(f"File not found: {p}", file=sys.stderr)
            sys.exit(1)

    print(f"Loading dropdown CSV  : {dropdown_path}")
    dropdown_rows = load_csv(dropdown_path, args.dropdown_encoding)
    print(f"  -> {len(dropdown_rows):,} rows")

    print(f"Loading parent CSV    : {parents_path}")
    parent_rows = load_csv(parents_path, args.parents_encoding)
    print(f"  -> {len(parent_rows):,} rows")

    parent_lookup = build_parent_lookup(parent_rows)
    print(f"Unique parent SKUs    : {len(parent_lookup):,}")

    picklist = build_picklist(dropdown_rows, parent_lookup)
    print(f"Parent products output: {len(picklist):,}")

    indent = args.indent if args.indent > 0 else None
    output_path.write_text(
        json.dumps(picklist, indent=indent, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\nWritten to: {output_path}")


if __name__ == "__main__":
    main()