from client import ApiClient
from datetime import datetime

api = ApiClient()

def main():

    page = 6844
    limit = 250

    while True:
        print(f'getting {limit} customer from page {page}')
        customers = api.get(f'/customers?page={page}&limit={limit}')

        ids = []

        print('checking customers ', len(customers))
        for customer in customers:
            email: str = customer.get('email')
            phone: str = customer.get('phone')

            if email.startswith('requestemailaddress') and (phone == 'unknown' or not phone):
                print(f"customer {email} {customer.get('id')} found with no information connected")
                ids.append(str(customer.get('id')))

        if len(ids):
            print('deleting customers')
            print(f'/customers?id:in={','.join(ids)}')
            api.delete(f'/customers?id:in={','.join(ids)}')
            ids = []

        page += 1

if __name__ == '__main__':
    main()