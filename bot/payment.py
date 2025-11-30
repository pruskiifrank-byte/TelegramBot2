# bot/payment.py
import requests
from bot.config import OXAPAY_API_KEY, BASE_URL

# Нам нужно обновлять базу при колбэке, поэтому импортируем update_order
from bot.storage import update_order

OXAPAY_INVOICE_URL = "https://api.oxapay.com/v1/payment/invoice"
OXAPAY_STATUS_URL = "https://api.oxapay.com/v1/payment/status"


def create_invoice(user_id, amount_usd, order_id):
    """Создание ссылки на оплату."""
    headers = {"merchant_api_key": OXAPAY_API_KEY, "Content-Type": "application/json"}
    data = {
        "amount": amount_usd,
        "currency": "USD",
        "lifetime": 60,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 5,
        "to_currency": "USDT",
        "callback_url": f"{BASE_URL}/oxapay/ipn",
        "description": f"Order {order_id}",
        "order_id": order_id,
    }
    try:
        response = requests.post(
            OXAPAY_INVOICE_URL, json=data, headers=headers, timeout=10
        )
        result = response.json()
        if result.get("result") == 100:
            return result["data"]["payment_url"], result["data"]["track_id"]
    except Exception as e:
        print(f"OxaPay Create Error: {e}")
    return None


def verify_payment_via_api(track_id):
    """
    Проверяет реальный статус заказа через API OxaPay.
    Возвращает True, если заказ оплачен.
    """
    if not track_id:
        return False

    data = {"merchant_api_key": OXAPAY_API_KEY, "track_id": track_id}
    try:
        response = requests.post(OXAPAY_STATUS_URL, json=data, timeout=10)
        res_json = response.json()

        if res_json.get("result") == 100:
            status = res_json.get("data", {}).get("status", "").lower()
            if status in ["paid", "confirmed", "complete"]:
                return True
    except Exception as e:
        print(f"API Check Error: {e}")

    return False


def handle_oxapay_callback(data):
    """
    Обрабатывает данные от OxaPay и обновляет статус в БД.
    """
    try:
        order_id = data.get("order_id")
        status = data.get("status")
        track_id = data.get("track_id")

        if not order_id:
            return False

        # Обновляем статус заказа в базе
        update_order(order_id, status=status, oxapay_track_id=track_id)
        return True
    except Exception as e:
        print(f"Error handling callback: {e}")
        return False
