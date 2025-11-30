# bot/payment.py
import requests
from bot.config import OXAPAY_API_KEY, BASE_URL

OXAPAY_INVOICE_URL = "https://api.oxapay.com/v1/payment/invoice"
OXAPAY_STATUS_URL = "https://api.oxapay.com/v1/payment/status"


def create_invoice(user_id, amount_usd, order_id):
    """Создание ссылки на оплату."""
    headers = {"merchant_api_key": OXAPAY_API_KEY, "Content-Type": "application/json"}
    data = {
        "amount": amount_usd,
        "currency": "USD",
        "lifetime": 60,  # Время жизни инвойса в минутах
        "fee_paid_by_payer": 1,
        "under_paid_coverage": 5,  # Допускаем небольшую недоплату
        "to_currency": "USDT",  # Конвертируем все в USDT
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

        # Проверяем успешный ответ и статус
        if res_json.get("result") == 100:
            status = res_json.get("data", {}).get("status", "").lower()
            if status in ["paid", "confirmed", "complete"]:
                return True
    except Exception as e:
        print(f"API Check Error: {e}")

    return False
