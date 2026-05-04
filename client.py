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