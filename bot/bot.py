# bot/bot.py

import telebot
from telebot import types
import time
from datetime import datetime, timedelta
import math
import random
from bot.config import TELEGRAM_TOKEN

# Импортируем create_invoice корректно
from bot.payment import create_invoice

# Импорты хранилища
from bot.storage import update_order, find_orders_by_user, get_order, add_order
from bot.storage import get_all_stores, get_products_by_store, get_product_details_by_id
from bot.db import execute_query

# -------------------------
# Константы, состояние и Анти-Флуд
# -------------------------
ADDRESSES = ["Бульвар Шевченко", "Ул. Победы", "Проспект Мира"]
user_state = {}

# Константы для Анти-Флуда
FLOOD_LIMIT_SECONDS = 0.8
flood_control = {}

# Константы для Бронирования
INITIAL_RESERVATION_HOURS = 1
MAX_UNPAID_ORDERS = 3

# ТЕМАТИЧЕСКИЕ ШУТКИ ГРИНЧА
grinch_jokes = [
    "😈 Гринч ворчит: «Опять ты… ну ладно, выбирай!»",
    "🎁 Гринч шепчет: «Это не подарок… это стратегическая пакость!»",
    "💚 «Не переживай, я почти добрый сегодня!»",
    "👀 «Если что-то пойдёт не так — это не я!»",
]

# Создаём бота
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML", threaded=False)


# -------------------------
# АНТИ-ФЛУД ДЕКОРАТОР
# -------------------------
def anti_flood(func):
    """Декоратор для ограничения частоты сообщений от пользователя."""

    def wrapper(message):
        if isinstance(message, telebot.types.CallbackQuery):
            uid = message.from_user.id
        elif isinstance(message, telebot.types.Message):
            uid = message.chat.id
        else:
            return func(message)

        current_time = time.time()
        last_time = flood_control.get(uid, 0)

        if current_time - last_time < FLOOD_LIMIT_SECONDS:
            return

        flood_control[uid] = current_time
        return func(message)

    return wrapper


# -------------------------
# ХЕЛПЕРЫ ДЛЯ КЛАВИАТУР
# -------------------------
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("🛒 Купить"))
    kb.add(types.KeyboardButton("📦 Мои заказы"))
    kb.add(types.KeyboardButton("📍 Показать адрес"))
    return kb


def back_to_main_menu_inline():
    return types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🔙 Главное меню", callback_data="cmd_main_menu")
    )


def create_inline_markup_with_back(buttons, back_callback_data="cmd_main_menu"):
    markup = types.InlineKeyboardMarkup()
    if buttons:
        if isinstance(buttons[0], list):
            for row in buttons:
                markup.row(*row)
        else:
            markup.add(*buttons)
    markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data=back_callback_data))
    return markup


# -------------------------
# ОСНОВНЫЕ КОМАНДЫ
# -------------------------
@bot.message_handler(commands=["start"])
@anti_flood
def cmd_start(message):
    uid = message.chat.id
    user_name = message.from_user.first_name or "Гость"

    welcome_text = (
        f"🎄 Привет, {user_name}! 🎁\n"
        "Добро пожаловать к Гринчу!\n"
        "💰 Оплата — Крипта\n"
        "Выберите действие в меню ниже:"
    )

    bot.send_message(uid, welcome_text, reply_markup=main_menu())


@bot.callback_query_handler(func=lambda call: call.data == "cmd_main_menu")
@anti_flood
def cmd_main_menu_callback(call):
    bot.answer_callback_query(call.id, "Главное меню")
    bot.send_message(
        call.message.chat.id,
        "Вы в главном меню. Выберите действие:",
        reply_markup=main_menu(),
    )
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass


@bot.message_handler(func=lambda m: m.text == "🛒 Купить")
@anti_flood
def handle_buy_button(message):
    uid = message.chat.id

    stores = get_all_stores()
    if not stores:
        return bot.send_message(uid, "❌ Каталог магазинов пуст.")

    joke = random.choice(grinch_jokes)

    markup_buttons = [
        types.InlineKeyboardButton(
            store["title"], callback_data=f"store_{store['store_id']}"
        )
        for store in stores
    ]

    markup = create_inline_markup_with_back(
        markup_buttons, back_callback_data="cmd_main_menu"
    )

    bot.send_message(
        uid, f"{joke}\n\nВыберите магазин:", reply_markup=markup, parse_mode="Markdown"
    )


# -------------------------
# ЭТАПЫ ПОКУПКИ
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("store_"))
@anti_flood
def handle_store_selection(call):
    uid = call.from_user.id
    store_id = call.data.split("_")[1]
    user_state[uid] = {"store_id": store_id}

    products = get_products_by_store(store_id)

    if not products:
        return bot.edit_message_text(
            "❌ Товары в этом магазине отсутствуют.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_to_main_menu_inline(),
        )

    markup_buttons = [
        types.InlineKeyboardButton(
            product["name"], callback_data=f"product_{store_id}_{product['product_id']}"
        )
        for product in products
    ]

    markup = create_inline_markup_with_back(
        markup_buttons, back_callback_data="cmd_buy_callback"
    )

    bot.edit_message_text(
        "Выберите товар:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
    )
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "cmd_buy_callback")
@anti_flood
def handle_back_to_buy(call):
    uid = call.from_user.id
    stores = get_all_stores()

    markup_buttons = [
        types.InlineKeyboardButton(
            store["title"], callback_data=f"store_{store['store_id']}"
        )
        for store in stores
    ]
    markup = create_inline_markup_with_back(
        markup_buttons, back_callback_data="cmd_main_menu"
    )

    joke = random.choice(grinch_jokes)

    bot.edit_message_text(
        f"{joke}\n\nВыберите магазин:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode="Markdown",
    )
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("product_"))
@anti_flood
def handle_product_selection(call):
    uid = call.from_user.id
    try:
        parts = call.data.split("_")
        # Обработка формата product_STOREID_PRODUCTID или product_PRODUCTID (возврат)
        if len(parts) == 3:
            _, store_id, product_id = parts
        else:
            # Если вернулись назад
            product_id = parts[1]
            # Получаем детали чтобы узнать store_id
            det = get_product_details_by_id(int(product_id))
            # Здесь нам нужно получить store_id, но get_product_details_by_id возвращает shop_title
            # Для упрощения кнопки "назад" можно просто вернуть в главное меню или переделать логику
            # Сейчас оставим store_id из user_state если есть
            store_id = user_state.get(uid, {}).get("store_id", "1")

        product_details = get_product_details_by_id(int(product_id))
    except (IndexError, ValueError):
        return bot.send_message(uid, "❌ Ошибка ID товара.")

    if not product_details:
        return bot.send_message(uid, "❌ Товар не найден.")

    user_state[uid] = {"current_product_details": product_details, "store_id": store_id}

    product_name = product_details.get("product_name", "Товар без названия")
    price = product_details.get("price_usd", 0.0)

    markup_buttons = [
        types.InlineKeyboardButton(address, callback_data=f"addr_{product_id}_{i}")
        for i, address in enumerate(ADDRESSES)
    ]

    markup = create_inline_markup_with_back(
        markup_buttons, back_callback_data=f"store_{store_id}"
    )

    bot.edit_message_text(
        f"**Выбран товар:** {product_name}\nЦена: {price:.2f} $\n\nВыберите адрес:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode="Markdown",
    )
    bot.answer_callback_query(call.id)


# -------------------------
# ЭТАП 4: Обработка выбора адреса (ПОДТВЕРЖДЕНИЕ С ФОТО)
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("addr_"))
@anti_flood
def handle_address_selection(call):
    uid = call.from_user.id

    # 1. ПРОВЕРКА ЛИМИТА
    orders = find_orders_by_user(uid)
    unpaid_count = 0
    now = datetime.now()

    if orders:
        for order_id, data in orders.items():
            if data.get("status") == "waiting_payment":
                # В find_orders_by_user мы не возвращаем reservation_expires_at,
                # поэтому здесь упрощенная проверка или нужно доработать запрос.
                # Считаем просто все неоплаченные:
                unpaid_count += 1

    if unpaid_count >= MAX_UNPAID_ORDERS:
        bot.answer_callback_query(
            call.id,
            f"Лимит! У вас уже {MAX_UNPAID_ORDERS} неоплаченных заказов.",
            show_alert=True,
        )
        bot.send_message(
            uid,
            f"❌ **Лимит неоплаченных заказов ({MAX_UNPAID_ORDERS}) достигнут.**\n\n",
            parse_mode="Markdown",
            reply_markup=back_to_main_menu_inline(),
        )
        return

    # 2. ПОЛУЧЕНИЕ ДАННЫХ
    try:
        _, product_id, address_index = call.data.split("_")
        product_id = int(product_id)
        address_index = int(address_index)
        selected_address = ADDRESSES[address_index]
    except (IndexError, ValueError):
        return bot.send_message(uid, "❌ Ошибка выбора товара/адреса.")

    product_details = get_product_details_by_id(product_id)
    if not product_details:
        return bot.send_message(uid, "❌ Ошибка: товар не найден.")

    price = product_details.get("price_usd", 0.0)
    product_name = product_details.get("product_name", "Товар без названия")
    file_path = product_details.get("file_path", "placeholder.jpg")
    product_description = product_details.get(
        "delivery_text", "Описание при покупке."
    )  # delivery_text используется как описание

    # 3. БРОНИРОВАНИЕ И СОЗДАНИЕ ИНВОЙСА
    # Вот здесь объявляем переменную, на которую ругался Pylance
    reservation_expires_at = datetime.now() + timedelta(hours=INITIAL_RESERVATION_HOURS)

    # Создаем временный ID для инвойса
    temp_order_id = f"ORD-{int(time.time())}-{uid}"

    # Создаем инвойс
    invoice_data = create_invoice(uid, price, temp_order_id)

    if not invoice_data:
        bot.answer_callback_query(call.id, "Ошибка создания платежа.", show_alert=True)
        return bot.send_message(
            uid, "❌ Не удалось создать платежную ссылку. Попробуйте позже."
        )

    payment_url, track_id = invoice_data

    # Сохраняем заказ в БД
    order_id = add_order(
        uid, product_id, price, selected_address, temp_order_id, track_id, payment_url
    )

    # 4. ОТПРАВКА ПОДТВЕРЖДЕНИЯ С ФОТОГРАФИЕЙ
    caption_text = (
        f"✅ **Подтверждение заказа №{order_id}**\n\n"
        f"**Товар:** {product_name}\n"
        f"**Адрес:** {selected_address}\n"
        f"**Цена:** {price:.2f} $\n"
        f"**Бронь до:** {reservation_expires_at.strftime('%Y-%m-%d %H:%M:%S')} (UTC)\n\n"
        f"**Описание:**\nТовар забронирован. Оплатите для получения."
    )

    try:
        with open(file_path, "rb") as f:
            bot.send_photo(uid, f, caption=caption_text, parse_mode="Markdown")
    except FileNotFoundError:
        bot.send_message(
            uid,
            caption_text
            + "\n\n❌ **ВНИМАНИЕ:** Фотография товара не найдена (нет файла на сервере).",
            parse_mode="Markdown",
        )

    # 5. ОТПРАВКА КНОПКИ ОПЛАТЫ
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Оплатить", url=payment_url))
    markup.add(
        types.InlineKeyboardButton(
            "🔙 Назад (Выбрать другой адрес)", callback_data=f"product_{product_id}"
        )
    )

    bot.send_message(
        uid,
        "**Для завершения** перейдите по ссылке ниже.\n"
        "Не забудьте отправить **TxID** после оплаты, если потребуется!",
        parse_mode="Markdown",
        reply_markup=markup,
    )

    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

    bot.answer_callback_query(call.id, "Заказ создан.")
