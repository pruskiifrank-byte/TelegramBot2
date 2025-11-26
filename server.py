import os
from flask import Flask, request, abort
from dotenv import load_dotenv
from telebot import TeleBot
import hashlib
import hmac
import json

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
TG_WEBHOOK_SECRET = os.getenv("TG_WEBHOOK_SECRET")
MERCHANT_SECRET = os.getenv("SECRET_KEY")  # !!! Global24 SECRET KEY

bot = TeleBot(API_TOKEN, parse_mode="HTML")

app = Flask(__name__)


# --------------------------
# Telegram Webhook
# --------------------------
@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != TG_WEBHOOK_SECRET:
        abort(403)

    json_update = request.json
    bot.process_new_updates([telebot.types.Update.de_json(json_update)])
    return "ok", 200


# --------------------------
# Global24 CALLBACK
# --------------------------
@app.route("/payment_callback", methods=["POST"])
def payment_callback():
    data = request.json
    if not data:
        abort(400)

    signature = request.headers.get("X-Signature")
    if not signature:
        abort(403)

    # Проверка подписи
    body_bytes = request.data
    expected_signature = hmac.new(
        MERCHANT_SECRET.encode(), body_bytes, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        abort(403)

    print("CALLBACK RECEIVED:", data)

    payment_status = data.get("payment_status")
    order_id = data.get("order_id")

    if payment_status == "success":
        bot.send_message(chat_id=order_id, text="🎉 Платёж успешно получен!\nСпасибо ❤️")

    return "ok", 200


# --------------------------
# Установка Webhook
# --------------------------
@app.route("/set_webhook")
def set_hook():
    bot.delete_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook", secret_token=TG_WEBHOOK_SECRET)
    return "Webhook installed!"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
