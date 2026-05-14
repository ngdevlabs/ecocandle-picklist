"""
revert_split.py
---------------
Reverts a product-split operation using a backup JSON file.

For each entry in `split_products`:
  1. Deletes the standalone product that was created from the variant
     (new_product_id).
  2. Re-creates the variant under the original parent product
     (original_product_id) with its original SKU, option values, pricing,
     weight, and inventory data.

Usage:
    python revert_split.py <backup_file.json>

If no argument is given it defaults to looking for a file named
`backup.json` in the current directory.
"""

import json
import sys
from client import ApiClient

# ── helpers ──────────────────────────────────────────────────────────────────

def build_variant_payload(variant_snap: dict) -> dict:
    """
    Convert a variant snapshot (from the backup) into the payload expected
    by the BigCommerce POST /v3/catalog/products/{id}/variants endpoint.

    Only fields that are explicitly set in the snapshot are included;
    null / empty values are omitted so BigCommerce falls back to the
    product-level defaults.
    """
    payload: dict = {}

    # ── required ──────────────────────────────────────────────────────────
    payload["sku"] = variant_snap["sku"]

    # option_values tells BigCommerce which combination this variant represents
    payload["option_values"] = [
        {"id": ov["id"], "option_id": ov["option_id"]}
        for ov in variant_snap.get("option_values", [])
    ]

    # ── optional – only include when not null / falsy ──────────────────────
    for field in ("price", "sale_price", "retail_price", "map_price",
                  "cost_price", "weight", "width", "height", "depth",
                  "upc", "mpn", "gtin", "bin_picking_number"):
        value = variant_snap.get(field)
        if value not in (None, "", 0, 0.0):
            payload[field] = value

    payload["inventory_level"] = variant_snap.get("inventory_level", 0)
    payload["inventory_warning_level"] = variant_snap.get("inventory_warning_level", 0)

    if variant_snap.get("is_free_shipping"):
        payload["is_free_shipping"] = True

    if variant_snap.get("fixed_cost_shipping_price"):
        payload["fixed_cost_shipping_price"] = variant_snap["fixed_cost_shipping_price"]

    if variant_snap.get("purchasing_disabled"):
        payload["purchasing_disabled"] = True
        payload["purchasing_disabled_message"] = variant_snap.get(
            "purchasing_disabled_message", ""
        )

    return payload


def revert(backup_path: str):
    with open(backup_path, "r") as f:
        backup = json.load(f)

    parent_product_id: int = backup["original_product_id"]
    split_products: list  = backup["split_products"]

    client = ApiClient()

    print(f"\n{'='*60}")
    print(f"Parent product ID : {parent_product_id}")
    print(f"Variants to restore: {len(split_products)}")
    print(f"{'='*60}\n")

    success_count = 0
    fail_count    = 0

    for entry in split_products:
        new_product_id  = entry["new_product_id"]
        option_label    = entry["option_label"]
        variant_snap    = entry["original_variant_snapshot"]
        original_var_id = variant_snap["id"]

        print(f"── Processing variant: {option_label}  (original variant id={original_var_id})")

        # ── Step 1: delete the standalone product ─────────────────────────
        try:
            client.delete(f"/catalog/products/{new_product_id}")
            print(f"   ✓ Deleted product {new_product_id}")
        except Exception as exc:
            print(f"   ✗ Failed to delete product {new_product_id}: {exc}")
            print(f"     Skipping variant restoration for safety.\n")
            fail_count += 1
            continue

        # ── Step 2: re-create the variant under the parent product ────────
        payload = build_variant_payload(variant_snap)

        try:
            created = client.post(
                f"/catalog/products/{parent_product_id}/variants",
                payload,
            )
            new_var_id = created.get("id", "?")
            print(f"   ✓ Variant re-created (new variant id={new_var_id})\n")
            success_count += 1
        except Exception as exc:
            print(f"   ✗ Failed to create variant for '{option_label}'")

            if hasattr(exc, "response") and exc.response is not None:
                try:
                    print("   Status:", exc.response.status_code)
                    print("   Response:", exc.response.text)
                except Exception:
                    pass

            print(f"   Error: {exc}\n")

    print(f"{'='*60}")
    print(f"Done.  Restored: {success_count}  |  Failed: {fail_count}")
    print(f"{'='*60}\n")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    backup_file = 'data/rollback_124.json'
    revert(backup_file)