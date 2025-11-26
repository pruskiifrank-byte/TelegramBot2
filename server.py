# server.py
from flask import Flask, request
import hmac, hashlib, os, time
from dotenv import load_dotenv
from bot import bot, orders, give_product, process_update

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
MERCHANT_SECRET = os.getenv("MERCHANT_SECRET")  # секрет для подписи Global24
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://your-domain
TG_WEBHOOK_SECRET = os.getenv(
    "TG_WEBHOOK_SECRET", "grinch_311"
)  # допустимый по правилам токен

if not API_TOKEN:
    raise RuntimeError("API_TOKEN not set")

app = Flask(__name__)

# Анти-флуд (серверный) — простая защита от частых одинаковых запросов
user_last_message = {}
FLOOD_SECONDS = float(os.getenv("FLOOD_SECONDS", "0.6"))


def is_flood(chat_id):
    now = time.time()
    last = user_last_message.get(chat_id, 0)
    if now - last < FLOOD_SECONDS:
        return True
    user_last_message[chat_id] = now
    return False


def log_event(order_id, reason, data):
    with open("callbacks.log", "a", encoding="utf-8") as f:
        f.write(f"{time.time()} | {order_id} | {reason} | {data}\n")


def verify_signature(string: str, signature: str) -> bool:
    if not MERCHANT_SECRET:
        return False
    calc = hmac.new(
        MERCHANT_SECRET.encode(), string.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(calc, signature)


@app.route("/", methods=["GET"])
def home():
    return "Bot is running!"


@app.route("/webhook", methods=["POST"])
def webhook():
    # Telegram will include the secret header only if you set secret_token in setWebhook
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    # header may be None if not provided; enforce equality
    if secret != TG_WEBHOOK_SECRET:
        return "Forbidden", 403

    # получаем json и проверяем flood (если есть message)
    raw_json = request.get_json(force=True, silent=True)
    if raw_json and "message" in raw_json:
        try:
            chat_id = raw_json["message"]["chat"]["id"]
            if is_flood(chat_id):
                # просто игнорируем частые сообщения
                return "OK", 200
        except Exception:
            pass

    # передаём raw строкой в bot.process
    raw_text = request.get_data().decode("utf-8")
    process_update(raw_text)
    return "OK", 200


@app.route("/payment_callback", methods=["POST"])
def payment_callback():
    print("CALLBACK RECEIVED:", request.form)
    data = request.form
    order_id = data.get("order_id")
    amount = data.get("amount")
    status = data.get("status")
    signature = data.get("signature")
    if not order_id or not signature:
        return "Invalid", 400
    # проверяем подпись
    string = f"{order_id}{amount}{status}"
    if not verify_signature(string, signature):
        log_event(order_id, "bad_signature", dict(data))
        return "Invalid signature", 400
    # проверяем заказ
    if order_id not in orders:
        log_event(order_id, "order_not_found", dict(data))
        return "Not found", 404
    order = orders[order_id]
    # дубль callback
    if order.get("status") == "paid":
        log_event(order_id, "duplicate_callback", dict(data))
        return "Duplicate", 200
    # проверка суммы
    if str(order.get("amount")) != str(amount):
        log_event(order_id, "wrong_amount", dict(data))
        return "Wrong amount", 400
    chat_id = order.get("user_id")
    product_name = order.get("product")
    if status == "success":
        order["status"] = "paid"
        try:
            bot.send_message(chat_id, "🎉 Оплата подтверждена!")
            give_product(chat_id, product_name)
        except Exception:
            pass
    else:
        try:
            bot.send_message(chat_id, "❌ Оплата не прошла.")
        except Exception:
            pass
    return "OK", 200


@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    if not WEBHOOK_URL:
        return "WEBHOOK_URL not set", 400
    bot.remove_webhook()
    # set webhook with secret_token (must match TG_WEBHOOK_SECRET)
    try:
        ok = bot.set_webhook(
            url=WEBHOOK_URL + "/webhook", secret_token=TG_WEBHOOK_SECRET
        )
    except TypeError:
        # older pytelegrambotapi versions may not support secret_token param
        ok = bot.set_webhook(url=WEBHOOK_URL + "/webhook")
    return f"Webhook set: {ok}", 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
