# bot/config.py
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_WEBHOOK_SECRET = os.getenv("TG_WEBHOOK_SECRET")

BASE_URL = os.getenv("BASE_URL")

OXAPAY_API_KEY = "FJ9YNQ-PRPGBM-XWXL7W-YOJ6OL"
OXAPAY_API_BASE = "https://api.oxapay.com"
