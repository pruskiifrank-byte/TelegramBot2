# server.py

from flask import Flask, request, abort
import telebot
import os

# --- Импорты ---
from bot.config import TELEGRAM_TOKEN
from bot.bot import bot
from bot.payment import handle_oxapay_callback

# !!! Вот здесь был пропущен импорт, добавляем его явно:
from bot.storage import update_order, get_order, get_product_details_by_id


# ----------------------------------------------------------------------
# ФУНКЦИЯ ВЫДАЧИ ТОВАРА
# ----------------------------------------------------------------------
def give_product(user_id, order_id):
    """
    Отправляет адрес/фото клиенту после успешной оплаты.
    """
    order_data = get_order(order_id)
    if not order_data:
        print(f"[DELIVERY] ERROR: Order ID {order_id} not found for delivery.")
        return False

    # Теперь функция get_product_details_by_id доступна благодаря импорту выше
    product_data = get_product_details_by_id(order_data["product_id"])

    if not product_data:
        print(f"[DELIVERY] ERROR: Product ID {order_data['product_id']} not found.")
        update_order(order_id, delivery_status="error")
        return False

    delivery_text = product_data.get(
        "delivery_text", "Данные для получения отсутствуют."
    )
    product_name = product_data.get("product_name", "Товар")

    caption_text = (
        f"✅ **Оплата заказа №{order_id} подтверждена!**\n\n"
        f"**Товар:** {product_name}\n\n"
        f"**ИНСТРУКЦИЯ КЛАДА:**\n{delivery_text}"
    )

    try:
        bot.send_message(user_id, caption_text, parse_mode="Markdown")
        update_order(order_id, delivery_status="delivered")
        print(
            f"[DELIVERY] Successfully delivered Order ID: {order_id} to User ID: {user_id}"
        )
        return True
    except Exception as e:
        print(f"[DELIVERY] FATAL ERROR during delivery for Order ID {order_id}: {e}")
        update_order(order_id, delivery_status="failed")
        return False


# ----------------------------------------------------------------------
app = Flask(__name__)


@app.route("/")
def home():
    return "Bot service is running.", 200


@app.route(f"/webhook/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    if request.headers.get("content-type") == "application/json":
        json_str = request.get_data().decode("UTF-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return "OK", 200
    else:
        abort(403)


@app.route("/oxapay/ipn", methods=["POST"])
def oxapay_ipn():
    if request.headers.get("content-type") != "application/json":
        abort(403)

    try:
        data = request.get_json()
    except Exception:
        return "Invalid JSON format", 400

    order_id = data.get("order_id")
    status = data.get("status")

    if not order_id or not status:
        return "Missing order_id or status in data", 400

    if not handle_oxapay_callback(data):
        return "Order verification or storage error", 400

    if status == "paid":
        order_data = get_order(order_id)
        if not order_data:
            return "Order data not found after callback processing", 400

        user_id = order_data.get("user_id")

        if order_data.get("delivery_status") == "pending":
            give_product(user_id, order_id)

        return "OK", 200

    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
