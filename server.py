# server.py
from flask import Flask, request, abort
import telebot
from telebot.types import InputMediaPhoto
import os
import json
import logging

# Импорты из бота
from bot.config import TELEGRAM_TOKEN, OXAPAY_API_KEY, ADMIN_IDS
from bot.bot import bot, start_background_tasks

# Импорты логики
from bot.storage import (
    update_order,
    get_order,
    get_product_details_by_id,
    mark_product_as_sold,
    execute_query,
)
from bot.payment import handle_oxapay_callback, verify_payment_via_api

# Настройка логирования для Flask
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

app = Flask(__name__)


# --- ВЫДАЧА ТОВАРА ---
def give_product(user_id, order_id):
    order = get_order(order_id)

    # 1. Если заказа нет или он уже выдан — выходим
    if not order:
        print(f"Заказ {order_id} не найден.")
        return False

    if order["delivery_status"] == "delivered":
        print(f"Заказ {order_id} уже был выдан ранее.")
        return True  # Возвращаем True, чтобы не считать это ошибкой

    prod = get_product_details_by_id(order["product_id"])
    if not prod:
        return False

    # --- НОВАЯ ЗАЩИТА: Проверяем, не продали ли товар другому ---
    # (На случай гонки запросов)
    try:
        check_sold = execute_query(
            "SELECT is_sold FROM products WHERE product_id = %s",
            (order["product_id"],),
            fetch=True,
        )
        if check_sold and check_sold[0][0] == True:
            print(f"Товар {order['product_id']} уже продан (Double Spend prevention).")
            # Можно уведомить админа, что произошла накладка
            return False
    except:
        pass
    # -----------------------------------------------------------

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

        # Уведомляем админа о продаже (для контроля)
        for adm in ADMIN_IDS:
            try:
                bot.send_message(
                    adm,
                    f"💰 <b>АВТО-ВЫДАЧА!</b>\nЗаказ: {order_id}\nСумма: {prod['price_usd']}$",
                    parse_mode="HTML",
                )
            except:
                pass

        return True

    except telebot.apihelper.ApiTelegramException as e:
        # Если бот в блоке, шлем админу
        print(f"Ошибка отправки юзеру {user_id}: {e}")
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


# Главная страница (Health Check) - ДОЛЖНА БЫТЬ ПЕРЕД app.run
@app.route("/")
def home():
    return "Bot alive and running!", 200


@app.route(f"/webhook/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    if request.headers.get("content-type") == "application/json":
        json_string = request.get_data().decode("UTF-8")
        update = telebot.types.Update.de_json(json_string)
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
    # Можно закомментировать, если спамит
    # try:
    #    debug_message = (
    #        f"🔔 <b>OxaPay Callback!</b>\n" f"<code>{json.dumps(data, indent=2)}</code>"
    #    )
    #    for admin_id in ADMIN_IDS:
    #        bot.send_message(admin_id, debug_message, parse_mode="HTML")
    # except Exception as e:
    #    print(f"Ошибка отправки лога: {e}")
    # ----------------------------------------

    order_id = data.get("order_id") or data.get("orderId")
    track_id = data.get("track_id") or data.get("trackId")
    status = data.get("status")

    # Если статус 'paid', 'confirmed' или 'complete'
    if status in ["paid", "confirmed", "complete"]:

        # 0. Сразу обновляем статус в БД, чтобы юзер видел прогресс
        handle_oxapay_callback(data)

        # 1. Проверяем валидность через API (Защита от фейков)
        try:
            is_valid = verify_payment_via_api(track_id)
        except Exception as e:
            print(f"Ошибка проверки API OxaPay: {e}")
            # Если API упал, лучше вернуть 200 и проверить руками, чем заставлять их слать повторы
            return "API Error", 200

        if not is_valid:
            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(
                        admin_id,
                        f"🚨 <b>ВНИМАНИЕ!</b> Фейковый callback!\nTrack ID: {track_id}",
                        parse_mode="HTML",
                    )
                except:
                    pass
            return "Fake Callback", 400

        # 2. Если всё ок — выдаем товар
        # Получаем user_id из заказа
        order_info = get_order(order_id)
        if order_info:
            give_product(order_info["user_id"], order_id)
        else:
            print(f"Заказ {order_id} не найден при IPN запросе.")

    return "OK", 200


start_background_tasks()

if __name__ == "__main__":
    # Запускаем сервер
    # Важно: use_reloader=False, чтобы не двоились потоки
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), use_reloader=False)
