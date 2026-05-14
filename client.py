from config import HEADERS, BASE_URL
import requests

class ApiClient:

    def __init__(self):
        self.base = BASE_URL

    def get(self, endpoint: str):
        r = requests.get(f"{self.base}{endpoint}", headers=HEADERS)
        r.raise_for_status()
        return r.json()["data"]

    def post(self, endpoint: str, payload):
        r = requests.post(f"{self.base}{endpoint}", headers=HEADERS, json=payload)
        r.raise_for_status()
        return r.json()["data"]

    def delete(self, endpoint: str):
        r = requests.delete(f"{self.base}{endpoint}", headers=HEADERS)
        r.raise_for_status()

    def put(self, endpoint: str, payload):
        url = f"{self.base}{endpoint}"
        print(payload)
        res = requests.put(url, headers=HEADERS, json=payload)
        print(res.text, 'text')
        res.raise_for_status()
        return res.json()

    def get_paginated(self, endpoint: str) -> list:
        """Fetch all pages from a BigCommerce paginated endpoint and return
        a single merged list of all records.

        BigCommerce v3 pagination uses:
        ?page=N&limit=250   (250 is the max allowed limit)
        and signals the last page via:
        response["meta"]["pagination"]["total_pages"]
        """
        results = []
        page = 1
        limit = 250  # maximum BigCommerce allows per page

        while True:
            sep = "&" if "?" in endpoint else "?"
            url = f"{self.base}{endpoint}{sep}page={page}&limit={limit}"

            r = requests.get(url, headers=HEADERS)
            r.raise_for_status()
            body = r.json()

            data = body.get("data", [])
            results.extend(data)

            pagination = body.get("meta", {}).get("pagination", {})
            total_pages = pagination.get("total_pages", 1)

            if page >= total_pages:
                break

            page += 1

        return results