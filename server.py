import os
from flask import Flask, request, abort
from bot.bot import bot, give_product
from bot.payment import handle_oxapay_callback
from bot.storage import orders, get_order

app = Flask(__name__)

# Загружаем переменные (они уже загружены в bot/config, но здесь тоже нужны)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_WEBHOOK_SECRET = os.getenv("TG_WEBHOOK_SECRET", "")

def verify_telegram_request(req):
    sig = req.headers.get("X-Telegram-Bot-Api-Secret-Token")
    return sig == TG_WEBHOOK_SECRET

# --- Telegram Webhook ---
@app.route(f"/webhook/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    if not verify_telegram_request(request):
        abort(403)
    
    # pyTelegramBotAPI требует JSON как строку или dict, но process_new_updates принимает список объектов Update
    # Самый надежный способ для этой библиотеки:
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    
    bot.process_new_updates([update])
    return "OK", 200

# --- OxaPay Webhook ---
@app.route("/oxapay/ipn", methods=["POST"])
def oxapay_ipn():
    data = request.get_json(silent=True)
    if not data:
        abort(400)

    # 1. Обрабатываем и сохраняем статус в БД
    success = handle_oxapay_callback(data)
    if not success:
        return "INVALID", 400

    # 2. Проверяем, нужно ли выдать товар
    order_id = data.get("order_id")
    order = get_order(order_id)
    
    # Статус "paid" означает, что деньги зачислены полностью
    if order and order.get("status") == "paid":
        user_id = order.get("user_id")
        
        # Вызываем функцию выдачи из bot.py
        if user_id:
            give_product(user_id, order_id)

    return "OK", 200

@app.route("/")
def index():
    return "Bot Server is Running!", 200

if __name__ == "__main__":
    # Локальный запуск
    import telebot # нужен для import
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)