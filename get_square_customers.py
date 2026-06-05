from square.client import Square
from square.environment import SquareEnvironment
from config import SQUARE_APP_TOKEN
from client import ApiClient
import csv


api = ApiClient()

def main():

    client = Square(
        token=SQUARE_APP_TOKEN,
        environment=SquareEnvironment.PRODUCTION
    )

    cursor = None
    dummy_counter = 40433
    bigC_customers = []
    square_customers = []

    with open("data/loyalty4.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        while True:

            with open("data/cursor.txt", "r", encoding="utf-8") as c:
                cursor = c.read().strip()

            if not cursor:
                cursor = None

            response = client.customers.list(cursor=cursor, limit=10)

            customers = response.response.customers
                
            cursor = response.response.cursor
            
            if not customers:
                break

            customer_ids = [customer.id for customer in customers]

            accounts = client.loyalty.accounts.search(query={
                "customer_ids": customer_ids
            })

            accounts = accounts.loyalty_accounts or []


            for customer in customers:

                email = customer.email_address

                balance = [account.balance for account in accounts if account.customer_id == customer.id]
                points = 0

                if balance:
                    points = balance[0]

                if not email:
                    email = f"requestemailaddress{dummy_counter}@domain.com"
                    dummy_counter += 1

                address = {}
                if customer.address:
                    address = customer.address.dict()

                customer = customer.dict()

                bigC_customers.append({
                    "email": email,
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
                })

                square_customers.append([email, points])


            if square_customers:
                writer.writerows(square_customers)
                print(f"wrote: {len(square_customers)}")
                square_customers = []

            if bigC_customers:
                api.post('/customers', bigC_customers)
                print(f"{len(bigC_customers)} Customer Created")
                bigC_customers = []

            with open('data/cursor.txt', 'w', newline="", encoding='utf-8') as c:
                c.write(cursor)

            f.flush()

            if not cursor:
                break


    print("Export complete")


if __name__ == '__main__':
    main()