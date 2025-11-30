# bot/payment.py
import requests
import json
from bot.config import OXAPAY_API_KEY, BASE_URL
from bot.storage import update_order

# Используем классический Merchant API (самый надежный)
OXAPAY_CREATE_URL = "https://api.oxapay.com/merchant/request"

# Используем V1 API только для проверки (так как GET запрос работает везде)
OXAPAY_STATUS_URL = "https://api.oxapay.com/v1/payment/status"  # или /history


def create_invoice(user_id, amount_usd, order_id):
    """
    Создание ссылки через Merchant API.
    """
    # Для Merchant API ключ отправляется внутри JSON как "merchant"
    data = {
        "merchant": OXAPAY_API_KEY,
        "amount": amount_usd,
        "currency": "USD",
        "lifeTime": 60,
        "feePaidByPayer": 1,
        "underPaidCover": 5,
        "toCurrency": "USDT",
        "callbackUrl": f"{BASE_URL}/oxapay/ipn",
        "returnUrl": f"https://t.me/MrGrinchShopZp_Bot",
        "description": f"Order {order_id}",
        "orderId": order_id,
    }

    try:
        response = requests.post(OXAPAY_CREATE_URL, json=data, timeout=15)
        result = response.json()

        # Если API ответило ошибкой 404 "Not Found", значит КЛЮЧ НЕВЕРЕН
        if result.get("result") == 100:
            return result.get("payLink"), result.get("trackId")
        else:
            print(f"⚠️ OxaPay Error: {result}")
            # Если result == 404, это значит API Key неверен!

    except Exception as e:
        print(f"OxaPay Connection Error: {e}")

    return None


def verify_payment_via_api(track_id):
    """
    Проверяет статус заказа.
    """
    if not track_id:
        return False

    # Для проверки используем V1 Payment History, он удобнее
    url = "https://api.oxapay.com/v1/payment"

    headers = {
        "merchant_api_key": OXAPAY_API_KEY,  # Тут ключ в заголовке
        "Content-Type": "application/json",
    }

    params = {"track_id": track_id}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        res_json = response.json()

        if res_json.get("status") == 200 and "data" in res_json:
            payments = res_json["data"].get("list", [])
            if payments:
                status = payments[0].get("status", "").lower()
                if status in ["paid", "confirmed", "complete"]:
                    return True
    except Exception as e:
        print(f"API Check Error: {e}")

    return False


def handle_oxapay_callback(data):
    try:
        # Пытаемся достать ключи в разных форматах (API иногда меняет регистр)
        order_id = data.get("order_id") or data.get("orderId")
        status = data.get("status")
        track_id = data.get("track_id") or data.get("trackId")

        if not order_id:
            return False

        update_order(order_id, status=status, oxapay_track_id=track_id)
        return True
    except Exception as e:
        print(f"Callback Error: {e}")
        return False
