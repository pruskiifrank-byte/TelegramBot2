# bot/payment.py
import requests
import json
import time
from bot.config import OXAPAY_API_KEY, BASE_URL

# Импортируем только функции, работающие с БД, и get_order для колбэков
from bot.storage import add_order, update_order, get_order

OXAPAY_INVOICE_URL = "https://api.oxapay.com/v1/payment/invoice"


def create_invoice(user_id, amount_usd, order_id):
    """
    Создание инвойса OxaPay v1.
    order_id должен быть создан и передан из bot.py.
    """

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
        "callback_url": f"{BASE_URL}/oxapay/ipn",
        "return_url": "https://t.me/MrGrinchShopZp_Bot",  # Замените на юзернейм своего бота
        "email": "",
        "order_id": order_id,
        "thanks_message": "Спасибо за оплату!",
        "description": "Номер заказа " + order_id,
        "sandbox": False,
    }

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
    track_id = payment_data["track_id"]

    # Теперь мы только возвращаем данные для обновления записи в БД в bot.py
    return pay_url, track_id


def handle_oxapay_callback(data):
    """
    Обработка IPN callback
    """
    order_id = data.get("order_id")
    track_id = data.get("track_id")
    status = data.get("status")  # "paid", "confirmed", etc
    amount = data.get("amount")

    # 1. Проверяем существование заказа в БД
    existing_order = get_order(order_id)

    if not order_id or not existing_order:
        print(f"Callback error: Order ID {order_id} not found.")
        return False

    # 2. Обновляем статус заказа в БД
    update_order(order_id, status=status)

    # NOTE: В server.py мы вызываем give_product
    return True
