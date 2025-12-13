# server.py
from flask import Flask, request, abort
from threading import Thread
import time
import telebot
from telebot.types import InputMediaPhoto
import os
import json
import logging

# Импорты из бота
from bot.config import TELEGRAM_TOKEN, OXAPAY_API_KEY, ADMIN_IDS

# Импортируем бота, но НЕ запускаем polling здесь (он запустится в потоке ниже)
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

# Настройка логирования (глушим лишний шум от сервера)
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

app = Flask(__name__)


# --- ВЫДАЧА ТОВАРА (ВАША ФУНКЦИЯ) ---
def give_product(user_id, order_id):
    order = get_order(order_id)
    if not order:
        print(f"Заказ {order_id} не найден.")
        return False

    if order["delivery_status"] == "delivered":
        print(f"Заказ {order_id} уже был выдан ранее.")
        return True

    prod = get_product_details_by_id(order["product_id"])
    if not prod:
        return False

    # Защита от повторной продажи
    try:
        check_sold = execute_query(
            "SELECT is_sold FROM products WHERE product_id = %s",
            (order["product_id"],),
            fetch=True,
        )
        if check_sold and check_sold[0][0] == True:
            print(f"Товар {order['product_id']} уже продан.")
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

        # Уведомление админам
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


# --- ROUTES (МАРШРУТЫ) ---


@app.route("/")
def home():
    return "Bot is running!", 200


@app.route(f"/webhook/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    # Этот вебхук нужен ТОЛЬКО если вы НЕ используете polling.
    # Но так как мы делаем polling, этот маршрут оставим "на всякий случай",
    # но он не будет использоваться.
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

    order_id = data.get("order_id") or data.get("orderId")
    track_id = data.get("track_id") or data.get("trackId")
    status = data.get("status")

    if status in ["paid", "confirmed", "complete"]:
        handle_oxapay_callback(data)

        # Проверка API (если выключена - закомментируйте блок)
        try:
            if not verify_payment_via_api(track_id):
                return "Fake Callback", 400
        except:
            pass  # Если API OxaPay лагает, верим колбэку

        order_info = get_order(order_id)
        if order_info:
            give_product(order_info["user_id"], order_id)

    return "OK", 200


# --- ЗАПУСК БОТА В ФОНЕ ---


def run_bot_polling():
    """Функция, которая запускает бота и держит его живым"""
    print("🚀 Запуск Polling в отдельном потоке...")
    try:
        # Сначала запускаем задачи очистки и бэкапа
        start_background_tasks()
        # Запускаем бесконечный цикл бота
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        print(f"❌ Бот упал с ошибкой: {e}")


# Мы создаем и запускаем поток ПРИ ИМПОРТЕ файла.
# Gunicorn импортирует этот файл, и поток стартует автоматически.
bot_thread = Thread(target=run_bot_polling)
bot_thread.daemon = True  # Это значит, что поток умрет, если упадет сервер
bot_thread.start()

if __name__ == "__main__":
    # Этот блок сработает только при локальном запуске python server.py
    # На Render его заменит Gunicorn
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
