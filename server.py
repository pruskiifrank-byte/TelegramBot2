# server.py

from flask import Flask, request, abort
import telebot
import os

# import time # Не используется
import json  # Добавлен для проверки JSON-ответа

# --- Импорты ---
# Если 'give_product' должна быть в другом файле, например, в 'bot.delivery',
# вам нужно будет заменить заглушку на правильный импорт:
# from bot.delivery import give_product

# В целях устранения ошибки:
try:
    from bot.config import TELEGRAM_TOKEN

    # Импортируем только бота, чтобы избежать ошибки
    from bot.bot import bot

    # Предполагаем, что эти модули существуют:
    from bot.payment import handle_oxapay_callback
    from bot.storage import update_order, get_order

except ImportError as e:
    # Заглушки, если вы запускаете код без полной структуры проекта
    print(f"WARNING: Missing import: {e}. Using stub values.")
    TELEGRAM_TOKEN = "ВАШ_ТОКЕН_БОТА"

    class BotStub:
        def process_new_updates(self, updates):
            pass

    bot = BotStub()

    def handle_oxapay_callback(data):
        return True

    def get_order(order_id):
        return {"user_id": 123456789, "delivery_status": "pending"}


# ЗАГЛУШКА ДЛЯ ФУНКЦИИ ВЫДАЧИ ТОВАРА
# !!! ВАЖНО: ЗАМЕНИТЕ ЭТУ ЗАГЛУШКУ НА РЕАЛЬНЫЙ ИМПОРТ ИЛИ РЕАЛЬНУЮ ФУНКЦИЮ !!!
def give_product(user_id, order_id):
    """(ЗАГЛУШКА) Здесь должна быть логика отправки адреса/фото клиенту."""
    print(f"[DELIVERY] Giving product for Order ID: {order_id} to User ID: {user_id}")
    # Здесь нужно вызвать bot.send_message или bot.send_photo
    # и обновить 'delivery_status' в БД на 'delivered'
    # update_order(order_id, delivery_status='delivered')
    return True


# ----------------------------------------------------------------------

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
        # Убедитесь, что 'bot' - это объект TeleBot
        bot.process_new_updates([update])
        return "OK", 200
    else:
        # 403 Forbidden, если запрос пришел не от Telegram
        abort(403)


# --- OxaPay IPN (Callback) ---
@app.route("/oxapay/ipn", methods=["POST"])
def oxapay_ipn():
    """Обработчик входящих уведомлений об оплате от OxaPay."""

    # 1. Проверка Content-Type
    if request.headers.get("content-type") != "application/json":
        abort(403)

    try:
        data = request.get_json()
    except Exception:
        # Не смогли разобрать JSON
        return "Invalid JSON format", 400

    order_id = data.get("order_id")
    status = data.get("status")

    if not order_id or not status:
        return "Missing order_id or status in data", 400

    # 2. Обработка колбэка (обновление статуса в БД)
    # Эта функция должна быть максимально надежной
    if not handle_oxapay_callback(data):
        # Если заказ не найден или обработка с ошибкой (например, подпись неверна)
        # OxaPay ожидает 200 OK, но лучше дать 400/500, если это критическая ошибка
        return "Order verification or storage error", 400

    # 3. Проверка статуса и выдача товара
    if status == "paid":
        order_data = get_order(order_id)

        if not order_data:
            return "Order data not found after callback processing", 400

        user_id = order_data.get("user_id")

        # Выдаем товар, только если статус доставки еще pending (предотвращаем дублирование выдачи)
        if order_data.get("delivery_status") == "pending":
            give_product(user_id, order_id)

        # Возвращаем 200 OK, чтобы OxaPay не повторял отправку
        return "OK", 200

    # Если статус не "paid" (например, "cancelled" или "pending"), просто принимаем и завершаем.
    return "OK", 200


if __name__ == "__main__":
    # Локальный запуск
    # PORT для Render обычно задается через ENV, 5000 - дефолтный
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
