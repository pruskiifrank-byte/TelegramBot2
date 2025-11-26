import hmac
import hashlib
import requests
import os
from dotenv import load_dotenv

load_dotenv()

MERCHANT_SECRET = os.getenv("SECRET_KEY")

# ==== ТЕСТОВЫЕ ДАННЫЕ ====
txID = "test123"
amount = "10"

# === ГЕНЕРАЦИЯ ПРАВИЛЬНОЙ ПОДПИСИ ===
raw = f"{txID}{amount}"  # <-- ВОТ ЭТО ПРОШЛО ВЕРИФИКАЦИЮ
signature = hmac.new(MERCHANT_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()

# === URL СЕРВЕРА ===
url = "https://telegrambot-z2bn.onrender.com/payment_callback"

data = {"txID": txID, "amount": amount, "signature": signature}

print("Sending:", data)

r = requests.post(url, data=data)
print("Response:", r.status_code, r.text)
