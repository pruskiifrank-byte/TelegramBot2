import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_WEBHOOK_SECRET = os.getenv("TG_WEBHOOK_SECRET")
DATABASE_URL = os.getenv("DATABASE_URL")

# Настройки URL
BASE_URL = os.getenv("BASE_URL")

# Исправлено: теперь берет значение из .env, а не просто строку "OXAPAY_API_KEY"
OXAPAY_API_KEY = os.getenv("OXAPAY_API_KEY")
OXAPAY_API_BASE = "https://api.oxapay.com"

ADMIN_IDS = [8431930561, 8347430991]
# Линки на помощь
SUPPORT_LINK = "https://t.me/НАШ_ОПЕРАТОР"  # Ссылка на оператора
REVIEWS_LINK = "https://t.me/+NW9rf1wPSl5lZmM6"  # Канал с отзывами
NEWS_LINK = "https://t.me/mrgrinchs"  # Канал с новостями
