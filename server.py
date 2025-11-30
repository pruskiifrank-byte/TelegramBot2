# server.py

from flask import Flask, request, abort
import telebot
import os
import time

# Импорт из вашей внутренней логики
from bot.config import TELEGRAM_TOKEN
from bot.bot import bot, give_product
from bot.payment import handle_oxapay_callback
from bot.storage import update_order, get_order

app = Flask(__name__)


@app.route("/")
def home():
    """Простое сообщение для проверки живости сервиса."""
    return "Bot service is running.", 200


# --- Telegram Webhook ---
@app.route(f"/webhook/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    if request.headers.get("content-type") == "application/json":
        json_str = request.get_data().decode("UTF-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return "OK", 200
    else:
        abort(403)


# --- OxaPay IPN (Callback) ---
@app.route("/oxapay/ipn", methods=["POST"])
def oxapay_ipn():
    """Обработчик входящих уведомлений об оплате от OxaPay."""
    if request.headers.get("content-type") == "application/json":
        data = request.get_json()
        order_id = data.get("order_id")
        status = data.get("status")

        # 1. Обработка колбэка (обновление статуса в БД)
        if not handle_oxapay_callback(data):
            # Если заказ не найден или обработка с ошибкой
            return "Order not found or processing error", 400

        # 2. Проверка статуса и выдача товара
        if status == "paid" and order_id:
            order_data = get_order(order_id)
            user_id = order_data.get("user_id")

            # Выдаем товар, только если статус доставки еще pending (предотвращаем дублирование выдачи)
            if order_data.get("delivery_status") == "pending":
                give_product(user_id, order_id)

            return "OK", 200

        return "OK", 200
    else:
        abort(403)


if __name__ == "__main__":
    # Если запускаете локально для тестирования
    # BASE_URL должен быть вашим ngrok или другим туннелем
    # bot.remove_webhook()
    # time.sleep(0.1)
    # bot.set_webhook(url=f"{BASE_URL}/webhook/{TELEGRAM_TOKEN}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
