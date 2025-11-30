# bot/bot.py

import telebot
from telebot import types
import time
from datetime import datetime, timedelta
import random  # Для шуток
import math
from bot.config import TELEGRAM_TOKEN
from bot.payment import create_invoice
from bot.storage import update_order, find_orders_by_user, get_order, add_order
from bot.storage import get_all_stores, get_products_by_store, get_product_details_by_id
from bot.db import execute_query

# ЗАГЛУШКИ ДЛЯ ТЕСТИРОВАНИЯ (Замените на ваши реальные импорты)
TELEGRAM_TOKEN = "8211248581:AAHxBU1kzqiSQrNZMRzpFRoOaEfCA9ecclg"


def update_order(*args, **kwargs):
    pass


def find_orders_by_user(uid):
    # Возвращает пример данных для теста лимита:
    # 1 активный (неоплаченный) и 1 истекший (статус: paid, бронь не важна)
    return {
        101: {
            "status": "waiting_payment",
            "reservation_expires_at": (
                datetime.now() + timedelta(minutes=30)
            ).timestamp(),
            "price": 10,
            "product_name": "Товар А",
        },
        102: {
            "status": "paid",
            "reservation_expires_at": (datetime.now() - timedelta(hours=2)).timestamp(),
            "price": 20,
            "product_name": "Товар Б",
        },
        103: {
            "status": "waiting_payment",
            "reservation_expires_at": (datetime.now() - timedelta(hours=2)).timestamp(),
            "price": 30,
            "product_name": "Товар В (ИСТЕКШИЙ)",
        },
    }


def get_order(order_id):
    return {}


def add_order(uid, data):
    return 104  # ID нового заказа


def get_all_stores():
    return [{"store_id": 1, "title": "Город А"}, {"store_id": 2, "title": "Город Б"}]


def get_products_by_store(store_id):
    if store_id == 1:
        return [
            {"product_id": 10, "name": "Шишка (1г)", "price": 50},
            {"product_id": 11, "name": "Лист (5г)", "price": 100},
        ]
    return []


def get_product_details_by_id(product_id):
    return {
        "price": 50,
        "name": "Шишка (1г)",
        "description": "Лучшее качество, свежий завоз. Натуральный, чистый продукт.",
        "file_path": "images/example.jpg",  # Укажите реальный путь
    }


def execute_query(*args, **kwargs):
    return None


# КОНЕЦ ЗАГЛУШЕК
# -------------------------------------------------------------

# -------------------------
# Константы, состояние и Анти-Флуд
# -------------------------
ADDRESSES = [
    "Бульвар Шевченко, Клад 1",
    "Ул. Победы, Тайник 2",
    "Проспект Мира, Локация 3",
]
user_state = {}

# Константы для Анти-Флуда
FLOOD_LIMIT_SECONDS = 0.8
flood_control = {}

# Константы для Бронирования
INITIAL_RESERVATION_HOURS = 1  # ФИКСИРОВАННАЯ БРОНЬ 1 ЧАС

# НОВАЯ КОНСТАНТА: Максимальное количество неоплаченных заказов
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
        uid = message.chat.id
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
    """Возвращает клавиатуру с одной кнопкой 'Главное меню'."""
    return types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🔙 Главное меню", callback_data="cmd_main_menu")
    )


def create_inline_markup_with_back(buttons, back_callback_data="cmd_main_menu"):
    """Создает InlineKeyboardMarkup с кнопкой 'Назад'."""
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
# ОСНОВНЫЕ КОМАНДЫ И НАВИГАЦИЯ
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
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(
        call.message.chat.id,
        "Вы в главном меню. Выберите действие:",
        reply_markup=main_menu(),
    )


@bot.message_handler(func=lambda m: m.text == "🛒 Купить")
@anti_flood
def handle_buy_button(message):
    uid = message.chat.id
    stores = get_all_stores()

    if not stores:
        return bot.send_message(
            uid, "❌ Каталог магазинов пуст.", reply_markup=main_menu()
        )

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


@bot.callback_query_handler(func=lambda call: call.data == "cmd_buy_callback")
@anti_flood
def handle_back_to_buy(call):
    # Повторяем логику handle_buy_button для возврата к магазинам
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


@bot.callback_query_handler(func=lambda call: call.data.startswith("store_"))
@anti_flood
def handle_store_selection(call):
    uid = call.from_user.id
    store_id = call.data.split("_")[1]

    products = get_products_by_store(store_id)

    if not products:
        return bot.edit_message_text(
            "❌ Товары в этом магазине отсутствуют.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_to_main_menu_inline(),
        )

    markup_buttons = [
        # В callback_data передаем store_id для кнопки "Назад"
        types.InlineKeyboardButton(
            product["name"], callback_data=f"product_{store_id}_{product['product_id']}"
        )
        for product in products
    ]

    # Кнопка "Назад" ведет к списку магазинов (cmd_buy_callback)
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


@bot.callback_query_handler(
    func=lambda call: call.data.startswith("product_") and len(call.data.split("_")) > 2
)
@anti_flood
def handle_product_selection(call):
    uid = call.from_user.id
    try:
        _, store_id, product_id = call.data.split("_")
        product_details = get_product_details_by_id(int(product_id))
    except (IndexError, ValueError):
        return bot.send_message(uid, "❌ Ошибка ID товара.")

    if not product_details:
        return bot.send_message(uid, "❌ Товар не найден.")

    markup_buttons = [
        # В callback_data передаем product_id для финального шага
        types.InlineKeyboardButton(address, callback_data=f"addr_{product_id}_{i}")
        for i, address in enumerate(ADDRESSES)
    ]

    # Кнопка "Назад" ведет обратно к списку товаров в этом магазине
    markup = create_inline_markup_with_back(
        markup_buttons, back_callback_data=f"store_{store_id}"
    )

    bot.edit_message_text(
        f"**Выбран товар:** {product_details.get('name', 'N/A')}\nЦена: {product_details.get('price', 0):.2f} $\n\nВыберите адрес:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode="Markdown",
    )
    bot.answer_callback_query(call.id)


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
                # Считаем только заказы, чья бронь еще не истекла
                expiry_timestamp = data.get("reservation_expires_at", 0)
                expiry_dt = datetime.fromtimestamp(expiry_timestamp)
                if expiry_dt > now:
                    unpaid_count += 1

    if unpaid_count >= MAX_UNPAID_ORDERS:
        bot.answer_callback_query(
            call.id,
            f"Лимит! У вас уже {MAX_UNPAID_ORDERS} неоплаченных заказов.",
            show_alert=True,
        )
        bot.send_message(
            uid,
            f"❌ **Лимит неоплаченных заказов ({MAX_UNPAID_ORDERS}) достигнут.**\n\n"
            "Пожалуйста, оплатите один из ваших существующих заказов или подождите.",
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

    price = product_details.get("price", 0)
    product_name = product_details.get("name", "Товар")
    file_path = product_details.get("file_path", "placeholder.jpg")
    product_description = product_details.get(
        "description", "Описание не предоставлено."
    )

    # 3. БРОНИРОВАНИЕ И СОЗДАНИЕ ИНВОЙСА
    reservation_expires_at = datetime.now() + timedelta(
        hours=INITIAL_RESERVATION_HOURS
    )  # 1 ЧАС
    payment_url = "https://oxapay.io/pay"  # Замените на реальный вызов create_invoice

    new_order_data = {
        "product_id": product_id,
        "product_name": product_name,
        "price": price,
        "address": selected_address,
        "status": "waiting_payment",
        "payment_url": payment_url,
        "reservation_expires_at": reservation_expires_at.timestamp(),
        "is_reserved": True,
    }

    order_id = add_order(uid, new_order_data)

    # 4. ОТПРАВКА ПОДТВЕРЖДЕНИЯ С ФОТОГРАФИЕЙ
    caption_text = (
        f"✅ **Подтверждение заказа №{order_id}**\n\n"
        f"**Товар:** {product_name}\n"
        f"**Адрес:** {selected_address}\n"
        f"**Цена:** {price:.2f} $\n"
        f"**Бронь до:** {reservation_expires_at.strftime('%Y-%m-%d %H:%M:%S')} (UTC)\n\n"
        f"**Описание:**\n{product_description}"
    )

    try:
        with open(file_path, "rb") as f:
            bot.send_photo(uid, f, caption=caption_text, parse_mode="Markdown")
    except FileNotFoundError:
        bot.send_message(
            uid,
            caption_text + "\n\n❌ **ВНИМАНИЕ:** Фотография товара не найдена.",
            parse_mode="Markdown",
        )

    # 5. ОТПРАВКА КНОПКИ ОПЛАТЫ
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Оплатить", url=payment_url))

    # Кнопка назад ведет к списку адресов (выбору продукта)
    markup.add(
        types.InlineKeyboardButton(
            "🔙 Назад (Выбрать другой адрес)", callback_data=f"product_{product_id}"
        )
    )

    bot.send_message(
        uid,
        "**Для завершения** перейдите по ссылке ниже.\n"
        "Не забудьте отправить **TxID** после оплаты!",
        parse_mode="Markdown",
        reply_markup=markup,
    )

    # Удаляем сообщение с выбором адреса
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

    bot.answer_callback_query(call.id, "Заказ создан.")


# -------------------------
# ФУНКЦИИ ВЫДАЧИ И ПРОВЕРКИ АДРЕСА (НЕЗНАЧИТЕЛЬНО ИЗМЕНЕНЫ)
# -------------------------


def give_product(user_id, order_id):
    """Отправляет пользователю фотографию тайника и текст."""
    # ... (логика выдачи)
    pass  # Заглушка


@bot.message_handler(func=lambda m: m.text == "📍 Показать адрес")
@anti_flood
def handle_show_address_button(message):
    # ... (логика показа адреса)
    pass  # Заглушка


@bot.callback_query_handler(func=lambda call: call.data.startswith("check_addr_"))
@anti_flood
def handle_show_address_callback(call):
    # ... (логика проверки статуса и выдачи адреса)
    pass  # Заглушка


@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
@anti_flood
def handle_my_orders(message):
    # ... (логика отображения заказов без кнопки продления)
    pass  # Заглушка
