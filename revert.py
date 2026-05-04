import json
from config import BACKUP_FILE
from client import ApiClient

api = ApiClient()

def restore_products():
    
    with open(BACKUP_FILE, "r", encoding="utf-8") as f:
        backup = json.load(f)

    products = backup["products"]
    total = len(products)

    for idx, item in enumerate(products, 1):
        product = item["product"]
        product_id = product["id"]

        print(f"[{idx}/{total}] Restoring product {product_id} - {product['name']}")

        product_payload = {
            "name": product["name"],
            "type": product["type"],
            "sku": product["sku"],
            "price": product["price"],
            "weight": product["weight"],
            "description": product["description"],
            "inventory_level": product["inventory_level"],
            "inventory_tracking": product["inventory_tracking"],
            "categories": product["categories"],
            "is_visible": product["is_visible"]
        }

        api.put(f"/catalog/products/{product_id}", product_payload)

        # Recreate modifiers
        for modifier in item["modifiers"]:
            modifier_payload = {
                k: v for k, v in modifier.items()
                if k not in ["id", "product_id", "option_values"]
            }

            created_modifier = api.post(f"/catalog/products/{product_id}/modifiers", modifier_payload)

            new_modifier_id = created_modifier["data"]["id"]

            for value in modifier.get("option_values", []):
                value_payload = {
                    k: v for k, v in value.items()
                    if k not in ["id", "option_id"]
                }
                api.post(f"/catalog/products/{product_id}/modifiers/{new_modifier_id}/values", value_payload)

        print(f"Restored product {product_id}")

if __name__ == "__main__":
    restore_products()
