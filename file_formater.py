import csv
import json

def convert_csv_to_json(input_file, output_file):
    # This dictionary will store our products using main_product_id as the key
    products_map = {}

    with open(input_file, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            # Handle the "123,124" logic: Split by comma and strip whitespace
            raw_ids = row['main_product_id'].strip()
            if raw_ids:
                target_ids = [id.strip() for id in raw_ids.split(',') if id.strip()]
            else:
                # If the first column is empty (as seen in your rows 2-4), 
                # we continue using the target_ids from the last row that had them.
                pass 

            # Data for the specific picklist item
            item_data = {
                "id": int(row['product_id']),
                "sku": row['product_sku'],
                "name": row['product_title']
            }
            
            dropdown_title = row['dropdown_title'].strip()

            for pid_str in target_ids:
                pid = int(pid_str)
                
                # 1. Initialize product entry if it doesn't exist
                if pid not in products_map:
                    products_map[pid] = {
                        "main_product_id": pid,
                        "picklist_options": []
                    }
                
                # 2. Check if this dropdown_title already exists in picklist_options
                # We look for a dict that has the dropdown_title as a key
                existing_option_group = None
                for option in products_map[pid]["picklist_options"]:
                    if dropdown_title in option:
                        existing_option_group = option
                        break
                
                if existing_option_group:
                    # Append item to existing dropdown list
                    existing_option_group[dropdown_title].append(item_data)
                else:
                    # Create a new dropdown entry
                    products_map[pid]["picklist_options"].append({
                        dropdown_title: [item_data]
                    })

    # Convert the map back into a simple list for the final JSON
    final_output = list(products_map.values())

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, indent=4)
    
    print(f"Successfully converted {input_file} to {output_file}")

if __name__ == "__main__":
    convert_csv_to_json('data/demo/all-products.csv', 'data/demo/clean.json')