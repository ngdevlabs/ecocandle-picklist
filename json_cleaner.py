import json
import sys
from collections import defaultdict

def deduplicate_picklist_options(data):
    for product in data:
        picklist_options = product.get("picklist_options", [])
        
        for option_dict in picklist_options:
            for option_name, values in option_dict.items():
                seen_ids = set()
                unique_values = []
                duplicates = []
                
                for item in values:
                    item_id = item.get("id")
                    if item_id not in seen_ids:
                        seen_ids.add(item_id)
                        unique_values.append(item)
                    else:
                        duplicates.append(item)
                
                if duplicates:
                    print(f"  Product {product.get('main_product_id')} → '{option_name}': "
                          f"removed {len(duplicates)} duplicate(s): "
                          f"{[d.get('sku', d.get('id')) for d in duplicates]}")
                
                option_dict[option_name] = unique_values
    
    return data

def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else "input.json"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "output.json"
    
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print(f"Processing '{input_file}'...\n")
    cleaned_data = deduplicate_picklist_options(data)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(cleaned_data, f, indent=4, ensure_ascii=False)
    
    print(f"\nDone. Cleaned file saved to '{output_file}'.")

if __name__ == "__main__":
    main()