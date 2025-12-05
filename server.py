# server.py
from flask import Flask, request, abort
import telebot
from telebot.types import InputMediaPhoto
import os
import json
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
        # --- ЛОГИКА ОТПРАВКИ (ФОТО ИЛИ АЛЬБОМ) ---
        photos = prod["file_path"].split(",")

        if len(photos) == 1:
            # Одно фото
            bot.send_photo(user_id, photos[0], caption=text, parse_mode="HTML")
        else:
            # Альбом (Media Group)
            media = []
            for i, file_id in enumerate(photos):
                if i == 0:
                    # Подпись только к первому фото
                    media.append(
                        InputMediaPhoto(file_id, caption=text, parse_mode="HTML")
                    )
                else:
                    media.append(InputMediaPhoto(file_id))
            bot.send_media_group(user_id, media)
        # -----------------------------------------

        # Обновляем статус заказа
        update_order(order_id, delivery_status="delivered")

        # Убираем товар с витрины
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
    try:
        data = request.get_json()
    except:
        return "Invalid JSON", 400

    # --- ОТПРАВКА ЛОГА В ТЕЛЕГРАМ (DEBUG) ---
    try:
        debug_message = (
            f"🔔 <b>OxaPay Callback!</b>\n" f"<code>{json.dumps(data, indent=2)}</code>"
        )
        for admin_id in ADMIN_IDS:
            bot.send_message(admin_id, debug_message, parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка отправки лога в Telegram: {e}")
    # ----------------------------------------

    order_id = data.get("order_id") or data.get("orderId")
    track_id = data.get("track_id") or data.get("trackId")
    status = data.get("status")

    # Если статус 'paid', 'confirmed' или 'complete'
    if status in ["paid", "confirmed", "complete"]:
        # 1. Защита от фейков
        if not verify_payment_via_api(track_id):
            for admin_id in ADMIN_IDS:
                bot.send_message(
                    admin_id,
                    f"🚨 <b>ВНИМАНИЕ!</b> Фейковый callback!\nTrack ID: {track_id}",
                    parse_mode="HTML",
                )
            return "Fake Callback", 400

        # 2. Обновление статуса в БД
        handle_oxapay_callback(data)

        # 3. Выдача товара
        give_product(get_order(order_id)["user_id"], order_id)

    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))


@app.route("/")
def home():
    return "Bot alive", 200
