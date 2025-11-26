# bot.py
from telebot import TeleBot, types
import telebot
import os
import random
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
CALLBACK_URL = os.getenv(
    "CALLBACK_URL"
)  # URL, который Global24 использует для callback (может быть тот же домен)
if not API_TOKEN:
    raise RuntimeError("API_TOKEN is not set in env")

# создаём бота
bot = TeleBot(API_TOKEN, parse_mode="HTML", threaded=False)

# ---------- Товары ----------
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

# ---------- Состояния ----------
# user_data: chat_id -> { city, product, address, order_id }
user_data = {}
# orders: order_id -> { user_id, product, status, amount }
orders = {}
# last_text_messages: chat_id -> message_id (для "чистых" сообщений)
last_text_messages = {}

# ---------- Антифлуд ----------
user_last_message = {}  # chat_id -> last_time for messages
user_last_callback = {}  # user_id -> last_time for callback queries
FLOOD_SECONDS = float(os.getenv("FLOOD_SECONDS", "0.8"))  # минимум между сообщениями
CALLBACK_FLOOD_SECONDS = float(os.getenv("CALLBACK_FLOOD_SECONDS", "0.5"))


def is_flood_message(chat_id: int) -> bool:
    import time

    now = time.time()
    last = user_last_message.get(chat_id, 0)
    if now - last < FLOOD_SECONDS:
        return True
    user_last_message[chat_id] = now
    return False


def is_flood_callback(user_id: int) -> bool:
    import time

    now = time.time()
    last = user_last_callback.get(user_id, 0)
    if now - last < CALLBACK_FLOOD_SECONDS:
        return True
    user_last_callback[user_id] = now
    return False


# ---------- Утилиты ----------
def send_temp_message(chat_id, text, reply_markup=None):
    msg = bot.send_message(chat_id, text, reply_markup=reply_markup)
    if chat_id in last_text_messages:
        try:
            bot.delete_message(chat_id, last_text_messages[chat_id])
        except Exception:
            pass
    last_text_messages[chat_id] = msg.message_id
    return msg


# ---------- Хендлеры ----------
@bot.message_handler(commands=["start"])
def send_welcome(message):
    chat_id = message.chat.id
    user_name = message.from_user.first_name or "друг"
    user_data.setdefault(chat_id, {})
    welcome_text = (
        f"🎄 Привет, {user_name}! 🎁\n"
        "Добро пожаловать к Гринчу!\n"
        "💰 Оплата — Global24\n"
        "Актуальные контакты - опер @mrgrinchs\n"
        "За пробами в лс условия\n"
        "Резерв на случай если снесут основу @scooby_doorezerv2\n"
        "Выберите город:"
    )
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Запорожье")
    send_temp_message(chat_id, welcome_text)
    bot.send_message(chat_id, "Выберите город:", reply_markup=markup)


@bot.message_handler(commands=["help"])
def help_command(message):
    text = (
        "❓ Помощь\n\n"
        "• Выберите товар и оплатите его\n"
        "• После оплаты получите фото и текст с местом подарка\n\n"
        "Команды:\n"
        "/start — перезапустить бота\n"
        "/help — справка\n"
        "Кнопка 'Мои заказы' — показать активные заказы"
    )
    bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda m: m.text == "Запорожье")
def city_choice(message):
    chat_id = message.chat.id
    if is_flood_message(chat_id):
        return
    user_data.setdefault(chat_id, {})
    user_data[chat_id]["city"] = message.text
    send_temp_message(chat_id, f"Город выбран: {message.text}")
    send_product_menu(message)
    # шутка, не нагружая поток
    try:
        bot.send_message(chat_id, random.choice(grinch_jokes))
    except Exception:
        pass


def send_product_menu(message):
    chat_id = message.chat.id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    # список товаров
    rows = list(products.keys())
    # добавляем по 2 в строке, но можно настроить
    if rows:
        for i in range(0, len(rows), 2):
            markup.row(*rows[i : i + 2])
    markup.row("Мои заказы")
    bot.send_message(chat_id, "Выберите товар:", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text in products.keys())
def product_choice(message):
    chat_id = message.chat.id
    if is_flood_message(chat_id):
        return
    user_data.setdefault(chat_id, {})
    user_data[chat_id]["product"] = message.text
    product = products[message.text]
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("Выбрать адрес доставки", "Назад")
    # отправка фото, если есть
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
    except Exception:
        bot.send_message(
            chat_id,
            f"{product['description']}\nЦена: {product['price']} грн.",
            reply_markup=markup,
        )
    # подпись-шутка
    try:
        bot.send_message(chat_id, random.choice(grinch_jokes))
    except Exception:
        pass


@bot.message_handler(func=lambda m: m.text in ["Назад", "Выбрать адрес доставки"])
def address_step(message):
    chat_id = message.chat.id
    if is_flood_message(chat_id):
        return
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
    if is_flood_message(chat_id):
        return
    user_data.setdefault(chat_id, {})
    user_data[chat_id]["address"] = message.text
    # генерируем уникальный order_id
    order_number = str(random.randint(10000, 99999))
    user_data[chat_id]["order_id"] = order_number
    product_name = user_data[chat_id].get("product")
    if not product_name:
        bot.send_message(chat_id, "Ошибка: товар не выбран.")
        return
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
        bot.send_message(chat_id, "📭 У вас нет активных заказов.")
        return
    text = "📦 Ваши активные заказы:\n\n"
    for oid in user_orders:
        product = orders[oid].get("product")
        district = user_data.get(chat_id, {}).get("address", "—")
        status = orders[oid].get("status", "—")
        text += f"• №{oid} — {product}, район: {district}, статус: {status}\n"
    bot.send_message(chat_id, text)


@bot.message_handler(commands=["orders"])
def my_orders_command(message):
    my_orders(message)


def send_payment_button(chat_id, order_id, product_name, amount, text):
    # В этом примере — ручная оплата (карта). Если используешь Global24, подставь корректную ссылку.
    card_number = os.getenv("CARD_NUMBER", "2066 6652 7388 94")
    payment_text = (
        f"{text}\n\n"
        f"💳 *Оплата вручная*\n"
        f"Переведите сумму: *{amount} грн*\n"
        f"На карту: *{card_number}*\n\n"
        f"После оплаты нажмите «Я оплатил» — наш сервер проверит callback от платёжного шлюза.\n"
    )
    # удаляем клавиатуру с выбором
    remove_keyboard = types.ReplyKeyboardRemove()
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✔ Я оплатил", callback_data=f"paid_{order_id}")
    )
    markup.add(
        types.InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_{order_id}")
    )
    # сначала отправляем текст оплаты (скрываем Reply-клавиатуру)
    bot.send_message(
        chat_id, payment_text, parse_mode="Markdown", reply_markup=remove_keyboard
    )
    # отдельным сообщением показываем inline-кнопки (чтобы не путать)
    bot.send_message(chat_id, "👇 Выберите действие:", reply_markup=markup)


# ---------- CALLBACKS ----------
@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_"))
def cancel_order_callback(call):
    # anti-flood for callbacks
    if is_flood_callback(call.from_user.id):
        bot.answer_callback_query(call.id, "Слишком часто", show_alert=False)
        return

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
        try:
            bot.send_message(call.message.chat.id, f"Заказ №{order_id} не найден.")
        except Exception:
            pass
        return
    try:
        bot.edit_message_text(
            f"Отменить заказ №{order_id}?",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )
    except Exception:
        bot.send_message(
            call.message.chat.id, f"Отменить заказ №{order_id}?", reply_markup=markup
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith("paid_"))
def confirm_payment_try(call):
    if is_flood_callback(call.from_user.id):
        bot.answer_callback_query(call.id, "Слишком часто", show_alert=False)
        return
    order_id = call.data.split("_", 1)[1]
    bot.answer_callback_query(call.id, "Ожидаю подтверждение оплаты...")
    bot.send_message(
        call.message.chat.id,
        f"⏳ Проверяю платеж для заказа №{order_id}...\nПожалуйста, подождите 3–10 секунд.",
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_cancel_"))
def cancel_confirm(call):
    if is_flood_callback(call.from_user.id):
        bot.answer_callback_query(call.id, "Слишком часто", show_alert=False)
        return
    # safer extraction
    order_id = call.data.replace("confirm_cancel_", "", 1)
    order = orders.get(order_id)
    if not order:
        bot.answer_callback_query(call.id, "Заказ не найден")
        try:
            bot.edit_message_text(
                f"Заказ №{order_id} не найден.",
                call.message.chat.id,
                call.message.message_id,
            )
        except Exception:
            pass
        return
    # помечаем как отменённый и очищаем user_data
    orders.pop(order_id, None)
    chat_id = order.get("user_id")
    if chat_id in user_data:
        user_data.pop(chat_id, None)
    try:
        bot.edit_message_text(
            f"Заказ №{order_id} отменён.", call.message.chat.id, call.message.message_id
        )
    except Exception:
        bot.send_message(call.message.chat.id, f"Заказ №{order_id} отменён.")
    # убеждаемся, что клавиатура скрыта
    try:
        bot.send_message(
            chat_id, "Меню скрыто.", reply_markup=types.ReplyKeyboardRemove()
        )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda call: call.data == "cancel_no")
def cancel_no(call):
    bot.answer_callback_query(call.id, "Отмена отменена")


# ---------- Выдача товара ----------
def give_product(chat_id, product_name):
    product = products.get(product_name)
    if not product:
        bot.send_message(chat_id, "Ошибка: товар не найден.")
        return
    # высылаем текст и фото (клавиатуру убираем)
    try:
        bot.send_message(
            chat_id, product["delivery_text"], reply_markup=types.ReplyKeyboardRemove()
        )
        with open(product["delivery_photo"], "rb") as photo:
            bot.send_photo(chat_id, photo)
    except FileNotFoundError:
        pass
    # очищаем заказ(ы) пользователя
    to_delete = None
    for oid, data in list(orders.items()):
        if data.get("user_id") == chat_id:
            to_delete = oid
            break
    if to_delete:
        orders.pop(to_delete, None)
    if chat_id in user_data:
        user_data.pop(chat_id, None)
    try:
        bot.send_message(chat_id, "🎁 Успех! Заказ выполнен.")
    except Exception:
        pass


# ---------- process_update для Flask ----------
def process_update(json_str: str):
    try:
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception:
        # не поднимаем исключение, чтобы Flask всегда отвечал 200
        pass
