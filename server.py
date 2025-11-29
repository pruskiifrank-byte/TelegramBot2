from flask import Flask, request, abort
import traceback
from bot.bot import bot
from bot.payment import handle_oxapay_callback
from bot.config import TG_WEBHOOK_SECRET  # секрет для URL, не заголовок

app = Flask(__name__)


# --- Telegram webhook ---
@app.route(f"/webhook/{TG_WEBHOOK_SECRET}", methods=["POST"])
def tg_webhook():
    try:
        update_json = request.get_json()
        if not update_json:
            abort(400)

        # Преобразуем dict в объект Update
        from telebot.types import Update

        update_obj = Update.de_json(update_json)

        # Обработка апдейта
        bot.process_new_updates([update_obj])
        return "OK", 200

    except Exception as e:
        print("❌ Telegram webhook error:", e)
        traceback.print_exc()
        return "Internal Server Error", 500


# --- OxaPay IPN ---
@app.route("/oxapay/ipn", methods=["POST"])
def oxapay_webhook():
    try:
        data = request.get_json()
        if not data:
            return "No JSON", 400

        ok = handle_oxapay_callback(data)
        if not ok:
            return "Invalid", 400

        return "OK", 200

    except Exception as e:
        print("❌ OxaPay webhook error:", e)
        traceback.print_exc()
        return "Internal Server Error", 500


# --- главная страница ---
@app.route("/")
def home():
    return "Bot is running!"
