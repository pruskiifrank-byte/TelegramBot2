# bot.py
from telebot import TeleBot, types
import telebot
import os
import random
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
if not API_TOKEN:
    raise RuntimeError("API_TOKEN is not set in .env")

bot = TeleBot(API_TOKEN, parse_mode="HTML", threaded=False)

# ---------------------------------------
#              ДАННЫЕ
# ---------------------------------------
products = {
    "Товар 1": {
        "photo": "images/Огурец.jpg",
        "description": "Описание Товара 1",
        "price": 15,
        "delivery_photo": "delivery/adr1.jpg",
        "delivery_text": "📍 Бульвар 1, дом 7 (тайник возле дерева)",
    },
}

delivery_addresses = ["Бульвар Шевченко", "Улица Центральная", "Проспект Мира"]

grinch_jokes = [
    "😈 Гринч ворчит: «Опять ты… ну ладно, выбирай!»",
    "🎁 Гринч шепчет: «Это не подарок… это стратегическая пакость!»",
    "💚 «Не переживай, я почти добрый сегодня!»",
    "👀 «Если что-то пойдёт не так — это не я!»",
]

user_data = {}
orders = {}  # order_id → {user_id, product, status, amount, txID}

last_text_messages = {}

# антифлуд
user_last_message = {}
user_last_callback = {}
FLOOD_SECONDS = float(os.getenv("FLOOD_SECONDS", "0.8"))
CALLBACK_FLOOD_SECONDS = float(os.getenv("CALLBACK_FLOOD_SECONDS", "0.5"))


def is_flood_message(chat_id):
    import time

    now = time.time()
    last = user_last_message.get(chat_id, 0)
    if now - last < FLOOD_SECONDS:
        return True
    user_last_message[chat_id] = now
    return False


def is_flood_callback(uid):
    import time

    now = time.time()
    last = user_last_callback.get(uid, 0)
    if now - last < CALLBACK_FLOOD_SECONDS:
        return True
    user_last_callback[uid] = now
    return False


# ---------------------------------------
#          УТИЛИТЫ
# ---------------------------------------
def send_temp_message(chat_id, text, reply_markup=None):
    msg = bot.send_message(chat_id, text, reply_markup=reply_markup)
    if chat_id in last_text_messages:
        try:
            bot.delete_message(chat_id, last_text_messages[chat_id])
        except:
            pass
    last_text_messages[chat_id] = msg.message_id
    return msg


# ---------------------------------------
#          КОМАНДА /start
# ---------------------------------------
@bot.message_handler(commands=["start"])
def send_welcome(message):
    chat_id = message.chat.id
    user_name = message.from_user.first_name or "друг"
    user_data.setdefault(chat_id, {})
    welcome_text = (
        f"🎄 Привет, {user_name}! 🎁\n"
        "Добро пожаловать к Гринчу!\n"
        "💰 Оплата — Global24 (P2P)\n"
        "После оплаты нужно отправить txID\n"
        "Выберите город:"
    )
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Запорожье")
    send_temp_message(chat_id, welcome_text)
    bot.send_message(chat_id, "Выберите город:", reply_markup=markup)


# Обработчик для кнопок "Назад" и "Выбрать адрес доставки"


@bot.message_handler(func=lambda m: m.text in ["Назад", "Выбрать адрес доставки"])
def address_step(message):
    chat_id = message.chat.id
    if is_flood_message(chat_id):
        return

    # Кнопка "Назад" просто возвращает к списку товаров
    if message.text == "Назад":
        send_product_menu(message)
        return

    # Кнопка "Выбрать адрес доставки" — показываем клавиатуру с адресами
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for addr in delivery_addresses:
        markup.add(addr)
    # добавляем опцию вернуться к товарам
    markup.add("⬅️ Назад к товарам")
    send_temp_message(chat_id, "Выберите район доставки:")
    bot.send_message(chat_id, "Адреса:", reply_markup=markup)


# Обработчик для кнопки "⬅️ Назад к товарам"
@bot.message_handler(func=lambda m: m.text == "⬅️ Назад к товарам")
def back_to_products(message):
    send_product_menu(message)


# ---------------------------------------
#            Город
# ---------------------------------------
@bot.message_handler(func=lambda m: m.text == "Запорожье")
def city_choice(message):
    chat_id = message.chat.id
    if is_flood_message(chat_id):
        return
    user_data.setdefault(chat_id, {})
    user_data[chat_id]["city"] = message.text
    send_temp_message(chat_id, f"Город выбран: {message.text}")
    send_product_menu(message)
    bot.send_message(chat_id, random.choice(grinch_jokes))


def send_product_menu(message):
    chat_id = message.chat.id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for p in products:
        markup.add(p)
    markup.add("Мои заказы")
    bot.send_message(chat_id, "Выберите товар:", reply_markup=markup)


# Обработчик для кнопок "Назад" и "Выбрать адрес доставки"
@bot.message_handler(func=lambda m: m.text in ["Назад", "Выбрать адрес доставки"])
def address_step(message):
    chat_id = message.chat.id
    if is_flood_message(chat_id):
        return

    # Кнопка "Назад" просто возвращает к списку товаров
    if message.text == "Назад":
        send_product_menu(message)
        return

    # Кнопка "Выбрать адрес доставки" — показываем клавиатуру с адресами
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for addr in delivery_addresses:
        markup.add(addr)
    # добавляем опцию вернуться к товарам
    markup.add("⬅️ Назад к товарам")
    send_temp_message(chat_id, "Выберите район доставки:")
    bot.send_message(chat_id, "Адреса:", reply_markup=markup)


# Обработчик для кнопки "⬅️ Назад к товарам"
@bot.message_handler(func=lambda m: m.text == "⬅️ Назад к товарам")
def back_to_products(message):
    send_product_menu(message)


# ---------------------------------------
#          Выбор товара
# ---------------------------------------
@bot.message_handler(func=lambda m: m.text in products)
def product_choice(message):
    chat_id = message.chat.id
    if is_flood_message(chat_id):
        return

    user_data.setdefault(chat_id, {})
    user_data[chat_id]["product"] = message.text

    product = products[message.text]

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("Выбрать адрес доставки", "Назад")

    try:
        with open(product["photo"], "rb") as p:
            bot.send_photo(
                chat_id,
                p,
                caption=f"{product['description']}\nЦена: {product['price']} грн.",
                reply_markup=markup,
            )
    except:
        bot.send_message(
            chat_id,
            f"{product['description']}\nЦена: {product['price']} грн.",
            reply_markup=markup,
        )

    bot.send_message(chat_id, random.choice(grinch_jokes))


# ---------------------------------------
#     Адрес → создание заказа
# ---------------------------------------
@bot.message_handler(func=lambda m: m.text in delivery_addresses)
def confirm_order(message):
    chat_id = message.chat.id
    if is_flood_message(chat_id):
        return

    user_data.setdefault(chat_id, {})
    user_data[chat_id]["address"] = message.text

    import random

    order_id = str(random.randint(10000, 99999))

    user_data[chat_id]["order_id"] = order_id

    product_name = user_data[chat_id].get("product")
    amount = products[product_name]["price"]

    orders[order_id] = {
        "user_id": chat_id,
        "product": product_name,
        "status": "pending",
        "amount": amount,
        "txID": None,
    }

    city = user_data[chat_id].get("city", "—")

    text = (
        f"✅ Заказ №{order_id} создан!\n\n"
        f"Город: {city}\n"
        f"Адрес: {message.text}\n"
        f"Товар: {product_name}\n"
        f"Цена: {amount} грн.\n\n"
        "💳 Оплатите через Global24 (P2P) на вашу карту.\n"
        "После оплаты нажмите «Я оплатил»."
    )

    send_payment_button(chat_id, order_id, text)


# ---------------------------------------
#      КНОПКИ ОПЛАТЫ
# ---------------------------------------
def send_payment_button(chat_id, order_id, text):
    remove_kb = types.ReplyKeyboardRemove()

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✔ Я оплатил", callback_data=f"paid_{order_id}")
    )
    markup.add(
        types.InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_{order_id}")
    )

    bot.send_message(chat_id, text, reply_markup=remove_kb)
    bot.send_message(chat_id, "👇 Выберите действие:", reply_markup=markup)


# ---------------------------------------
#    Пользователь нажал «Я оплатил»
# ---------------------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("paid_"))
def enter_txid(call):
    if is_flood_callback(call.from_user.id):
        bot.answer_callback_query(call.id, "Подождите", show_alert=False)
        return

    order_id = call.data.split("_", 1)[1]

    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        f"Введите *txID* из уведомления Global24\n\n"
        f"📌 Пример: `7664436`\n"
        f"Или последние 4 цифры.",
        parse_mode="Markdown",
    )

    bot.register_next_step_handler(msg, save_txid_step, order_id)


def save_txid_step(message, order_id):
    chat_id = message.chat.id

    txid = message.text.strip()

    if not txid.isdigit():
        bot.send_message(chat_id, "⚠ txID должен быть числом. Попробуйте ещё раз.")
        return

    if order_id not in orders:
        bot.send_message(chat_id, "Ошибка: заказ не найден.")
        return

    orders[order_id]["txID"] = txid

    bot.send_message(
        chat_id,
        f"🧾 txID `{txid}` сохранён!\n\n" "⏳ Ожидаю подтверждение от Global24...",
    )


# ---------------------------------------
#   Отмена заказа
# ---------------------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_"))
def cancel_order(call):
    if is_flood_callback(call.from_user.id):
        bot.answer_callback_query(call.id, "Подождите")
        return

    order_id = call.data.split("_", 1)[1]

    if order_id in orders:
        orders.pop(order_id)

    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f"❌ Заказ №{order_id} отменён.")


# ---------------------------------------
#      Выдача товара
# ---------------------------------------
def give_product(chat_id, product_name):
    product = products.get(product_name)
    if not product:
        bot.send_message(chat_id, "Ошибка: товар не найден.")
        return

    try:
        bot.send_message(chat_id, product["delivery_text"])
        with open(product["delivery_photo"], "rb") as p:
            bot.send_photo(chat_id, p)
    except:
        pass

    bot.send_message(chat_id, "🎁 Успех! Заказ выполнен.")


# ---------------------------------------
#   Обработка /webhook от Flask
# ---------------------------------------
def process_update(json_str: str):
    try:
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except:
        pass
