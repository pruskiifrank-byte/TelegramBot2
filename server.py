# server.py
from flask import Flask, request, abort
import telebot
import os
import requests  # НУЖЕН ДЛЯ ПРОВЕРКИ API
from bot.config import TELEGRAM_TOKEN, OXAPAY_API_KEY, ADMIN_IDS
from bot.bot import bot
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
    if not order or order["delivery_status"] == "delivered":
        return False  # Уже выдали

    prod = get_product_details_by_id(order["product_id"])
    if not prod:
        return False
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
        # Отправляем фото по ID (prod['file_path'] хранит file_id)
        bot.send_photo(user_id, prod["file_path"], caption=text, parse_mode="HTML")

        # Обновляем статус заказа
        update_order(order_id, delivery_status="delivered")

        # Помечаем товар как проданный (удаляем с витрины)
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
def oxapay_ipn():
    data = request.get_json()
    order_id = data.get("order_id")
    track_id = data.get("track_id")
    status = data.get("status")

    if status == "paid":
        # 1. Защита от фейков
        if not verify_payment_via_api(track_id):
            return "Fake Callback", 400

        # 2. Обновление статуса
        handle_oxapay_callback(data)

        # 3. Выдача
        give_product(get_order(order_id)["user_id"], order_id)

    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
