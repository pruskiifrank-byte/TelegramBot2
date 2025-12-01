# bot/payment.py
import requests
import json
from bot.config import OXAPAY_API_KEY, BASE_URL
from bot.storage import update_order

# Ссылки V1 API
OXAPAY_CREATE_URL = "https://api.oxapay.com/v1/payment/invoice"
OXAPAY_HISTORY_URL = "https://api.oxapay.com/v1/payment"


def create_invoice(user_id, amount_usd, order_id):
    headers = {"merchant_api_key": OXAPAY_API_KEY, "Content-Type": "application/json"}

    data = {
        "amount": amount_usd,
        "currency": "USD",
        "lifetime": 60,
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 5,
        "to_currency": "USDT",
        "auto_withdrawal": False,
        "mixed_payment": True,
        "callback_url": f"{BASE_URL}/oxapay/ipn",
        "return_url": f"https://t.me/MrGrinchShopZp_Bot",
        "description": f"Order {order_id}",
        "order_id": str(order_id),
        "sandbox": False,
    }

    try:
        response = requests.post(
            OXAPAY_CREATE_URL, data=json.dumps(data), headers=headers, timeout=15
        )
        result = response.json()

        # Проверяем успешность
        if (
            result.get("status") == 200
            or result.get("result") == 100
            or result.get("message") == "success"
        ):
            payment_data = result.get("data", {})

            # !!! ГЛАВНОЕ ИСПРАВЛЕНИЕ: Ищем ссылку везде !!!
            pay_url = payment_data.get("payment_url") or payment_data.get("payLink")
            track_id = payment_data.get("track_id") or payment_data.get("trackId")

            # Если ссылки нет, считаем это ошибкой, чтобы не ломать бота
            if pay_url:
                return pay_url, track_id
            else:
                print(f"⚠️ OxaPay Error: URL not found in response: {result}")
                return None
        else:
            print(f"⚠️ OxaPay API Error: {result}")
            return None

    except Exception as e:
        print(f"🚨 Connection Error: {e}")
        return None


def verify_payment_via_api(track_id):
    if not track_id:
        return False
    headers = {"merchant_api_key": OXAPAY_API_KEY, "Content-Type": "application/json"}
    params = {"track_id": track_id}

    try:
        response = requests.get(
            OXAPAY_HISTORY_URL, params=params, headers=headers, timeout=15
        )
        res_json = response.json()

        if res_json.get("status") == 200 and "data" in res_json:
            payments_list = res_json["data"].get("list", [])
            if payments_list:
                status = payments_list[0].get("status", "").lower()
                if status in ["paid", "confirmed", "complete"]:
                    return True
    except Exception as e:
        print(f"API Check Error: {e}")
    return False


def handle_oxapay_callback(data):
    try:
        order_id = data.get("order_id") or data.get("orderId")
        status = data.get("status")
        track_id = data.get("track_id") or data.get("trackId")
        if not order_id:
            return False
        update_order(order_id, status=status, oxapay_track_id=track_id)
        return True
    except:
        return False
