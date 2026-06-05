"""
BigCommerce: Build a picklist modifier on the original product using
the newly-created split products recorded in a rollback manifest.

Usage:
    python manifest_to_picklist.py --manifest rollback_<product_id>.json

Optional flags:
    --display-name "choose your fragrance"   Override the modifier display name
    --dry-run                                Print what would happen without API calls
"""

import argparse
import json
import sys
import time

from client import ApiClient

api = ApiClient()


# ---------------------------------------------------------------------------
# Helpers (mirrored from your existing picklist script)
# ---------------------------------------------------------------------------

def delete_existing_options_and_modifiers(product_id: int, option_name: str) -> None:
    """Remove any existing modifier or variant option with the same display name."""
    modifiers = api.get(f"/catalog/products/{product_id}/modifiers")
    for mod in modifiers:
        if mod["display_name"] == option_name:
            api.delete(f"/catalog/products/{product_id}/modifiers/{mod['id']}")
            print(f"  ✓ Deleted existing modifier '{option_name}' (id={mod['id']})")

    options = api.get(f"/catalog/products/{product_id}/options")
    for opt in options:
        api.delete(f"/catalog/products/{product_id}/options/{opt['id']}")
        print(f"  ✓ Deleted variant option '{opt['display_name']}' (id={opt['id']})")


def create_picklist_modifier(
    product_id: int,
    display_name: str,
    items: list,
    dry_run: bool = False,
) -> None:
    """
    Creates a product_list (Pick List) modifier on `product_id`.

    items: list of {"id": <new_product_id>, "name": <label>}
    """
    option_values = [
        {
            "label": item["name"],
            "sort_order": idx,
            "value_data": {"product_id": item["id"]},
        }
        for idx, item in enumerate(items)
    ]

    payload = {
        "type": "product_list_with_images",
        "display_name": display_name,
        "required": True,
        "config":{
            "product_list_adjusts_pricing": False,   # Adjust price → OFF
            "product_list_adjusts_inventory": True,  # Adjust inventory → ON
            "product_list_show_image": True,
            "product_list_shipping_calc": "none",
        },
        "productListShowWithImages": True,
        "option_values": option_values,
    }

    if dry_run:
        print(f"  [DRY-RUN] Would POST modifier '{display_name}' with {len(items)} items:")
        for item in items:
            print(f"    • {item['name']}  (product_id={item['id']})")
        return

    response = api.post(f"/catalog/products/{product_id}/modifiers", payload)
    if response:
        print(f"  ✓ Picklist '{display_name}' created on product {product_id} "
              f"with {len(items)} entries.")
    else:
        print(f"  ✗ Failed to create picklist on product {product_id}.")


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def infer_display_name(manifest: dict) -> str:
    """
    Try to pull the original option display name from the first split entry.
    Falls back to 'choose your fragrance' if unavailable.
    """
    for entry in manifest.get("split_products", []):
        for ov in entry.get("option_values", []):
            name = ov.get("option_display_name")
            if name:
                return name
    return "choose your fragrance"


def build_picklist_items(manifest: dict) -> list:
    """
    Convert split_products entries into the item list expected by
    create_picklist_modifier: [{"id": <new_product_id>, "name": <label>}, ...]

    Skips any entry whose new_product_id is None (dry-run artefacts).
    """
    items = []
    for entry in manifest.get("split_products", []):
        new_id = entry.get("new_product_id")
        label = entry.get("option_label", f"Variant {entry.get('variant_id', '?')}")
        if new_id is None:
            print(f"  ⚠ Skipping '{label}' — no new_product_id recorded (was this a dry-run manifest?)")
            continue
        items.append({"id": new_id, "name": label})
    return items


def run(manifest_path: str, display_name_override: str | None, dry_run: bool) -> None:
    print(f"\n{'='*60}")
    print(f"Reading manifest: {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    original_product_id: int = manifest["original_product_id"]
    was_deleted: bool = manifest.get("original_product_deleted", False)

    print(f"Original product id : {original_product_id}")
    print(f"Original deleted    : {was_deleted}")

    if was_deleted:
        print("\n❌  The original product was deleted during the split — "
              "there is no product to attach a picklist to.")
        sys.exit(1)

    display_name = display_name_override or infer_display_name(manifest)
    print(f"Modifier display name: '{display_name}'")

    items = build_picklist_items(manifest)
    if not items:
        print("\n⚠  No usable split products found in the manifest. Nothing to do.")
        sys.exit(0)

    print(f"Picklist entries    : {len(items)}\n")
    for item in items:
        print(f"  • [{item['id']}] {item['name']}")

    print()

    if not dry_run:
        print("Step 1 — Clearing existing modifiers / variant options …")
        delete_existing_options_and_modifiers(original_product_id, display_name)
        time.sleep(0.3)

        print("\nStep 2 — Creating picklist modifier …")
        create_picklist_modifier(original_product_id, display_name, items, dry_run=False)
    else:
        print("Step 1 — [DRY-RUN] Would clear existing modifiers / variant options.")
        print("\nStep 2 — [DRY-RUN] Would create picklist modifier:")
        create_picklist_modifier(original_product_id, display_name, items, dry_run=True)

    print("\nDone.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Attach split products as a picklist modifier on the original product."
    )
    parser.add_argument(
        "--manifest",
        required=True,
        metavar="FILE",
        help="Path to the rollback manifest JSON produced by variant_to_product.py",
    )
    parser.add_argument(
        "--display-name",
        default=None,
        metavar="NAME",
        help="Override the modifier display name (auto-detected from manifest if omitted)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would happen without making any API calls",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        run(
            manifest_path=args.manifest,
            display_name_override=args.display_name,
            dry_run=args.dry_run,
        )
    except FileNotFoundError:
        print(f"\n❌  Manifest file not found: {args.manifest}")
        sys.exit(1)
    except KeyError as exc:
        print(f"\n❌  Unexpected manifest structure — missing key: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\n❌  {exc}")
        sys.exit(1)