from config import HEADERS, BASE_URL
import requests

class ApiClient:

    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    def get(self):
        r = requests.get(f"{BASE_URL}{self.endpoint}", headers=HEADERS)
        r.raise_for_status()
        return r.json()["data"]

    def post(self, payload):
        r = requests.post(f"{BASE_URL}{self.endpoint}", headers=HEADERS, json=payload)
        r.raise_for_status()
        return r.json()["data"]

    def delete(self):
        r = requests.delete(f"{BASE_URL}{self.endpoint}", headers=HEADERS)
        r.raise_for_status()

    def put(self, payload):
        url = f"{BASE_URL}{self.endpoint}"
        res = requests.put(url, headers=HEADERS, json=payload)
        res.raise_for_status()
        return res.json()