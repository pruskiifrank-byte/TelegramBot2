# bot/payment_oxapay.py
import time
import json
import requests
from bot.config import OXAPAY_API_KEY, BASE_URL
from bot.storage import orders


OXAPAY_INVOICE_URL = "https://api.oxapay.com/v1/merchant/create-invoice"


def create_invoice(user_id: int, amount_usd: float, file_path: str):
    """
    Создание платежного инвойса в OxaPay
    """
    order_id = str(int(time.time()))

    # Заголовки — только Content-Type
    headers = {"Content-Type": "application/json"}

    # Тело запроса строго по документации
    payload = {
        "merchant_id": OXAPAY_API_KEY,
        "amount": amount_usd,
        "currency": "USD",
        "order_id": order_id,
        "callback_url": f"{BASE_URL}/oxapay/ipn",
        "success_url": "https://t.me/yourbot",
        "cancel_url": "https://t.me/yourbot",
        "description": "Digital product",
        "lifetime": 30,
        "under_paid_cover": False,
        "fee_paid_by_payer": True,
    }

    response = requests.post(OXAPAY_INVOICE_URL, json=payload, headers=headers)

    try:
        data = response.json()
    except:
        print("OXAPAY ERROR: invalid JSON")
        return None

    print("OXAPAY DEBUG =", data)

    # Проверка успешности
    if data.get("result") != 100:
        print("OXAPAY ERROR:", data.get("message"))
        return None

    pay_link = data.get("payment_url")
    track_id = data.get("track_id")

    if not pay_link:
        print("OXAPAY ERROR: no payment_url")
        return None

    # сохраняем заказ
    orders[order_id] = {
        "user_id": user_id,
        "file": file_path,
        "status": "pending",
        "trackId": track_id,
    }

    return order_id, pay_link


def handle_oxapay_callback(data: dict):
    """
    Обработка IPN от OxaPay
    """
    order_id = data.get("order_id")
    status = data.get("status")

    if not order_id or not status:
        return False

    if order_id not in orders:
        return False

    # paid / canceled / expired / pending / underpaid
    orders[order_id]["status"] = status

    return True
