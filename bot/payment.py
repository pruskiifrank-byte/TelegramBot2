import requests
import json
import time
from bot.config import OXAPAY_API_KEY, BASE_URL
# Импортируем функции управления хранилищем, а не просто словарь
from bot.storage import orders, add_order, update_order

OXAPAY_INVOICE_URL = "https://api.oxapay.com/v1/payment/invoice"

def create_invoice(user_id, amount_usd, file_path):
    """
    Создание инвойса OxaPay v1
    """
    order_id = f"ORD-{int(time.time())}"

    headers = {
        "merchant_api_key": OXAPAY_API_KEY, 
        "Content-Type": "application/json"
    }

    data = {
        "amount": amount_usd,
        "currency": "USD",
        "lifetime": 60,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 10,
        "to_currency": "USDT",
        "auto_withdrawal": False,
        "mixed_payment": True,
        "callback_url": f"{BASE_URL}/oxapay/ipn",
        "return_url": "https://t.me/Elk_ShopBot", # Замените на юзернейм своего бота
        "email": "",
        "order_id": order_id,
        "thanks_message": "Спасибо за оплату!",
        "description": "Номер заказа " + order_id,
        "sandbox": False,
    }

    # ВАЖНО: json=data вместо data=json.dumps
    try:
        response = requests.post(OXAPAY_INVOICE_URL, json=data, headers=headers)
        result = response.json()
    except Exception as e:
        print(f"Request error: {e}")
        return None

    if result.get("status") != 200:
        print(f"OxaPay API error: {result}")
        return None

    payment_data = result["data"]
    pay_url = payment_data["payment_url"]

    # ВАЖНО: Используем add_order для сохранения на диск
    new_order_data = {
        "user_id": user_id,
        "file": file_path,
        "status": "pending",
        "track_id": payment_data["track_id"],
        "price": amount_usd # Сохраняем цену сразу
    }
    add_order(order_id, new_order_data)

    return order_id, pay_url


def handle_oxapay_callback(data):
    """
    Обработка IPN callback
    """
    order_id = data.get("order_id")
    track_id = data.get("track_id")
    status = data.get("status") # "paid", "confirmed", etc
    amount = data.get("amount")

    if not order_id or order_id not in orders:
        return False

    # ВАЖНО: Используем update_order для сохранения на диск
    update_order(
        order_id, 
        status=status, 
        paid_amount=amount, 
        track_id=track_id
    )

    return True