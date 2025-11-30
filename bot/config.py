import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_WEBHOOK_SECRET = os.getenv("TG_WEBHOOK_SECRET")

BASE_URL = os.getenv("BASE_URL")

# Исправлено: теперь берет значение из .env, а не просто строку "OXAPAY_API_KEY"
OXAPAY_API_KEY = os.getenv("OXAPAY_API_KEY")
OXAPAY_API_BASE = "https://api.oxapay.com"
DATABASE_URL = os.getenv("DATABASE_URL")
