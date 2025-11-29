# server.py
import os
from flask import Flask, request, abort
from bot.bot import bot  # Твой TeleBot
from bot.payment_oxapay import handle_oxapay_callback
from bot.storage import orders

app = Flask(__name__)

# Проверка Telegram webhook — если используешь webhook для Telegram (не polling)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_WEBHOOK_SECRET = os.getenv("TG_WEBHOOK_SECRET", "")


def verify_telegram_request(req):
    # Telegram присылает заголовок "X-Telegram-Bot-Api-Secret-Token"
    sig = req.headers.get("X-Telegram-Bot-Api-Secret-Token")
    return sig == TG_WEBHOOK_SECRET


@app.route(f"/webhook/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    if not verify_telegram_request(request):
        abort(403)
    update = request.get_json()
    bot.process_new_updates([update])
    return "OK", 200


# Webhook OxaPay IPN
@app.route("/oxapay/ipn", methods=["POST"])
def oxapay_ipn():
    data = request.get_json(silent=True)
    if not data:
        # Некорректный JSON
        abort(400)

    success = handle_oxapay_callback(data)
    if not success:
        # Либо заказ не найден, либо неверный формат
        return "INVALID", 400

    # Если статус — paid (или любой, который ты считаешь завершённым)
    order_id = data.get("order_id")
    order = orders.get(order_id)
    if order and order.get("status") == "paid":
        user_id = order.get("user_id")
        file_path = order.get("file")
        try:
            with open(file_path, "rb") as f:
                bot.send_photo(user_id, f)
            bot.send_message(user_id, "✅ Оплата получена, вот ваш товар!")
        except Exception as e:
            # Логировать ошибку (файл не найден или send failed)
            print("Error sending photo:", e)

    return "OK", 200


@app.route("/")
def index():
    return "Server is up and running", 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
