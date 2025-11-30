# bot/payment.py
import requests
import json
from bot.config import OXAPAY_API_KEY, BASE_URL

# Импортируем обновление статуса для колбэка
from bot.storage import update_order

# Ссылка из вашего примера (V1 Invoice)
OXAPAY_CREATE_URL = "https://api.oxapay.com/v1/payment/invoice"

# Ссылка для проверки статуса (V1)
OXAPAY_HISTORY_URL = "https://api.oxapay.com/v1/payment"


def create_invoice(user_id, amount_usd, order_id):
    """
    Создание ссылки на оплату через OxaPay V1 (по вашему примеру).
    """

    # 1. Заголовки (Ключ передаем здесь!)
    headers = {"merchant_api_key": OXAPAY_API_KEY, "Content-Type": "application/json"}

    # 2. Данные (Обратите внимание на названия полей snake_case)
    data = {
        "amount": amount_usd,
        "currency": "USD",
        "lifetime": 60,  # Время жизни в минутах
        "fee_paid_by_payer": 1,  # Комиссию платит покупатель
        "under_paid_coverage": 5,  # Допускаем недоплату 5%
        "to_currency": "USDT",  # Конвертация в USDT
        "auto_withdrawal": False,
        "mixed_payment": True,  # Можно платить частями
        # Важные ссылки
        "callback_url": f"{BASE_URL}/oxapay/ipn",  # Куда стучится сервер
        "return_url": "https://t.me/MrGrinchShopZp_Bot",  # Куда вернуть юзера
        "description": f"Order {order_id}",
        "order_id": str(order_id),
        "sandbox": False,  # Выключаем песочницу для реальных денег
    }

    try:
        # Отправляем POST запрос
        response = requests.post(
            OXAPAY_CREATE_URL, data=json.dumps(data), headers=headers, timeout=15
        )
        result = response.json()

        # В V1 API успешный код "result": 100
        # Также проверяем message на "success"
        if result.get("result") == 100 or result.get("message") == "success":
            # OxaPay V1 возвращает payLink и trackId внутри 'data'
            payment_data = result.get("data", {})
            return payment_data.get("payLink"), payment_data.get("trackId")
        else:
            print(f"⚠️ OxaPay Error: {result}")

    except Exception as e:
        print(f"🚨 Connection Error: {e}")

    return None


def verify_payment_via_api(track_id):
    """
    Проверяет статус заказа (V1 Payment History).
    """
    if not track_id:
        return False

    headers = {"merchant_api_key": OXAPAY_API_KEY, "Content-Type": "application/json"}

    # Параметры для GET запроса
    params = {"track_id": track_id}

    try:
        response = requests.get(
            OXAPAY_HISTORY_URL, params=params, headers=headers, timeout=15
        )
        res_json = response.json()

        # Проверяем статус 200 и наличие данных
        if res_json.get("status") == 200 and "data" in res_json:
            payments_list = res_json["data"].get("list", [])

            if payments_list:
                payment = payments_list[0]
                status = payment.get("status", "").lower()

                # Статусы успеха
                if status in ["paid", "confirmed", "complete"]:
                    return True
                elif status == "paying":
                    print(f"Payment {track_id} is still in Paying status.")
            else:
                print(f"Payment {track_id} not found.")

    except Exception as e:
        print(f"API Check Error: {e}")

    return False


def handle_oxapay_callback(data):
    """
    Обрабатывает вебхук от OxaPay.
    """
    try:
        # Пытаемся достать данные. В V1 ключи обычно snake_case
        order_id = data.get("order_id")
        status = data.get("status")
        track_id = data.get("track_id")

        if not order_id:
            return False

        update_order(order_id, status=status, oxapay_track_id=track_id)
        return True
    except Exception as e:
        print(f"Error handling callback: {e}")
        return False
