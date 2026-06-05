from dotenv import load_dotenv
import os

load_dotenv()

STORE_HASH = os.getenv('STORE_HASH')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')

BACKUP_FILE = "data/production/products_backup.json"

BASE_URL = f"https://api.bigcommerce.com/stores/{STORE_HASH}/v3"
BIGC_HEADERS = {
    "X-Auth-Token": ACCESS_TOKEN,
    "Accept": "application/json",
    "Content-Type": "application/json"
}

SQUARE_APP_ID = os.getenv('SQUARE_APP_ID')
SQUARE_APP_TOKEN = os.getenv('SQUARE_APP_TOKEN')

SQUARE_HEADERS = {
    "Authorization": f"Bearer {SQUARE_APP_TOKEN}",
    "Content-Type":  "application/json",
    "Square-Version": "2024-01-17",
}
