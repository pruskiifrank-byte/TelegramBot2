# bot/payment_oxapay.py
import time
import json
import requests
from bot.config import OXAPAY_API_KEY, BASE_URL
from bot.storage import orders


OXAPAY_INVOICE_URL = "https://api.oxapay.com/v1/payment/invoice"


def create_invoice(user_id: int, amount_usd: float, file_path: str):
    """
    Создание платежного инвойса в Oxapay
    """

    order_id = str(int(time.time()))

    headers = {"merchant_api_key": OXAPAY_API_KEY, "Content-Type": "application/json"}

    payload = {
        "amount": amount_usd,
        "currency": "USD",
        "lifetime": 30,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 0,
        "to_currency": "USDT",
        "auto_withdrawal": False,
        "mixed_payment": False,
        "callback_url": f"{BASE_URL}/oxapay/ipn",
        "return_url": "https://t.me/yourbot",
        "email": "",
        "order_id": order_id,
        "thanks_message": "Спасибо за покупку!",
        "description": "Digital Product",
        "sandbox": False,
    }

    response = requests.post(
        OXAPAY_INVOICE_URL, data=json.dumps(payload), headers=headers
    )

    try:
        data = response.json()
    except:
        print("OXAPAY ERROR: invalid JSON")
        return None

    print("OXAPAY DEBUG =", data)

    # Успешный результат — result == 100
    if data.get("result") != 100:
        print("OXAPAY ERROR: result != 100")
        return None

    pay_link = data.get("payLink")
    track_id = data.get("trackId")

    if not pay_link:
        print("OXAPAY ERROR: no payLink")
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
    Обработка IPN от Oxapay
    """

    order_id = data.get("order_id")
    status = data.get("status")

    if not order_id or not status:
        return False

    if order_id not in orders:
        return False

    # Пример статусов:
    # paid, pending, expired, underpaid, canceled
    orders[order_id]["status"] = status

    return True
