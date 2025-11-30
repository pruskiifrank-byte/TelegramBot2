# server.py

import os
import json
from flask import Flask, request, abort
import telebot
from bot.config import TELEGRAM_TOKEN
from bot.bot import bot, give_product
from bot.storage import update_order, get_order
import time

# ... (Инициализация app)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не установлен")

app = Flask(__name__)


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


# --- OxaPay Webhook ---
@app.route("/oxapay/ipn", methods=["POST"])
def oxapay_ipn():
    data = request.get_json(silent=True)
    if not data:
        abort(400)

    order_id = data.get("order_id")
    status = data.get("status")  # 'paid', 'canceled' и т.д.

    if not order_id or not status:
        return "MISSING DATA", 400

    # 1. Обновляем статус заказа в БД
    if status == "paid":
        # Используем update_order для установки статуса и времени оплаты
        update_order(
            order_id, status="paid", paid_at=time.strftime("%Y-%m-%d %H:%M:%S")
        )
    elif status == "canceled":
        update_order(order_id, status="canceled")
    # Добавьте другие статусы, если OxaPay их присылает

    # 2. Выдача товара, если оплачено
    if status == "paid":
        order = get_order(order_id)
        if (
            order
            and order.get("user_id")
            and order.get("delivery_status") != "delivered"
        ):
            # Выдача товара, которая теперь отправляет фото тайника
            give_product(order["user_id"], order_id)

    return "OK", 200


# ... (остальной код, если есть)
