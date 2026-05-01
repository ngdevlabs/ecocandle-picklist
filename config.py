from dotenv import load_dotenv
import os

load_dotenv()

STORE_HASH = os.getenv('STORE_HASH')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')

BACKUP_FILE = "bigcommerce_backup.json"

BASE_URL = f"https://api.bigcommerce.com/stores/{STORE_HASH}/v3"
HEADERS = {
    "X-Auth-Token": ACCESS_TOKEN,
    "Accept": "application/json",
    "Content-Type": "application/json"
}