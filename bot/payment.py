import time
import requests
from bot.config import OXAPAY_API_KEY, OXAPAY_API_BASE, BASE_URL
from bot.storage import orders


# Создание платежа OxaPay
def create_invoice(user_id, amount_usd, file_path):

    order_id = str(int(time.time()))  # уникальный ID

    url = f"{OXAPAY_API_BASE}/merchants/request"

    payload = {
        "merchant": OXAPAY_API_KEY,
        "amount": amount_usd,
        "currency": "USD",
        "orderId": order_id,
        "callbackUrl": f"{BASE_URL}/oxapay/ipn",
        "returnUrl": "https://t.me/yourbot",
    }

    response = requests.post(url, json=payload)
    try:
        data = response.json()
    except:
        print("OxaPay ERROR: not JSON:", response.text)
        return None

    print("OXAPAY DEBUG =", data)  # ← Добавлено

    if not data.get("msg"):
        print("OXAPAY ERROR msg=False:", data)
        return None

    pay_url = data["link"]

    orders[order_id] = {
        "user_id": user_id,
        "file": file_path,
        "status": "pending",
        "trackId": data["trackId"],
    }

    return order_id, pay_url


# OxaPay IPN (без подписи)
def handle_oxapay_callback(data):

    order_id = data.get("orderId")
    status = data.get("status")

    if not order_id or not status:
        return False

    if order_id not in orders:
        return False

    orders[order_id]["status"] = status  # paid | pending | canceled | expired

    return True
