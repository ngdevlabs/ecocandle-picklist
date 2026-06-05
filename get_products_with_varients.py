import csv
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import requests
from config import HEADERS, BASE_URL

# ─── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Tunables ─────────────────────────────────────────────────────────────────
MAX_WORKERS      = 10      # concurrent variant-fetch threads
CONNECT_TIMEOUT  = 15      # seconds to wait for a TCP connection
READ_TIMEOUT     = 30      # seconds to wait for a response
MAX_RETRIES      = 5       # max attempts per request
BACKOFF_BASE     = 2       # exponential-backoff multiplier (2^attempt seconds)


# ─── Resilient HTTP helper ─────────────────────────────────────────────────────
def _get(endpoint: str, params: Optional[dict] = None) -> dict:
    """
    GET with:
      • configurable timeouts
      • automatic retry with exponential backoff on connection errors
      • automatic pause + retry on 429 (rate-limit) using Retry-After header
    """
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

            # ── Rate-limited ──────────────────────────────────────────────────
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 10))
                log.warning(
                    "429 Too Many Requests on %s — waiting %ds before retry %d/%d",
                    endpoint, wait, attempt, MAX_RETRIES,
                )
                time.sleep(wait)
                continue

            r.raise_for_status()
            return r.json()

        except requests.exceptions.ConnectTimeout:
            log.warning(
                "Connect timeout on %s (attempt %d/%d)", endpoint, attempt, MAX_RETRIES
            )
        except requests.exceptions.ReadTimeout:
            log.warning(
                "Read timeout on %s (attempt %d/%d)", endpoint, attempt, MAX_RETRIES
            )
        except requests.exceptions.ConnectionError as exc:
            log.warning(
                "Connection error on %s: %s (attempt %d/%d)",
                endpoint, exc, attempt, MAX_RETRIES,
            )
        except requests.exceptions.HTTPError as exc:
            # 5xx → retry; anything else → give up immediately
            if r.status_code >= 500:
                log.warning(
                    "Server error %d on %s (attempt %d/%d)",
                    r.status_code, endpoint, attempt, MAX_RETRIES,
                )
            else:
                log.error("HTTP %d on %s — not retrying", r.status_code, endpoint)
                raise

        if attempt < MAX_RETRIES:
            wait = BACKOFF_BASE ** attempt          # 2, 4, 8, 16 …
            log.info("Retrying in %ds…", wait)
            time.sleep(wait)

    raise RuntimeError(f"All {MAX_RETRIES} attempts failed for {endpoint}")


# ─── Paginated fetch ───────────────────────────────────────────────────────────
def get_paginated(endpoint: str) -> list:
    results = []
    page     = 1
    limit    = 250

    while True:
        body       = _get(endpoint, params={"page": page, "limit": limit})
        data       = body.get("data", [])
        results.extend(data)

        pagination  = body.get("meta", {}).get("pagination", {})
        total_pages = pagination.get("total_pages", 1)
        log.debug("%s  page %d/%d  (+%d records)", endpoint, page, total_pages, len(data))

        if page >= total_pages:
            break
        page += 1

    return results


# ─── Per-product worker ────────────────────────────────────────────────────────
_progress_lock  = threading.Lock()
_progress_count = 0

def fetch_variants_for_product(product: dict, total: int) -> list:
    global _progress_count

    product_id   = product["id"]
    product_name = product["name"]

    try:
        variants = get_paginated(f"/catalog/products/{product_id}/variants")
    except Exception as exc:
        log.error("Failed to fetch variants for product %d (%s): %s", product_id, product_name, exc)
        variants = []

    with _progress_lock:
        _progress_count += 1
        done = _progress_count
    log.info("[%d/%d] Product %-6d  variants=%d  %s", done, total, product_id, len(variants), product_name[:60])

    # Skip simple products (≤1 variant means no real option combinations)
    if len(variants) <= 1:
        return []

    rows = []
    for variant in variants:
        rows.append({
            "product_id":    product_id,
            "product_name":  product_name,
            "variant_id":    variant.get("id"),
            "variant_sku":   variant.get("sku", ""),
            "variant_price": variant.get("price", ""),
            "option_values": ", ".join(
                f"{ov['option_display_name']}: {ov['label']}"
                for ov in variant.get("option_values", [])
            ),
        })
    return rows


# ─── Main orchestrator ─────────────────────────────────────────────────────────
def fetch_products_with_variants() -> list:
    global _progress_count
    _progress_count = 0

    log.info("Fetching product catalogue…")
    products = get_paginated("/catalog/products")
    total    = len(products)
    log.info("Catalogue loaded — %d products. Starting variant fetch with %d threads…", total, MAX_WORKERS)

    all_rows = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(fetch_variants_for_product, p, total): p["id"]
            for p in products
        }
        for future in as_completed(futures):
            product_id = futures[future]
            try:
                rows = future.result()
                all_rows.extend(rows)
            except Exception as exc:
                log.error("Unhandled error for product %d: %s", product_id, exc)

    products_with_variants = len({r["product_id"] for r in all_rows})
    log.info(
        "Done — %d products have variants → %d variant rows total",
        products_with_variants, len(all_rows),
    )
    return all_rows


# ─── CSV writer ───────────────────────────────────────────────────────────────
def write_csv(rows: list, output_file: str = "products_with_variants.csv") -> None:
    if not rows:
        log.warning("No rows to write — CSV not created.")
        return

    fieldnames = [
        "product_id",
        "product_name",
        "variant_id",
        "variant_sku",
        "variant_price",
        "option_values",
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    log.info("CSV saved → %s  (%d rows)", output_file, len(rows))


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    start = time.time()
    rows  = fetch_products_with_variants()
    write_csv(rows)
    log.info("Total time: %.1fs", time.time() - start)