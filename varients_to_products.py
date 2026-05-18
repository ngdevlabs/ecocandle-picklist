"""
BigCommerce: Convert product variants into separate independent products.

Saves a rollback manifest to  rollback_<product_id>_<timestamp>.json
so the operation can be fully reverted with revert_to_variants.py.

Usage:
    python variant_to_product.py --store-hash <STORE_HASH> --token <ACCESS_TOKEN> --product-id <PRODUCT_ID>

Optional flags:
    --delete-original     Delete the original product after splitting (default: False)
    --dry-run             Print what would happen without making any changes
    --manifest-dir DIR    Directory to save the rollback manifest (default: current dir)
"""

import argparse
import json
import sys
import datetime
import requests
from client import ApiClient

api = ApiClient()

def save_manifest(manifest: dict, product_id: int, manifest_dir: str) -> str:
    filename = f"{manifest_dir}/rollback_{product_id}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return filename


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_product(product_id: int) -> dict:
    return api.get(f"/catalog/products/{product_id}?include=variants,images,custom_fields")


def build_new_product_payload(original: dict, variant: dict) -> dict:
    option_values = variant.get("option_values", [])
    option_label = " / ".join(ov["label"] for ov in option_values) if option_values else ""
    new_name = f"{original['name']} - {option_label}" if option_label else original["name"]

    payload = {
        "name": new_name,
        "type": "physical",
        "sku": variant.get("sku") or original.get("sku", ""),
        "price": float(variant.get("price") or original.get("price", 0)),
        "sale_price": float(variant.get("sale_price") or original.get("sale_price") or 0) or None,
        "retail_price": float(variant.get("retail_price") or original.get("retail_price") or 0) or None,
        "cost_price": float(variant.get("cost_price") or original.get("cost_price") or 0) or None,
        "inventory_level": variant.get("inventory_level") or original.get("inventory_level", 0),
        "inventory_warning_level": (
            variant.get("inventory_warning_level") or original.get("inventory_warning_level", 0)
        ),
        "inventory_tracking": "variant",
        "weight": float(variant.get("weight") or original.get("weight", 0)),
        "width":  float(variant.get("width")  or original.get("width", 0)),
        "height": float(variant.get("height") or original.get("height", 0)),
        "depth":  float(variant.get("depth")  or original.get("depth", 0)),
        "is_visible": original.get("is_visible", True),
        "availability": original.get("availability", "available"),
        "condition": original.get("condition", "New"),
        "is_condition_shown": original.get("is_condition_shown", False),
        "brand_id": original.get("brand_id"),
        "categories": original.get("categories", []),
        "description": original.get("description", ""),
        "search_keywords": original.get("search_keywords", ""),
        "meta_keywords": original.get("meta_keywords", []),
        "meta_description": original.get("meta_description", ""),
        "page_title": original.get("page_title", ""),
        "sort_order": original.get("sort_order", 0),
        "is_free_shipping": original.get("is_free_shipping", False),
        "fixed_cost_shipping_price": original.get("fixed_cost_shipping_price"),
        "warranty": original.get("warranty", ""),
        "bin_picking_number": variant.get("bin_picking_number") or original.get("bin_picking_number", ""),
        "upc": variant.get("upc") or original.get("upc", ""),
        "mpn": variant.get("mpn") or original.get("mpn", ""),
        "gtin": variant.get("gtin") or original.get("gtin", ""),
    }
    return {k: v for k, v in payload.items() if v is not None}


def delete_variant(product_id: int, variant_id: int) -> None:
    """Delete a single variant from the original product before re-creating it as a
    standalone product. This frees up the variant's SKU so BigCommerce does not
    raise a 409 duplicate-SKU conflict when the new product is created."""
    api.delete(f"/catalog/products/{product_id}/variants/{variant_id}")
    print(f"  ✓ Deleted variant id={variant_id} from original product")


def copy_images(original_product_id: int, new_product_id: int,
                variant: dict, dry_run: bool) -> list:
    """Copy images to the new product. Returns list of image records for the manifest."""
    images = api.get_paginated(f"/catalog/products/{original_product_id}/images")
    saved = []
    if not images:
        return saved

    variant_image_id = variant.get("image_id")
    ordered = sorted(images, key=lambda img: (img["id"] != variant_image_id, img.get("sort_order", 999)))

    for i, img in enumerate(ordered):
        url = img.get("url_standard") or img.get("url_zoom") or img.get("url_thumbnail")
        if not url:
            continue
        img_payload = {
            "image_url": url,
            "is_thumbnail": i == 0,
            "sort_order": i,
            "description": img.get("description", ""),
        }
        if not dry_run:
            created = api.post(f"/catalog/products/{new_product_id}/images", img_payload)
            saved.append({"new_image_id": created["id"], "url": url})
            print(f"    Image added: {url[:60]}...")
        else:
            print(f"    [DRY-RUN] Would add image: {url[:60]}...")
    return saved


def copy_custom_fields(original_product_id: int, new_product_id: int,
                       dry_run: bool) -> list:
    """Copy custom fields to new product. Returns list of field records for the manifest."""
    fields = api.get_paginated(f"/catalog/products/{original_product_id}/custom-fields")
    saved = []
    for field in fields:
        payload = {"name": field["name"], "value": field["value"]}
        if not dry_run:
            created = api.post(f"/catalog/products/{new_product_id}/custom-fields", payload)
            saved.append({"new_field_id": created["id"], "name": field["name"], "value": field["value"]})
            print(f"    Custom field: {field['name']} = {field['value']}")
        else:
            print(f"    [DRY-RUN] Would add custom field: {field['name']} = {field['value']}")
    return saved


# ---------------------------------------------------------------------------
# Main conversion logic
# ---------------------------------------------------------------------------

def convert_variants_to_products(
    product_id: int,
    delete_original: bool = False,
    dry_run: bool = False,
    manifest_dir: str = ".",
) -> list:
    print(f"\n{'='*60}")
    print(f"Fetching product {product_id} ...")

    original = get_product(product_id)
    variants = original.get("variants", [])

    if not variants:
        print("No variants found — nothing to do.")
        return []

    print(f"Product : {original['name']}")
    print(f"Variants: {len(variants)}\n")

    has_options = any(v.get("option_values") for v in variants)
    if not has_options:
        print("⚠  All variants lack option values (no dropdown options found).")
        print("   The product may already be a simple product. Proceeding anyway...\n")

    # ------------------------------------------------------------------
    # Build the manifest skeleton — captures everything needed to revert
    # ------------------------------------------------------------------
    manifest = {
        "schema_version": "1.0",
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        "store_hash": api.base.split("/stores/")[1].split("/")[0],
        "original_product_id": product_id,
        "original_product_deleted": False,      # updated below if deleted
        "original_product_snapshot": original,  # full snapshot for restore
        "split_products": [],                   # one entry per variant
    }

    new_product_ids = []

    for idx, variant in enumerate(variants, start=1):
        option_label = " / ".join(
            ov["label"] for ov in variant.get("option_values", [])
        ) or f"Variant {variant['id']}"

        print(f"[{idx}/{len(variants)}] Processing variant: {option_label}")

        payload = build_new_product_payload(original, variant)
        print(f"  SKU   : {payload.get('sku', '—')}")
        print(f"  Price : {payload['price']}")
        print(f"  Name  : {payload['name']}")

        split_entry = {
            "variant_id": variant["id"],
            "option_label": option_label,
            "option_values": variant.get("option_values", []),
            "original_variant_snapshot": variant,
            "new_product_id": None,     # filled after creation
            "images": [],
            "custom_fields": [],
        }

        if dry_run:
            print("  [DRY-RUN] Would delete variant then create product — skipping API calls.\n")
        else:
            # Delete the variant first to free up the SKU, then create the
            # standalone product. Without this step BigCommerce returns a 409
            # "duplicate SKU" error because the variant still holds the SKU.
            delete_variant(product_id, variant["id"])

            new_product = api.post("/catalog/products", payload)
            new_id = new_product["id"]
            new_product_ids.append(new_id)
            split_entry["new_product_id"] = new_id
            print(f"  ✓ Created product id={new_id}")

            split_entry["images"] = copy_images(product_id, new_id, variant, dry_run)
            split_entry["custom_fields"] = copy_custom_fields(product_id, new_id, dry_run)
            print()

        manifest["split_products"].append(split_entry)

    # Handle original deletion
    if delete_original:
        if dry_run:
            print(f"[DRY-RUN] Would delete original product id={product_id}")
        else:
            api.delete(f"/catalog/products/{product_id}")
            manifest["original_product_deleted"] = True
            print(f"✓ Original product {product_id} deleted.")
    else:
        print(f"Original product {product_id} kept (pass --delete-original to remove it).")

    # Save manifest (skip in dry-run — nothing real happened)
    if not dry_run:
        manifest_path = save_manifest(manifest, product_id, manifest_dir)
        print(f"\n📄 Rollback manifest saved → {manifest_path}")
        print(f"   Run:  python revert_to_variants.py --manifest {manifest_path} --store-hash ... --token ...")

    print(f"\nDone! {len(new_product_ids)} new products created.")
    return new_product_ids


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert BigCommerce product variants into independent products."
    )
    parser.add_argument("--product-id",  required=True, type=int, help="Source product ID")
    parser.add_argument(
        "--delete-original",
        action="store_true",
        default=False,
        help="Delete the original product after splitting (default: keep it)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would happen without creating or deleting anything",
    )
    parser.add_argument(
        "--manifest-dir",
        default="data",
        metavar="",
        help="Directory to save the rollback manifest JSON (default: current dir)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    try:
        convert_variants_to_products(
            product_id=args.product_id,
            delete_original=args.delete_original,
            dry_run=args.dry_run,
            manifest_dir=args.manifest_dir,
        )
    except requests.HTTPError as exc:
        print(f"\n❌ HTTP Error: {exc}")
        print(f"   Response: {exc.response.text}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)