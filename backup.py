import requests
import json
from datetime import datetime
from config import BASE_URL, HEADERS, BACKUP_FILE

def get_paginated(endpoint):
    page = 1
    limit = 250
    all_items = []

    while True:
        url = f"{BASE_URL}{endpoint}?page={page}&limit={limit}"
        res = requests.get(url, headers=HEADERS)
        res.raise_for_status()

        data = res.json()
        items = data.get("data", [])
        all_items.extend(items)

        pagination = data.get("meta", {}).get("pagination", {})
        if page >= pagination.get("total_pages", 1):
            break
        page += 1

    return all_items

def backup_products():
    print("Fetching products...")
    products = get_paginated("/catalog/products")

    backup = {
        "created_at": datetime.utcnow().isoformat(),
        "products": []
    }

    total = len(products)

    for idx, product in enumerate(products, 1):
        product_id = product["id"]
        print(f"[{idx}/{total}] Backing up product {product_id} - {product['name']}")

        variants = get_paginated(f"/catalog/products/{product_id}/variants")
        modifiers = get_paginated(f"/catalog/products/{product_id}/modifiers")
        custom_fields = get_paginated(f"/catalog/products/{product_id}/custom-fields")
        images = get_paginated(f"/catalog/products/{product_id}/images")

        backup["products"].append({
            "product": product,
            "variants": variants,
            "modifiers": modifiers,
            "custom_fields": custom_fields,
            "images": images
        })

    filename = BACKUP_FILE

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(backup, f, indent=2)

    print(f"\nBackup completed: {filename}")

if __name__ == "__main__":
    backup_products()
