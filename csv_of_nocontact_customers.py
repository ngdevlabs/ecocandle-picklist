import json
import csv

def main():
    with open('data/production/deleted_customer.csv', 'w') as c:
        writer = csv.writer(c)
        writer.writerow(['Email'])
        with open('data/production/loyalty/square_customers.json', 'r', encoding='utf-8') as f:
            customers: dict[str, dict[str, str]] = json.load(f)

            for email, customer in customers.items():
                if email.startswith("requestemailaddress") and (customer.get('phone_number') == 'unknown' or not customer.get('phone_number')):
                    name = customer.get("given_name")
                    if name and len([name for number in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'] if number in name]):
                        print(name, 'nameee')
                    writer.writerow([email])

if __name__ == '__main__':
    main()