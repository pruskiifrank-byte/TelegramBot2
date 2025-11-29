from flask import Flask, request, abort
import traceback
from bot.bot import bot
from bot.payment import handle_oxapay_callback
from bot.config import TELEGRAM_TOKEN, TG_WEBHOOK_SECRET

app = Flask(__name__)


# Проверка подписи Telegram webhook
def verify_telegram(req):
    return req.headers.get("X-Telegram-Bot-Api-Secret-Token") == TG_WEBHOOK_SECRET


# --- Telegram webhook ---
@app.route(f"/webhook/{TG_WEBHOOK_SECRET}", methods=["POST"])
def tg_webhook():
    try:
        if not verify_telegram(request):
            abort(403)

        update = request.get_json()
        if not update:
            abort(400)

        bot.process_new_updates([update])
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
