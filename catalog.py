import csv
from collections import defaultdict
from client import ApiClient

CSV_PRODUCTS = "products_to_convert.csv"
CSV_PICKLIST = "picklist_values.csv"


def load_picklist_mapping():
    mapping = defaultdict(list)

    with open(CSV_PICKLIST, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            parent_sku = row["Parent SKU"].strip()
            mapping[parent_sku].append({
                "label": row["Dropdown Label"].strip(),
                "value_label": row["Product Name"].strip(),
                "product_id": int(row["Product ID"])
            })

    return mapping

def create_picklist_modifier(product_id, display_name, values):
    modifier_payload = {
        "display_name": display_name,
        "type": "product_list",
        "required": False
    }

    modifier = ApiClient(f"/catalog/products/{product_id}/modifiers").post(modifier_payload)
    modifier_id = modifier["id"]

    for value in values:
        value_payload = {
            "label": value["value_label"],
            "value_data": {
                "product_id": value["product_id"]
            }
        }

        ApiClient(f"/catalog/products/{product_id}/modifiers/{modifier_id}/values").post(value_payload)

    return modifier_id

# =====================================
# CONVERT OPTIONS
# =====================================
def convert_options(product_id, sku, picklist_mapping):
    options = ApiClient(f"/catalog/products/{product_id}/options").get()

    grouped = defaultdict(list)
    for row in picklist_mapping[sku]:
        grouped[row["label"]].append(row)

    for option in options:
        option_name = option["display_name"]

        if option_name in grouped:
            print(f"Converting OPTION '{option_name}' on product {product_id}")

            ApiClient(f"/catalog/products/{product_id}/options/{option['id']}").delete()

            create_picklist_modifier(
                product_id,
                option_name,
                grouped[option_name]
            )

# =====================================
# CONVERT MODIFIERS
# =====================================
def convert_modifiers(product_id, sku, picklist_mapping):
    modifiers = ApiClient(f"/catalog/products/{product_id}/modifiers/{modifier['id']}").get(f"/catalog/products/{product_id}/modifiers")

    grouped = defaultdict(list)
    for row in picklist_mapping[sku]:
        grouped[row["label"]].append(row)

    for modifier in modifiers:
        mod_name = modifier["display_name"]

        if mod_name in grouped:
            print(f"Converting MODIFIER '{mod_name}' on product {product_id}")

            ApiClient(f"/catalog/products/{product_id}/modifiers/{modifier['id']}").delete()

            create_picklist_modifier(
                product_id,
                mod_name,
                grouped[mod_name]
            )

# =====================================
# MAIN
# =====================================
def main():
    picklist_mapping = load_picklist_mapping()

    with open(CSV_PRODUCTS, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            sku = row["SKU"].strip()
            product_id = int(row["Product ID"])

            print(f"\nProcessing product {sku} ({product_id})")

            convert_options(product_id, sku, picklist_mapping)
            convert_modifiers(product_id, sku, picklist_mapping)

    print("\nDone!")

if __name__ == "__main__":
    main()
