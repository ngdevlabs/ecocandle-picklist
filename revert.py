"""
restore_products.py

Reverts BigCommerce products to their backed-up state using a JSON backup file.

Usage:
    python restore_products.py --backup products_backup.json
    python restore_products.py --backup products_backup.json --product-ids 2840 2841
"""

import argparse
import json
import logging
import sys
from typing import Any

from client import ApiClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fields sent to PUT /v3/catalog/products/{id}
# Omits read-only and relationship fields that are managed separately.
# ---------------------------------------------------------------------------
PRODUCT_CORE_FIELDS = [
    "name", "type", "sku", "description", "weight", "width", "depth", "height",
    "price", "cost_price", "retail_price", "sale_price", "map_price",
    "tax_class_id", "product_tax_code", "categories", "brand_id",
    "option_set_id", "option_set_display",
    "inventory_level", "inventory_warning_level", "inventory_tracking",
    "fixed_cost_shipping_price", "is_free_shipping", "is_visible", "is_featured",
    "related_products", "warranty", "bin_picking_number", "layout_file",
    "upc", "mpn", "gtin", "search_keywords", "availability",
    "availability_description", "gift_wrapping_options_type",
    "gift_wrapping_options_list", "sort_order", "condition", "is_condition_shown",
    "order_quantity_minimum", "order_quantity_maximum",
    "page_title", "meta_keywords", "meta_description",
    "is_preorder_only", "is_price_hidden", "price_hidden_label",
    "open_graph_type", "open_graph_title", "open_graph_description",
    "open_graph_use_meta_description", "open_graph_use_product_name",
    "open_graph_use_image",
]

# Fields sent when creating/updating a modifier option value
MODIFIER_VALUE_FIELDS = [
    "label", "sort_order", "value_data", "is_default",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_product_payload(product: dict) -> dict:
    return {k: product[k] for k in PRODUCT_CORE_FIELDS if k in product}


def build_modifier_payload(mod: dict) -> dict:
    """Strip server-only fields before creating/updating a modifier."""
    return {
        "display_name": mod["display_name"],
        "type": mod["type"],
        "required": mod["required"],
        "sort_order": mod["sort_order"],
        "config": mod.get("config", []),
    }


def build_modifier_value_payload(val: dict) -> dict:
    payload = {k: val[k] for k in MODIFIER_VALUE_FIELDS if k in val}
    # Include adjuster sub-fields if present
    if "adjusters" in val:
        payload["adjusters"] = val["adjusters"]
    return payload


# ---------------------------------------------------------------------------
# Core restore logic
# ---------------------------------------------------------------------------

def restore_product_core(client: ApiClient, product: dict) -> None:
    pid = product["id"]
    payload = build_product_payload(product)
    log.info("  Updating core fields for product %s ('%s')", pid, product.get("name"))
    client.put(f"/catalog/products/{pid}", payload)


def restore_variants(client: ApiClient, product: dict) -> None:
    pid = product["id"]
    backed_up_variants: list[dict] = product.get("variants", [])
    if not backed_up_variants:
        return

    log.info("  Restoring %d variant(s) for product %s", len(backed_up_variants), pid)

    live_variants: list[dict] = client.get(f"/catalog/products/{pid}/variants")
    live_by_id = {v["id"]: v for v in live_variants}

    for bv in backed_up_variants:
        vid = bv["id"]
        variant_payload = {
            "sku": bv.get("sku", ""),
            "price": bv.get("price"),
            "sale_price": bv.get("sale_price"),
            "retail_price": bv.get("retail_price"),
            "weight": bv.get("weight"),
            "width": bv.get("width"),
            "height": bv.get("height"),
            "depth": bv.get("depth"),
            "cost_price": bv.get("cost_price"),
            "is_free_shipping": bv.get("is_free_shipping"),
            "fixed_cost_shipping_price": bv.get("fixed_cost_shipping_price"),
            "inventory_level": bv.get("inventory_level"),
            "inventory_warning_level": bv.get("inventory_warning_level"),
            "upc": bv.get("upc", ""),
            "mpn": bv.get("mpn", ""),
            "gtin": bv.get("gtin", ""),
            "bin_picking_number": bv.get("bin_picking_number", ""),
            "purchasing_disabled": bv.get("purchasing_disabled", False),
            "purchasing_disabled_message": bv.get("purchasing_disabled_message", ""),
        }
        # Remove None values — BigCommerce rejects nulls for some fields
        variant_payload = {k: v for k, v in variant_payload.items() if v is not None}

        if vid in live_by_id:
            client.put(f"/catalog/products/{pid}/variants/{vid}", variant_payload)
            log.info("    Updated variant %s", vid)
        else:
            log.warning("    Variant %s not found live — skipping (use BC import to recreate)", vid)


def restore_modifiers(client: ApiClient, product: dict) -> None:
    """
    Full modifier restore strategy:
      1. Fetch live modifiers.
      2. For each backed-up modifier:
         - If it exists live (matched by id) → PUT to restore fields,
           then reconcile its option values.
         - If it no longer exists live → POST to recreate it (new id assigned
           by BC, option values added afterwards).
      3. Delete any live modifiers that are NOT in the backup.
    """
    pid = product["id"]
    backed_up_mods: list[dict] = product.get("modifiers", [])
    if not backed_up_mods:
        return

    log.info("  Restoring %d modifier(s) for product %s", len(backed_up_mods), pid)

    live_mods: list[dict] = client.get(f"/catalog/products/{pid}/modifiers")
    live_by_id = {m["id"]: m for m in live_mods}
    backed_up_ids = {m["id"] for m in backed_up_mods}

    # Delete modifiers that aren't in the backup
    for live_id in list(live_by_id.keys()):
        if live_id not in backed_up_ids:
            log.info("    Deleting extra modifier %s", live_id)
            client.delete(f"/catalog/products/{pid}/modifiers/{live_id}")

    for bm in backed_up_mods:
        mod_payload = build_modifier_payload(bm)

        if bm["id"] in live_by_id:
            # Update existing modifier
            client.put(f"/catalog/products/{pid}/modifiers/{bm['id']}", mod_payload)
            log.info("    Updated modifier %s ('%s')", bm["id"], bm["display_name"])
            _restore_modifier_values(client, pid, bm["id"], bm.get("option_values", []))
        else:
            # Recreate modifier (BC assigns a new id)
            created = client.post(f"/catalog/products/{pid}/modifiers", mod_payload)
            new_mod_id = created["id"]
            log.info("    Recreated modifier '%s' → new id %s", bm["display_name"], new_mod_id)
            _restore_modifier_values(client, pid, new_mod_id, bm.get("option_values", []))


def _restore_modifier_values(
    client: ApiClient, pid: int, mod_id: int, backed_up_values: list[dict]
) -> None:
    if not backed_up_values:
        return

    live_values: list[dict] = client.get(
        f"/catalog/products/{pid}/modifiers/{mod_id}/values"
    )
    live_by_id = {v["id"]: v for v in live_values}
    backed_up_ids = {v["id"] for v in backed_up_values}

    # Delete option values not in backup
    for live_val_id in list(live_by_id.keys()):
        if live_val_id not in backed_up_ids:
            client.delete(
                f"/catalog/products/{pid}/modifiers/{mod_id}/values/{live_val_id}"
            )

    for bv in backed_up_values:
        val_payload = build_modifier_value_payload(bv)
        if bv["id"] in live_by_id:
            client.put(
                f"/catalog/products/{pid}/modifiers/{mod_id}/values/{bv['id']}",
                val_payload,
            )
        else:
            client.post(
                f"/catalog/products/{pid}/modifiers/{mod_id}/values",
                val_payload,
            )

    log.info("      Synced %d option value(s) on modifier %s", len(backed_up_values), mod_id)


def restore_images(client: ApiClient, product: dict) -> None:
    """
    Restores image metadata (description, sort_order, is_thumbnail).
    Does NOT re-upload binary image data — the CDN URLs in the backup
    already point to the live CDN, so no re-upload is needed.
    Only updates images that still exist on the product by id.
    """
    pid = product["id"]
    backed_up_images: list[dict] = product.get("images", [])
    if not backed_up_images:
        return

    live_images: list[dict] = client.get(f"/catalog/products/{pid}/images")
    live_by_id = {img["id"]: img for img in live_images}

    log.info("  Restoring image metadata for product %s", pid)
    for bi in backed_up_images:
        img_id = bi["id"]
        if img_id not in live_by_id:
            log.warning("    Image %s not found live — skipping", img_id)
            continue
        client.put(
            f"/catalog/products/{pid}/images/{img_id}",
            {
                "is_thumbnail": bi.get("is_thumbnail", False),
                "sort_order": bi.get("sort_order", 0),
                "description": bi.get("description", ""),
            },
        )
    log.info("    Updated %d image record(s)", len(backed_up_images))


def restore_custom_fields(client: ApiClient, product: dict) -> None:
    pid = product["id"]
    backed_up: list[dict] = product.get("custom_fields", [])

    live: list[dict] = client.get(f"/catalog/products/{pid}/custom-fields")
    live_by_id = {cf["id"]: cf for cf in live}
    backed_up_ids = {cf["id"] for cf in backed_up}

    for live_id in list(live_by_id.keys()):
        if live_id not in backed_up_ids:
            client.delete(f"/catalog/products/{pid}/custom-fields/{live_id}")

    for bcf in backed_up:
        payload = {"name": bcf["name"], "value": bcf["value"]}
        if bcf["id"] in live_by_id:
            client.put(f"/catalog/products/{pid}/custom-fields/{bcf['id']}", payload)
        else:
            client.post(f"/catalog/products/{pid}/custom-fields", payload)

    if backed_up:
        log.info("  Restored %d custom field(s) for product %s", len(backed_up), pid)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def restore_product(client: ApiClient, product: dict) -> None:
    pid = product["id"]
    log.info("=" * 60)
    log.info("Restoring product %s: %s", pid, product.get("name"))
    try:
        restore_product_core(client, product)
        restore_variants(client, product)
        restore_modifiers(client, product)
        restore_images(client, product)
        restore_custom_fields(client, product)
        log.info("✓ Product %s restored successfully", pid)
    except Exception as exc:
        log.error("✗ Failed to restore product %s: %s", pid, exc)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore BigCommerce products from a JSON backup.")
    parser.add_argument("--backup", required=True, help="Path to the JSON backup file")
    parser.add_argument(
        "--product-ids",
        nargs="*",
        type=int,
        default=None,
        help="Optional list of product IDs to restore. Restores all if omitted.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate the backup without making any API calls.",
    )
    args = parser.parse_args()

    with open(args.backup, "r", encoding="utf-8") as f:
        backup: dict[str, Any] = json.load(f)

    products: list[dict] = backup.get("products", [])
    if not products:
        log.error("No products found in backup file.")
        sys.exit(1)

    # Filter to requested IDs if provided
    if args.product_ids:
        id_set = set(args.product_ids)
        products = [p for p in products if p["id"] in id_set]
        if not products:
            log.error("None of the requested product IDs were found in the backup.")
            sys.exit(1)

    log.info("Found %d product(s) to restore.", len(products))

    if args.dry_run:
        log.info("Dry run — no API calls will be made.")
        for p in products:
            log.info(
                "  Would restore: id=%s name='%s' modifiers=%d variants=%d",
                p["id"], p.get("name"), len(p.get("modifiers", [])), len(p.get("variants", [])),
            )
        return

    client = ApiClient()
    errors = []
    for product in products:
        try:
            restore_product(client, product)
        except Exception as exc:
            errors.append((product["id"], str(exc)))

    log.info("=" * 60)
    if errors:
        log.error("Restore completed with %d error(s):", len(errors))
        for pid, err in errors:
            log.error("  Product %s: %s", pid, err)
        sys.exit(1)
    else:
        log.info("All products restored successfully.")


if __name__ == "__main__":
    main()