from flask import Flask, request, abort
from bot.bot import bot
from bot.payment import handle_oxapay_callback
from bot.config import TELEGRAM_TOKEN, TG_WEBHOOK_SECRET

app = Flask(__name__)


# Проверка подписи Telegram webhook
def verify_telegram(req):
    return req.headers.get("X-Telegram-Bot-Api-Secret-Token") == TG_WEBHOOK_SECRET


# --- Telegram webhook ---
@app.route(f"/webhook/{TELEGRAM_TOKEN}", methods=["POST"])
def tg_webhook():
    if not verify_telegram(request):
        abort(403)

    update = request.get_json()
    bot.process_new_updates([update])
    return "OK"


# --- OxaPay IPN ---
@app.route("/oxapay/ipn", methods=["POST"])
def oxapay_webhook():

    data = request.get_json()

    if not data:
        return "No JSON", 400

    ok = handle_oxapay_callback(data)

    if not ok:
        return "Invalid", 400

    return "OK", 200


# --- главная страница ---
@app.route("/")
def home():
    return "Bot is running!"
