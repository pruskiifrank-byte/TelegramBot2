# bot.py
from telebot import TeleBot, types
import telebot
import os
import random
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
CALLBACK_URL = os.getenv("CALLBACK_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
if not API_TOKEN:
    raise RuntimeError("API_TOKEN is not set in env")

bot = TeleBot(API_TOKEN, parse_mode="HTML", threaded=False)

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
    "💚 «Не переживай, я почти добрый сегодня!» — P.S.Гринч.",
    "👀 «Если что-то пойдёт не так — это не я!» — честный Гринч.",
    "😂 «Я бы помог, но мне лень… шучу, я и так ничего не делаю!»",
    "😏 «Выбирай быстрее, пока я не передумал!»",
    "🎄 «Праздник у меня один — когда никто ничего не хочет…»",
    "🧦 «Мои носки пахнут лучше, чем настроение людей…» — Гринч.",
    "🔥 «Я не злой, я просто… тёплый изнутри!»",
    "😼 «Если подарок исчезнет — знай, его забрал… Неуловимый любитель чужих подарков»",
    "😼 ««Улыбаетесь? Потерпите, сейчас пройдёт.»»",
    "😈 Гринч шепчет: «Выбирай осторожнее, а то вдруг понравится!»",
]

user_data = {}
orders = {}
last_text_messages = {}


def send_temp_message(chat_id, text, reply_markup=None):
    msg = bot.send_message(chat_id, text, reply_markup=reply_markup)
    if chat_id in last_text_messages:
        try:
            bot.delete_message(chat_id, last_text_messages[chat_id])
        except Exception:
            pass
    last_text_messages[chat_id] = msg.message_id
    return msg


@bot.message_handler(commands=["start"])
def send_welcome(message):
    chat_id = message.chat.id
    user_name = message.from_user.first_name or "друг"
    user_data[chat_id] = {}
    welcome_text = (
        f"🎄 Привет, {user_name}! 🎁\n"
        "Добро пожаловать к Гринчу!\n"
        "💰 Оплата — Global24\n"
        "Выберите город:"
    )
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Запорожье")

    send_temp_message(chat_id, welcome_text)
    bot.send_message(chat_id, "Выберите город:", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == "Запорожье")
def city_choice(message):
    chat_id = message.chat.id
    user_data.setdefault(chat_id, {})
    user_data[chat_id]["city"] = message.text

    send_temp_message(chat_id, f"Город выбран: {message.text}")
    send_product_menu(message)
    bot.send_message(chat_id, random.choice(grinch_jokes))


def send_product_menu(message):
    chat_id = message.chat.id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("Товар 1")
    markup.row("Мои заказы")
    bot.send_message(chat_id, "Выберите товар:", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text in products.keys())
def product_choice(message):
    chat_id = message.chat.id
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
    except FileNotFoundError:
        bot.send_message(
            chat_id,
            f"{product['description']}\nЦена: {product['price']} грн.",
            reply_markup=markup,
        )

    bot.send_message(chat_id, random.choice(grinch_jokes))


@bot.message_handler(func=lambda m: m.text in ["Назад", "Выбрать адрес доставки"])
def address_step(message):
    chat_id = message.chat.id

    if message.text == "Назад":
        send_product_menu(message)
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for addr in delivery_addresses:
        markup.add(addr)

    markup.add("⬅️ Назад к товарам")

    send_temp_message(chat_id, "Выберите район доставки:")
    bot.send_message(chat_id, "Адреса:", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == "⬅️ Назад к товарам")
def back_to_products(message):
    send_product_menu(message)


@bot.message_handler(func=lambda m: m.text in delivery_addresses)
def confirm_order(message):
    chat_id = message.chat.id
    user_data.setdefault(chat_id, {})
    user_data[chat_id]["address"] = message.text

    order_number = str(random.randint(10000, 99999))
    user_data[chat_id]["order_id"] = order_number

    product_name = user_data[chat_id].get("product")
    amount = products[product_name]["price"]

    orders[order_number] = {
        "user_id": chat_id,
        "product": product_name,
        "status": "pending",
        "amount": amount,
    }

    city = user_data[chat_id].get("city", "—")
    text = (
        f"✅ Заказ №{order_number} создан!\n\n"
        f"Город: {city}\n"
        f"Район: {message.text}\n"
        f"Товар: {product_name}\n"
        f"Цена: {amount} грн.\n\n"
        "Нажмите кнопку ниже для оплаты:"
    )

    send_payment_button(chat_id, order_number, product_name, amount, text)


@bot.message_handler(func=lambda m: m.text == "Мои заказы")
def my_orders(message):
    chat_id = message.chat.id

    user_orders = [
        oid
        for oid, data in orders.items()
        if data.get("user_id") == chat_id and data.get("status") != "canceled"
    ]

    if not user_orders:
        bot.send_message(chat_id, "📭 У вас нет активных заказы.")
        return

    text = "📦 Ваши активные заказы:\n\n"
    for oid in user_orders:
        product = orders[oid].get("product")
        district = user_data.get(chat_id, {}).get("address", "—")
        status = orders[oid].get("status", "—")
        text += f"• №{oid} — {product}, район: {district}, статус: {status}\n"

    bot.send_message(chat_id, text)


def send_payment_button(chat_id, order_id, product_name, amount, text):
    card_number = "2066 6652 7388 94"

    payment_text = (
        f"{text}\n\n"
        f"💳 *Оплата вручную*\n"
        f"Переведите сумму: *{amount} грн*\n"
        f"На карту: *{card_number}*\n\n"
        f"После оплаты бот автоматически подтвердит заказ.\n"
        f"❗ Это занимает 3–10 секунд.\n"
    )

    remove_keyboard = types.ReplyKeyboardRemove()

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✔ Я оплатил", callback_data=f"paid_{order_id}")
    )
    markup.add(
        types.InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_{order_id}")
    )

    bot.send_message(
        chat_id,
        payment_text,
        parse_mode="Markdown",
        reply_markup=remove_keyboard,
    )

    bot.send_message(chat_id, "👇 Выберите действие:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_"))
def cancel_order_callback(call):
    order_id = call.data.split("_", 1)[1]
    order = orders.get(order_id)

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            "Да, отменить", callback_data=f"confirm_cancel_{order_id}"
        )
    )
    markup.add(types.InlineKeyboardButton("Нет", callback_data="cancel_no"))

    if not order:
        bot.answer_callback_query(call.id, "Заказ не найден")
        bot.send_message(call.message.chat.id, f"Заказ №{order_id} не найден.")
        return

    bot.edit_message_text(
        f"Отменить заказ №{order_id}?",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("paid_"))
def confirm_payment_try(call):
    order_id = call.data.split("_", 1)[1]
    bot.answer_callback_query(call.id, "Ожидаю подтверждение оплаты...")
    bot.send_message(
        call.message.chat.id,
        f"⏳ Проверяю платеж для заказа №{order_id}...\nПожалуйста, подождите 3–10 секунд.",
        reply_markup=types.ReplyKeyboardRemove(),  # скрыть клавиатуру здесь тоже
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_cancel_"))
def cancel_confirm(call):
    order_id = call.data.split("_", 2)[2]
    order = orders.get(order_id)

    if not order:
        bot.answer_callback_query(call.id, "Заказ не найден")
        bot.edit_message_text(
            f"Заказ №{order_id} не найден.",
            call.message.chat.id,
            call.message.message_id,
        )
        return

    orders.pop(order_id, None)
    chat_id = order.get("user_id")
    user_data.pop(chat_id, None)

    bot.edit_message_text(
        f"Заказ №{order_id} отменён.",
        call.message.chat.id,
        call.message.message_id,
    )

    bot.send_message(chat_id, "Меню скрыто.", reply_markup=types.ReplyKeyboardRemove())


@bot.callback_query_handler(func=lambda call: call.data == "cancel_no")
def cancel_no(call):
    bot.answer_callback_query(call.id, "Отмена отменена")


def give_product(chat_id, product_name):
    product = products.get(product_name)
    if not product:
        bot.send_message(chat_id, "Ошибка: товар не найден.")
        return

    bot.send_message(
        chat_id, product["delivery_text"], reply_markup=types.ReplyKeyboardRemove()
    )

    try:
        with open(product["delivery_photo"], "rb") as photo:
            bot.send_photo(chat_id, photo)
    except FileNotFoundError:
        pass

    to_delete = None
    for oid, data in list(orders.items()):
        if data.get("user_id") == chat_id:
            to_delete = oid
            break

    if to_delete:
        orders.pop(to_delete, None)
    user_data.pop(chat_id, None)

    bot.send_message(chat_id, "🎁 Успех! Заказ выполнен.")


def process_update(json_str: str):
    try:
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception:
        pass
