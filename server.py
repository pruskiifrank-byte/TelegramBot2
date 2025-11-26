# server.py
from flask import Flask, request
import hmac, hashlib, os, time
from dotenv import load_dotenv
from bot import bot, orders, give_product, process_update

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
MERCHANT_SECRET = os.getenv("SECRET_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
TG_WEBHOOK_SECRET = os.getenv("TG_WEBHOOK_SECRET", "SUPERSECRET123")

if not API_TOKEN:
    raise RuntimeError("API_TOKEN not set")

app = Flask(__name__)

# ————— АНТИ-ФЛУД для Telegram —————
user_last_message = {}
FLOOD_SECONDS = 1.0  # минимальный интервал между запросами


def is_flood(chat_id):
    now = time.time()
    last = user_last_message.get(chat_id, 0)
    if now - last < FLOOD_SECONDS:
        return True
    user_last_message[chat_id] = now
    return False


# ————— ЛОГИРОВАНИЕ ПОВТОРНЫХ CALLBACK —————


def log_event(order_id, reason, data):
    with open("callbacks.log", "a", encoding="utf-8") as f:
        f.write(f"{order_id} | {reason} | {data}\n")


# ————— Проверка подписи —————


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


# ————————————————
# 🔥 WEBHOOK TELEGRAM
# ————————————————
@app.route("/webhook", methods=["POST"])
def webhook():
    # ——— Проверка секретного токена Telegram ———
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != TG_WEBHOOK_SECRET:
        return "Forbidden", 403

    # ——— Анти-флуд на стороне сервера ———
    raw = request.get_json(force=True, silent=True)
    if raw and "message" in raw:
        chat_id = raw["message"]["chat"]["id"]
        if is_flood(chat_id):
            return "OK", 200

    # ——— Передача обновления в бота ———
    raw_text = request.get_data().decode("utf-8")
    process_update(raw_text)
    return "OK", 200


# ————————————————
# 🔥 CALLBAСK ОТ GLOBAL24
# ————————————————
@app.route("/payment_callback", methods=["POST"])
def payment_callback():
    data = request.form

    order_id = data.get("order_id")
    amount = data.get("amount")
    status = data.get("status")
    signature = data.get("signature")

    if not order_id or not signature:
        return "Invalid", 400

    # ——— Проверка подписи Global24 ———
    string = f"{order_id}{amount}{status}"

    if not verify_signature(string, signature):
        log_event(order_id, "bad_signature", dict(data))
        return "Invalid signature", 400

    # ——— Проверка, что заказ существует ———
    if order_id not in orders:
        log_event(order_id, "order_not_found", dict(data))
        return "Not found", 404

    order = orders[order_id]

    # ——— Заказ уже оплачен ———
    if order["status"] == "paid":
        log_event(order_id, "duplicate_callback", dict(data))
        return "Duplicate", 200

    # ——— Проверка суммы ———
    if str(order["amount"]) != str(amount):
        log_event(order_id, "wrong_amount", dict(data))
        return "Wrong amount", 400

    chat_id = order["user_id"]
    product_name = order["product"]

    # ——— Успешная оплата ———
    if status == "success":
        order["status"] = "paid"

        bot.send_message(chat_id, "🎉 Оплата подтверждена!")
        give_product(chat_id, product_name)

    else:
        bot.send_message(chat_id, "❌ Оплата не прошла.")

    return "OK", 200


# ————————————————
@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    bot.remove_webhook()
    ok = bot.set_webhook(url=WEBHOOK_URL + "/webhook", secret_token=TG_WEBHOOK_SECRET)
    return f"Webhook set: {ok}", 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
