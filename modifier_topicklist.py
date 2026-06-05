import json
import time
from client import ApiClient

api = ApiClient()


def get_all_pages(endpoint):
    """
    Fetches all pages from a paginated endpoint.
    Handles both list responses and dict responses with a 'data' key.
    """
    results = []
    page = 1
    while True:
        response = api.get(f"{endpoint}?page={page}&limit=250")
        # Handle {"data": [...]} wrapper that BigCommerce often returns
        if isinstance(response, dict):
            items = response.get("data", [])
        elif isinstance(response, list):
            items = response
        else:
            break

        if not items:
            break

        results.extend(items)

        # Stop if we got fewer than the limit (last page)
        if len(items) < 250:
            break
        page += 1

    return results


def delete_existing_options_and_modifiers(product_id, display_name):
    """
    Deletes existing Modifiers and Variant Options matching the display_name.
    Returns True if anything was deleted (caller should wait before re-creating).
    """
    deleted_something = False

    # --- 1. Delete matching Modifiers ---
    modifiers = get_all_pages(f"/catalog/products/{product_id}/modifiers")
    for mod in modifiers:
        if mod.get("display_name").lower() == display_name.lower():
            result = api.delete(f"/catalog/products/{product_id}/modifiers/{mod['id']}")
            print(f"  [DELETE] Modifier '{display_name}' (id={mod['id']}) on product {product_id}")
            deleted_something = True

    # --- 2. Delete ALL Variant Options (they share the same namespace as modifiers for name uniqueness) ---
    options = get_all_pages(f"/catalog/products/{product_id}/options")
    for opt in options:
        if opt.get("display_name").lower() == display_name.lower():
            result = api.delete(f"/catalog/products/{product_id}/options/{opt['id']}")
            print(f"  [DELETE] Variant option '{opt.get('display_name')}' (id={opt['id']}) on product {product_id}")
            deleted_something = True

    return deleted_something


def verify_name_is_free(product_id, display_name, retries=3, delay=1.5):
    """
    After deletion, poll until the name no longer appears in modifiers or options.
    Prevents the race condition that causes the 422.
    """
    for attempt in range(retries):
        time.sleep(delay)
        modifiers = get_all_pages(f"/catalog/products/{product_id}/modifiers")
        options = get_all_pages(f"/catalog/products/{product_id}/options")

        name_exists = any(m.get("display_name") == display_name for m in modifiers) or \
                      any(o.get("display_name") == display_name for o in options)

        if not name_exists:
            print(f"  [OK] Name '{display_name}' is free on product {product_id}")
            return True

        print(f"  [WAIT] Name '{display_name}' still exists (attempt {attempt + 1}/{retries}), retrying...")

    print(f"  [WARN] Name '{display_name}' still exists after {retries} retries — proceeding anyway")
    return False


def create_picklist_modifier(product_id, display_name, items):
    """
    Creates a Pick List (product_list) modifier.
    """
    option_values = []
    for index, item in enumerate(items):
        option_values.append({
            "label": item["name"],
            "sort_order": index,
            "value_data": {
                "product_id": item["id"]
            }
        })

    payload = {
        "type": "product_list_with_images",
        "display_name": display_name,
        "required": True,
        "config":{
            "product_list_adjusts_pricing": False,   # Adjust price → OFF
            "product_list_adjusts_inventory": True,  # Adjust inventory → ON
            "product_list_show_image": True,
            "product_list_shipping_calc": "none",
        },
        "option_values": option_values,
    }

    response = api.post(f"/catalog/products/{product_id}/modifiers", payload)

    if response:
        print(f"  [CREATE] Picklist '{display_name}' created for product {product_id}")
    else:
        print(f"  [FAIL] Could not create Picklist '{display_name}' for product {product_id}")


def run_automation(data):
    for entry in data:
        product_id = entry["main_product_id"]

        for option_group in entry["picklist_options"]:
            for display_name, items in option_group.items():
                print(f"\nProcessing product {product_id} — '{display_name}'")

                # Step 1: Delete old modifiers/options with this name
                deleted = delete_existing_options_and_modifiers(product_id, display_name)

                # Step 2: If we deleted something, wait for BC to settle before re-creating
                if deleted:
                    verify_name_is_free(product_id, display_name)
                else:
                    print(f"  [SKIP DELETE] No existing modifier named '{display_name}' found")

                # Step 3: Create the new Picklist
                create_picklist_modifier(product_id, display_name, items)

                time.sleep(0.5)


# --- Execution ---
if __name__ == "__main__":
    try:
        with open("data/production/clean.json", "r") as f:
            json_data = json.load(f)
        run_automation(json_data)
    except Exception as e:
        print(f"Error: {e}")