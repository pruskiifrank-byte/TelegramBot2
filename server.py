# server.py
from flask import Flask, request, abort
import telebot
from telebot.types import InputMediaPhoto
import os
import json
import logging
import time

# Импорты из бота
from bot.config import TELEGRAM_TOKEN, OXAPAY_API_KEY, ADMIN_IDS, BASE_URL
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

# Настройка логов
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

app = Flask(__name__)


# --- ВЫДАЧА ТОВАРА (Логика без изменений) ---
def give_product(user_id, order_id):
    order = get_order(order_id)
    if not order:
        return False
    if order["delivery_status"] == "delivered":
        return True

    prod = get_product_details_by_id(order["product_id"])
    if not prod:
        return False

    try:
        check_sold = execute_query(
            "SELECT is_sold FROM products WHERE product_id = %s",
            (order["product_id"],),
            fetch=True,
        )
        if check_sold and check_sold[0][0] == True:
            return False
    except:
        pass

    text = (
        f"✅ <b>Оплата прошла успешно!</b>\n"
        f"📦 Товар: <b>{prod['product_name']}</b>\n\n"
        f"📍 <b>ВАШ КЛАД:</b>\n{prod['delivery_text']}\n\n"
        f"—————————————\n"
        f"Спасибо за покупку!\n"
    )

    try:
        photos = prod["file_path"].split(",")
        if len(photos) == 1:
            bot.send_photo(user_id, photos[0], caption=text, parse_mode="HTML")
        else:
            media = []
            for i, file_id in enumerate(photos):
                if i == 0:
                    media.append(
                        InputMediaPhoto(file_id, caption=text, parse_mode="HTML")
                    )
                else:
                    media.append(InputMediaPhoto(file_id))
            bot.send_media_group(user_id, media)

        update_order(order_id, delivery_status="delivered")
        mark_product_as_sold(order["product_id"])

        for adm in ADMIN_IDS:
            try:
                bot.send_message(
                    adm, f"💰 <b>ПРОДАЖА!</b> {prod['price_usd']}$", parse_mode="HTML"
                )
            except:
                pass
        return True

    except Exception as e:
        print(f"Delivery Error: {e}")
        return False


# --- ВЕБХУК ДЛЯ ТЕЛЕГРАМА ---


@app.route(f"/webhook/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    """
    Сюда Телеграм присылает обновления.
    """
    if request.headers.get("content-type") == "application/json":
        json_string = request.get_data().decode("UTF-8")
        update = telebot.types.Update.de_json(json_string)

        # Обрабатываем сообщение
        try:
            bot.process_new_updates([update])
        except Exception as e:
            print(f"Ошибка обработки апдейта: {e}")

        return "OK", 200
    abort(403)


# --- ОПЛАТА OXAPAY ---


@app.route("/oxapay/ipn", methods=["POST"])
def oxapay_ipn():
    try:
        data = request.get_json()
    except:
        return "Invalid JSON", 400

    order_id = data.get("order_id") or data.get("orderId")
    track_id = data.get("track_id") or data.get("trackId")
    status = data.get("status")

    if status in ["paid", "confirmed", "complete"]:
        handle_oxapay_callback(data)
        try:
            if not verify_payment_via_api(track_id):
                return "Fake Callback", 400
        except:
            pass

        order_info = get_order(order_id)
        if order_info:
            give_product(order_info["user_id"], order_id)

    return "OK", 200


@app.route("/")
def home():
    return "Webhook Bot is Running!", 200


# --- НАСТРОЙКА ПРИ СТАРТЕ ---


def setup_webhook():
    """Устанавливаем вебхук при запуске сервера"""
    # Удаляем старый, чтобы не было конфликтов
    bot.remove_webhook()
    time.sleep(1)

    # Ставим новый
    # BASE_URL должен быть без слеша в конце, например: https://myapp.onrender.com
    url = f"{BASE_URL}/webhook/{TELEGRAM_TOKEN}"
    print(f"🔗 Ставлю вебхук на: {url}")

    status = bot.set_webhook(url=url)
    if status:
        print("✅ Вебхук успешно установлен!")
    else:
        print("❌ Ошибка установки вебхука!")


# Запускаем фоновые задачи (бэкапы, очистка)
start_background_tasks()

# Устанавливаем вебхук (делаем это один раз при старте)
# Важно: На Render это сработает, когда Gunicorn загрузит файл
try:
    setup_webhook()
except Exception as e:
    print(f"⚠️ Не удалось поставить вебхук при старте: {e}")


if __name__ == "__main__":
    # Локальный запуск (для тестов)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
