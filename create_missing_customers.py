
import csv
import json
from client import ApiClient

api = ApiClient()

def map_customer_for_bigCommerce(customer):
    address = customer.get('adress', {})
    return {
        "email": customer.get("email", "unknown"),
        "first_name": customer.get("given_name", "unknown"),
        "last_name": customer.get("family_name", "unknown"),
        "company": customer.get("company_name", "unknown"),
        "phone": customer.get("phone_number", "unknown"),
        "notes": customer.get("note", "unknonw"),

        "addresses": [
            {
            "first_name": customer.get("given_name", "unknonw"),
            "last_name": customer.get("family_name", "unknown"),
            "company": customer.get("company_name", "unknown"),

            "address1": address.get("address_line1", "unknown"),
            "address2": address.get("address_line2", "unknown"),

            "city": address.get("locality", "unknown"),

            "state_or_province": address.get("administrative_district_level1", "Wisconsin"),

            "postal_code": address.get("postal_code", "54136"),

            "country_code": address.get("country", "US"),

            "phone": customer.get("phone_number", "unknown"),

            "address_type": "residential"
            }
        ]
    }

def main():

    square_customers = {}
    new_customers = []
    total = 0

    with open('data/production/loyalty/square_customers.json', 'r') as j:
        square_customers = json.load(j)

    with open('data/production/customer_notfound.csv', 'r') as f:
        reader = csv.DictReader(f)

        for row in reader:
            email = row.get('Email')
            customer = square_customers.get(email)

            if customer:
                print('Found the email mapping user data')
                new_customers.append(map_customer_for_bigCommerce(customer))

                if len(new_customers) == 10:
                    print(f"creating {len(new_customers)} customers in bigcommerce")
                    api.post('/customers', new_customers)
                    total = total + 10
                    print(f"{total} customers created in bigCommerce")
                    new_customers = []

    # if any customers still remain create them 
    if len(new_customers):
        print(f'creating remaing {len(new_customers)}')
        api.post('/customers', new_customers)


if __name__ == '__main__':
    main()