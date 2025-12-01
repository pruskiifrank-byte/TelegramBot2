# server.py
from flask import Flask, request, abort
import telebot
import os
import json
from bot.config import TELEGRAM_TOKEN, OXAPAY_API_KEY, ADMIN_IDS
from bot.bot import bot

# ВАЖНО: Импортируем mark_product_as_sold
from bot.storage import (
    update_order,
    get_order,
    get_product_details_by_id,
    mark_product_as_sold,
)
from bot.payment import handle_oxapay_callback, verify_payment_via_api

app = Flask(__name__)


# --- ВЫДАЧА ТОВАРА ---
def give_product(user_id, order_id):
    order = get_order(order_id)
    # Если заказа нет или он уже выдан — ничего не делаем
    if not order or order["delivery_status"] == "delivered":
        return False

    prod = get_product_details_by_id(order["product_id"])
    if not prod:
        return False

    # Текст с вашими ссылками
    text = (
        f"✅ <b>Оплата прошла успешно!</b>\n"
        f"📦 Товар: <b>{prod['product_name']}</b>\n\n"
        f"📍 <b>ВАШ КЛАД:</b>\n{prod['delivery_text']}\n\n"
        f"—————————————\n"
        f"Спасибо за покупку \n"
        f"быстрого подъёма и мягкого покура🥰\n\n"
        f"Отзывы довольных клиентов⤵️\n"
        f"https://t.me/+NW9rf1wPSl5lZmM6\n\n"
        f"Резервы в случае блокировки ⤵️⤵️⤵️\n"
        f"@scooby_doorezerv1\n"
        f"@scooby_doorezerv2\n"
        f"@scoobbyy_doo\n\n"
        f"Это все актуальные линки \n"
        f"Остальное скам-мошенники\n"
        f"—————————————"
    )

    try:
        # Отправляем фото
        bot.send_photo(user_id, prod["file_path"], caption=text, parse_mode="HTML")

        # Обновляем статус заказа
        update_order(order_id, delivery_status="delivered")

        # !!! ВАЖНО: УБИРАЕМ ТОВАР С ВИТРИНЫ !!!
        mark_product_as_sold(order["product_id"])

        return True
    except telebot.apihelper.ApiTelegramException as e:
        # Если бот в блоке, шлем админу
        for adm in ADMIN_IDS:
            try:
                bot.send_message(
                    adm,
                    f"🆘 АВАРИЯ! Клиент {user_id} оплатил, но заблокировал бота!\nOrder: {order_id}",
                )
            except:
                pass
        return False
    except Exception as e:
        print(f"Delivery Error: {e}")
        return False


# --- ROUTES ---
@app.route(f"/webhook/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    if request.headers.get("content-type") == "application/json":
        update = telebot.types.Update.de_json(request.get_data().decode("UTF-8"))
        bot.process_new_updates([update])
        return "OK", 200
    abort(403)


@app.route("/oxapay/ipn", methods=["POST"])
# server.py (часть кода)


@app.route("/oxapay/ipn", methods=["POST"])
def oxapay_ipn():
    try:
        data = request.get_json()
    except:
        return "Invalid JSON", 400

    # --- 🔥 НОВАЯ ЧАСТЬ: ОТПРАВКА ЛОГА В ТЕЛЕГРАМ ---
    # Это отправит вам сырые данные от платежки, чтобы вы видели, что происходит
    try:
        # Формируем красивое сообщение с данными
        debug_message = (
            f"🔔 <b>OxaPay Callback!</b>\n" f"<code>{json.dumps(data, indent=2)}</code>"
        )

        # Отправляем всем админам
        for admin_id in ADMIN_IDS:
            bot.send_message(admin_id, debug_message, parse_mode="HTML")

    except Exception as e:
        print(f"Ошибка отправки лога в Telegram: {e}")
    # --------------------------------------------------

    order_id = data.get("order_id")
    track_id = data.get("track_id")
    status = data.get("status")

    # Если статус 'paid', 'confirmed' или 'complete'
    if status in ["paid", "confirmed", "complete"]:
        # 1. Защита от фейков
        if not verify_payment_via_api(track_id):
            # Тоже сообщим админу о попытке взлома
            for admin_id in ADMIN_IDS:
                bot.send_message(
                    admin_id,
                    f"🚨 <b>ВНИМАНИЕ!</b> Фейковый callback!\nTrack ID: {track_id}",
                    parse_mode="HTML",
                )
            return "Fake Callback", 400

        # 2. Выдача
        give_product(get_order(order_id)["user_id"], order_id)

    return "OK", 200
