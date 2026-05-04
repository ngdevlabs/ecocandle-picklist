import json
import time
from client import ApiClient

api = ApiClient()

def revert_product_changes(product_id, option_name, items):
    """
    Deletes the Pick List modifier and restores the original Dropdown (as a Variant Option).
    """
    # 1. Delete the Pick List Modifier
    modifiers = api.get(f"/catalog/products/{product_id}/modifiers")
    if modifiers:
        for mod in modifiers:
            if mod['display_name'] == option_name and mod['type'] == 'product_list':
                api.delete(f"/catalog/products/{product_id}/modifiers/{mod['id']}")
                print(f"Removed Pick List modifier '{option_name}' from product {product_id}")

    # 2. Re-create the Variant Option (Dropdown)
    # Note: This creates a Multiple Choice (dropdown) variant option
    option_values = []
    for index, item in enumerate(items):
        option_values.append({
            "label": item['name'],
            "sort_order": index,
            "is_default": False
        })

    payload = {
        "name": option_name,
        "display_name": option_name,
        "type": "dropdown",
        "option_values": option_values
    }

    response = api.post(f"/catalog/products/{product_id}/options", payload)
    
    if response:
        print(f"Successfully restored Variant Dropdown '{option_name}' for product {product_id}")
    else:
        print(f"Failed to restore Variant for {product_id}")

def run_revert(data):
    for entry in data:
        product_id = entry['main_product_id']
        for option_group in entry['picklist_options']:
            for display_name, items in option_group.items():
                print(f"Reverting Product ID: {product_id}...")
                
                try:
                    revert_product_changes(product_id, display_name, items)
                except Exception as e:
                    print(f"Error reverting product {product_id}: {e}")
                
                time.sleep(0.5)

if __name__ == "__main__":
    try:
        with open('data/demo/clean.json', 'r') as f:
            json_data = json.load(f)
        run_revert(json_data)
    except Exception as e:
        print(f"Error loading file: {e}")