# test_key.py
import requests

# --- ВСТАВЬТЕ СЮДА ВАШ КЛЮЧ ---
MY_KEY = "CQGVUT-QRJJOX-YQQHSJ-C7AGTR"
# ------------------------------

url = "https://api.oxapay.com/merchant/request"

data = {
    "merchant": MY_KEY,
    "amount": 1,
    "currency": "USD",
    "lifeTime": 30,
    "feePaidByPayer": 0,
    "underPaidCover": 0,
    "callbackUrl": "https://google.com",
    "description": "Test",
    "orderId": "TEST-123",
}

print(f"📡 Проверяем ключ: {MY_KEY} ...")

try:
    response = requests.post(url, json=data)
    print(f"Ответ сервера: {response.status_code}")
    print(f"Тело ответа: {response.text}")

    json_resp = response.json()
    if json_resp.get("result") == 100:
        print("\n✅ УСПЕХ! Ключ рабочий. Ссылка:", json_resp.get("payLink"))
    else:
        print("\n❌ ОШИБКА! Ключ неверный или не того типа.")
except Exception as e:
    print(f"Ошибка соединения: {e}")
