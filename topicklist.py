import json
import time
from client import ApiClient

api = ApiClient()

def delete_existing_options_and_modifiers(product_id, option_name):
    """
    Deletes existing Modifiers and Variant Options to clear the way for the Picklist.
    """
    # 1. Delete Modifiers with the same name
    modifiers = api.get(f"/catalog/products/{product_id}/modifiers")
    for mod in modifiers:
        if mod['display_name'] == option_name:
            api.delete(f"/catalog/products/{product_id}/modifiers/{mod['id']}")
            print(f"Deleted existing modifier '{option_name}' for product {product_id}")

    # 2. Delete Variant Options (This removes the variants/dropdowns)
    options = api.get(f"/catalog/products/{product_id}/options")
    for opt in options:
        # You can add a name check here if you only want to delete specific variant sets
        api.delete(f"/catalog/products/{product_id}/options/{opt['id']}")
        print(f"Deleted variant option '{opt['display_name']}' for product {product_id}")

def create_picklist_modifier(product_id, display_name, items):
    """
    Creates a Pick List (product_list) modifier.
    """
    # Prepare the option values for the picklist
    option_values = []
    for index, item in enumerate(items):
        option_values.append({
            "label": item['name'],
            "sort_order": index,
            "value_data": {
                "product_id": item['id']
            }
        })

    payload = {
        "type": "product_list", # This creates the Pick List type
        "display_name": display_name,
        "required": False,
        "option_values": option_values
    }

    response = api.post(f"/catalog/products/{product_id}/modifiers", payload)
    
    if response:
        print(f"Successfully created Picklist '{display_name}' for product {product_id}")
    else:
        print(f"Failed to create Picklist for {product_id}: {response.text}")

def run_automation(data):
    for entry in data:
        product_id = entry['main_product_id']
        # Each entry has a list of picklist_options (usually just one dictionary)
        for option_group in entry['picklist_options']:
            for display_name, items in option_group.items():
                print(f"Processing Product ID: {product_id}...")
                
                # Step 1: Clean up old data
                delete_existing_options_and_modifiers(product_id, display_name)
                
                # Step 2: Create new Picklist
                create_picklist_modifier(product_id, display_name, items)
                
                # Small sleep to avoid hitting rate limits too hard
                time.sleep(0.5)

# --- Execution ---
if __name__ == "__main__":
    # Assuming your JSON is in a file named 'data.json'
    try:
        with open('data/demo/clean.json', 'r') as f:
            json_data = json.load(f)
        run_automation(json_data)
    except Exception as e:
        print(f"Error: {e}")