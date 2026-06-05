"""
backup_products.py
──────────────────
Reads product IDs from the variants CSV produced by fetch_variants.py,
fetches the complete product payload (all fields + variants + options +
custom fields + images + videos + bulk-pricing rules + modifiers) from
BigCommerce, and writes a single timestamped JSON backup file.

Usage:
    python backup_products.py
    python backup_products.py --csv products_with_variants.csv --out backups/
"""

import argparse
import csv
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

import requests
from config import HEADERS, BASE_URL

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Tunables ─────────────────────────────────────────────────────────────────
MAX_WORKERS     = 10
CONNECT_TIMEOUT = 15
READ_TIMEOUT    = 30
MAX_RETRIES     = 5
BACKOFF_BASE    = 2


# ─── Resilient HTTP helpers ───────────────────────────────────────────────────
def _get(endpoint: str, params: Optional[dict] = None) -> dict:
    url = f"{BASE_URL}{endpoint}"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log.debug("GET %s params=%s (attempt %d)", endpoint, params, attempt)
            r = requests.get(
                url,
                headers=HEADERS,
                params=params,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )

            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 10))
                log.warning(
                    "429 Too Many Requests — waiting %ds (attempt %d/%d)",
                    wait, attempt, MAX_RETRIES,
                )
                time.sleep(wait)
                continue

            r.raise_for_status()
            return r.json()

        except requests.exceptions.ConnectTimeout:
            log.warning("Connect timeout on %s (attempt %d/%d)", endpoint, attempt, MAX_RETRIES)
        except requests.exceptions.ReadTimeout:
            log.warning("Read timeout on %s (attempt %d/%d)", endpoint, attempt, MAX_RETRIES)
        except requests.exceptions.ConnectionError as exc:
            log.warning("Connection error on %s: %s (attempt %d/%d)", endpoint, exc, attempt, MAX_RETRIES)
        except requests.exceptions.HTTPError as exc:
            if r.status_code >= 500:
                log.warning("Server error %d on %s (attempt %d/%d)", r.status_code, endpoint, attempt, MAX_RETRIES)
            else:
                log.error("HTTP %d on %s — not retrying", r.status_code, endpoint)
                raise

        if attempt < MAX_RETRIES:
            wait = BACKOFF_BASE ** attempt
            log.info("Retrying in %ds…", wait)
            time.sleep(wait)

    raise RuntimeError(f"All {MAX_RETRIES} attempts failed for {endpoint}")


def _get_single(endpoint: str) -> Optional[dict]:
    """Fetch a single-object endpoint; returns the 'data' dict or None on 404."""
    try:
        body = _get(endpoint)
        return body.get("data")
    except requests.exceptions.HTTPError as exc:
        if exc.response.status_code == 404:
            return None
        raise


def _get_paginated(endpoint: str) -> list:
    """Fetch all pages and return a flat list."""
    results = []
    page    = 1
    limit   = 250

    while True:
        body        = _get(endpoint, params={"page": page, "limit": limit})
        data        = body.get("data", [])
        results.extend(data)

        pagination  = body.get("meta", {}).get("pagination", {})
        total_pages = pagination.get("total_pages", 1)

        if page >= total_pages:
            break
        page += 1

    return results


# ─── CSV reader ───────────────────────────────────────────────────────────────
def load_product_ids_from_csv(csv_path: str) -> list[int]:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    ids = set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ids.add(int(row["id"]))
            except (KeyError, ValueError):
                log.warning("Skipping invalid row: %s", row)

    log.info("Loaded %d unique product IDs from %s", len(ids), csv_path)
    return sorted(ids)


# ─── Full product fetcher ─────────────────────────────────────────────────────
def fetch_full_product(product_id: int) -> Optional[dict]:
    """
    Fetch every piece of data BigCommerce exposes for a single product:
      • core product fields
      • variants           /v3/catalog/products/{id}/variants
      • options            /v3/catalog/products/{id}/options
      • modifiers          /v3/catalog/products/{id}/modifiers
      • images             /v3/catalog/products/{id}/images
      • videos             /v3/catalog/products/{id}/videos
      • custom fields      /v3/catalog/products/{id}/custom-fields
      • bulk pricing rules /v3/catalog/products/{id}/bulk-pricing-rules
      • metafields         /v3/catalog/products/{id}/metafields
    """
    base = f"/catalog/products/{product_id}"

    # Core product
    product = _get_single(base)
    if product is None:
        log.warning("Product %d not found — skipping", product_id)
        return None

    # Sub-resources (all paginated)
    sub_resources = {
        "variants":           f"{base}/variants",
        "options":            f"{base}/options",
        "modifiers":          f"{base}/modifiers",
        "images":             f"{base}/images",
        "videos":             f"{base}/videos",
        "custom_fields":      f"{base}/custom-fields",
        "bulk_pricing_rules": f"{base}/bulk-pricing-rules",
        "metafields":         f"{base}/metafields",
    }

    for key, endpoint in sub_resources.items():
        try:
            product[key] = _get_paginated(endpoint)
        except Exception as exc:
            log.warning("Could not fetch %s for product %d: %s", key, product_id, exc)
            product[key] = []

    return product


# ─── Threaded orchestrator ────────────────────────────────────────────────────
_progress_lock  = threading.Lock()
_progress_count = 0


def _worker(product_id: int, total: int) -> Optional[dict]:
    global _progress_count

    result = fetch_full_product(product_id)

    with _progress_lock:
        _progress_count += 1
        done = _progress_count

    status = "OK" if result else "SKIPPED"
    name   = (result or {}).get("name", "")[:60]
    log.info("[%d/%d] Product %-6d  %-8s  %s", done, total, product_id, status, name)

    return result


def backup_products(product_ids: list[int]) -> list[dict]:
    global _progress_count
    _progress_count = 0

    total = len(product_ids)
    log.info("Backing up %d products with %d threads…", total, MAX_WORKERS)

    products = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_worker, pid, total): pid
            for pid in product_ids
        }
        for future in as_completed(futures):
            pid = futures[future]
            try:
                result = future.result()
                if result:
                    products.append(result)
            except Exception as exc:
                log.error("Unhandled error for product %d: %s", pid, exc)

    # Sort by product_id for deterministic output
    products.sort(key=lambda p: p["id"])
    return products


# ─── JSON writer ──────────────────────────────────────────────────────────────
def write_backup(products: list[dict], out_dir: str = ".") -> str:
    if not products:
        log.warning("Nothing to back up — file not written.")
        return ""

    os.makedirs(out_dir, exist_ok=True)

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(out_dir, f"products_backup_{timestamp}.json")

    payload = {
        "meta": {
            "created_at":    datetime.now().isoformat(),
            "product_count": len(products),
            "source":        BASE_URL,
        },
        "products": products,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    log.info("Backup saved → %s  (%.2f MB, %d products)", output_path, size_mb, len(products))
    return output_path


# ─── Entry point ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Backup BigCommerce products to JSON")
    parser.add_argument(
        "--csv", default="data/production/products-to-picklist.csv",
        help="Path to the variants CSV (default: products_with_variants.csv)",
    )
    parser.add_argument(
        "--out", default="data/production",
        help="Output directory for the backup JSON (default: current directory)",
    )
    args = parser.parse_args()

    start = time.time()

    product_ids = load_product_ids_from_csv(args.csv)
    products    = backup_products(product_ids)
    write_backup(products, out_dir=args.out)

    log.info("Total time: %.1fs", time.time() - start)


if __name__ == "__main__":
    main()