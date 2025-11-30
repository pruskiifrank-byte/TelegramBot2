# server.py
from flask import Flask, request, abort
import telebot
import os
import requests  # НУЖЕН ДЛЯ ПРОВЕРКИ API
from bot.config import TELEGRAM_TOKEN, OXAPAY_API_KEY, ADMIN_IDS
from bot.bot import bot
from bot.storage import update_order, get_order, get_product_details_by_id
from bot.payment import handle_oxapay_callback

app = Flask(__name__)


# --- БЕЗОПАСНОСТЬ: Проверка через API OxaPay ---
def verify_payment_via_api(track_id):
    url = "https://api.oxapay.com/v1/payment/status"
    data = {"merchant_api_key": OXAPAY_API_KEY, "track_id": track_id}
    try:
        r = requests.post(url, json=data, timeout=10).json()
        if r.get("result") == 100 and r.get("data", {}).get("status") in [
            "Paid",
            "Confirmed",
            "paid",
        ]:
            return True
    except Exception as e:
        print(f"API Check Error: {e}")
    return False


# --- ВЫДАЧА ТОВАРА ---
def give_product(user_id, order_id):
    order = get_order(order_id)
    if not order or order["delivery_status"] == "delivered":
        return False  # Уже выдали

    prod = get_product_details_by_id(order["product_id"])
    if not prod:
        return False

    text = f"✅ <b>Оплата прошла!</b>\nТовар: {prod['product_name']}\n\n📍 <b>КЛАД:</b>\n{prod['delivery_text']}"

    try:
        # Отправляем фото по ID
        bot.send_photo(user_id, prod["file_path"], caption=text, parse_mode="HTML")
        update_order(order_id, delivery_status="delivered")
        return True
    except telebot.apihelper.ApiTelegramException as e:
        # Если бот в блоке, шлем админу
        for adm in ADMIN_IDS:
            bot.send_message(
                adm,
                f"🆘 АВАРИЯ! Клиент {user_id} оплатил, но заблокировал бота!\nOrder: {order_id}",
            )
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
