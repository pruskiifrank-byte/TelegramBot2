import requests
import json
import time
from bot.config import OXAPAY_API_KEY, BASE_URL
from bot.storage import orders


OXAPAY_INVOICE_URL = "https://api.oxapay.com/v1/payment/invoice"


def create_invoice(user_id, amount_usd, file_path):
    """
    Создание инвойса по новой схеме OxaPay v1
    """

    order_id = f"ORD-{int(time.time())}"

    headers = {"merchant_api_key": OXAPAY_API_KEY, "Content-Type": "application/json"}

    data = {
        "amount": amount_usd,
        "currency": "USD",
        "lifetime": 60,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 10,
        "to_currency": "USDT",
        "auto_withdrawal": False,
        "mixed_payment": True,
        # Webhook для callback
        "callback_url": f"{BASE_URL}/oxapay/ipn",
        # Куда вернуть покупателя после оплаты
        "return_url": "https://t.me/yourbot",
        "email": "",
        "order_id": order_id,
        "thanks_message": "Спасибо за оплату!",
        "description": "Номер заказа " + order_id,
        "sandbox": False,
    }

    response = requests.post(OXAPAY_INVOICE_URL, data=json.dumps(data), headers=headers)

    result = response.json()

    # Успешный ответ строго такой:
    # {
    #   "data": {
    #       "track_id": "...",
    #       "payment_url": "https://pay.oxapay.com/...",
    #       ...
    #   },
    #   "status": 200
    # }

    if result.get("status") != 200:
        return None

    payment_data = result["data"]
    pay_url = payment_data["payment_url"]

    # сохраняем заказ в RAM (storage.py)
    orders[order_id] = {
        "user_id": user_id,
        "file": file_path,
        "status": "pending",
        "track_id": payment_data["track_id"],
    }

    return order_id, pay_url


def handle_oxapay_callback(data):
    """
    Принимаем IPN callback от OxaPay.
    В новой версии API формат другой.
    """

    order_id = data.get("order_id")
    track_id = data.get("track_id")
    status = data.get(
        "status"
    )  # "paid", "confirmed", "expired", "canceled", "underpaid"
    amount = data.get("amount")

    if not order_id or order_id not in orders:
        return False

    # сохраняем статус
    orders[order_id]["status"] = status
    orders[order_id]["paid_amount"] = amount
    orders[order_id]["track_id"] = track_id

    return True
