# bot/payment.py
import requests
import json
from bot.config import OXAPAY_API_KEY, BASE_URL

# Нам нужно обновлять базу при колбэке, поэтому импортируем update_order
from bot.storage import update_order

# Ссылка для СОЗДАНИЯ счета (стандартный Merchant API)
OXAPAY_CREATE_URL = "https://api.oxapay.com/merchant/request"

# Ссылка для ПРОВЕРКИ счета (из вашей документации)
OXAPAY_HISTORY_URL = "https://api.oxapay.com/v1/payment"


def create_invoice(user_id, amount_usd, order_id):
    """
    Создание ссылки на оплату через Merchant API.
    """
    # Для создания платежа данные отправляются в JSON (POST)
    data = {
        "merchant": OXAPAY_API_KEY,  # В этом эндпоинте ключ передается в теле как "merchant"
        "amount": amount_usd,
        "currency": "USD",
        "lifeTime": 60,  # Обратите внимание: CamelCase (lifeTime)
        "feePaidByPayer": 1,  # CamelCase
        "underPaidCover": 5,  # CamelCase
        "toCurrency": "USDT",  # CamelCase
        "callbackUrl": f"{BASE_URL}/oxapay/ipn",
        "returnUrl": f"https://t.me/MrGrinchShopZp_Bot",  # Ссылка возврата в бота
        "description": f"Order {order_id}",
        "orderId": order_id,
    }

    try:
        response = requests.post(OXAPAY_CREATE_URL, json=data, timeout=15)
        result = response.json()

        # В Merchant API успешный код "result": 100
        if result.get("result") == 100:
            return result.get("payLink"), result.get("trackId")
        else:
            print(f"OxaPay Create Error (API response): {result}")

    except Exception as e:
        print(f"OxaPay Create Error (Exception): {e}")

    return None


def verify_payment_via_api(track_id):
    """
    Проверяет статус заказа, используя метод Payment History (из вашей документации).
    """
    if not track_id:
        return False

    # Согласно вашей документации:
    # Метод: GET
    # Параметры: merchant_api_key, track_id

    headers = {"merchant_api_key": OXAPAY_API_KEY, "Content-Type": "application/json"}

    params = {"track_id": track_id}

    try:
        # Делаем GET запрос, как в документации
        response = requests.get(
            OXAPAY_HISTORY_URL, params=params, headers=headers, timeout=15
        )
        res_json = response.json()

        # Анализируем ответ
        # Структура: {"status": 200, "data": {"list": [...]}}
        if res_json.get("status") == 200 and "data" in res_json:
            payments_list = res_json["data"].get("list", [])

            if payments_list:
                # Берем первый найденный платеж (так как мы искали по уникальному track_id)
                payment = payments_list[0]
                status = payment.get("status", "").lower()

                # Проверяем статус
                # Возможные значения из доков: Paying, Paid (и другие)
                if status in ["paid", "confirmed", "complete"]:
                    return True
                elif status == "paying":
                    print(f"Payment {track_id} is still in Paying status.")
            else:
                print(f"Payment {track_id} not found in history.")

    except Exception as e:
        print(f"API Check Error: {e}")

    return False


def handle_oxapay_callback(data):
    """
    Обрабатывает данные от OxaPay (Webhook) и обновляет статус в БД.
    """
    try:
        # В вебхуке ключи могут приходить немного по-другому, проверяем
        order_id = data.get("order_id") or data.get("orderId")
        status = data.get("status")
        track_id = data.get("track_id") or data.get("trackId")

        if not order_id:
            return False

        # Обновляем статус заказа в базе
        update_order(order_id, status=status, oxapay_track_id=track_id)
        return True
    except Exception as e:
        print(f"Error handling callback: {e}")
        return False
