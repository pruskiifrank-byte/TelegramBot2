# bot/bot.py

import telebot
from telebot import types
import time
from datetime import datetime, timedelta
import random
import math
import os  # Для работы с файловой системой при сохранении фото

# -------------------------------------------------------------
# ЗАГЛУШКИ ДЛЯ ТЕСТИРОВАНИЯ (Замените на ваши реальные импорты и функции)
# -------------------------------------------------------------
TELEGRAM_TOKEN = "ВАШ_ТОКЕН_БОТА"
ADMIN_IDS = [123456789, 987654321]  # <-- ЗАМЕНИТЕ НА ВАШИ РЕАЛЬНЫЕ TELEGRAM ID


def update_order(*args, **kwargs):
    pass


def find_orders_by_user(uid):
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
    return 104


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
        "file_path": "images/example.jpg",
    }


def execute_query(query, params=None):
    return None


# -------------------------------------------------------------

# -------------------------
# Константы и Состояние
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
INITIAL_RESERVATION_HOURS = 1

# Максимальное количество неоплаченных заказов
MAX_UNPAID_ORDERS = 3

# ТЕМАТИЧЕСКИЕ ШУТКИ ГРИНЧА
grinch_jokes = [
    "😈 Гринч ворчит: «Опять ты… ну ладно, выбирай!»",
    "🎁 Гринч шепчет: «Это не подарок… это стратегическая пакость!»",
    "💚 «Не переживай, я почти добрый сегодня!»",
    "👀 «Если что-то пойдёт не так — это не я!»",
]

# СТЕЙТЫ АДМИН ПАНЕЛИ
ADMIN_STATES = {
    "A_START": 1,
    "A_NAME": 2,
    "A_PRICE": 3,
    "A_DESC": 4,
    "A_PHOTO": 5,
    "A_STORE": 6,
    "A_CONFIRM": 7,
}

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


def admin_menu():
    """Клавиатура для администратора."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("➕ Добавить товар"))
    kb.add(types.KeyboardButton("🚪 Выйти из Admin"))
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
# ОБЩИЕ КОМАНДЫ (СТАРТ, МЕНЮ)
# -------------------------


@bot.message_handler(commands=["start"])
@anti_flood
def cmd_start(message):
    uid = message.chat.id
    user_name = message.from_user.first_name or "Гость"

    welcome_text = (
        f"🎄 Привет, {user_name}! 🎁\n"
        "Добро пожаловать к Гринчу!\n"
        "💰 Оплата — Global24 (P2P)\n"
        "После оплаты нужно отправить txID\n"
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


# -------------------------
# АДМИН ПАНЕЛЬ
# -------------------------


@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    uid = message.chat.id
    if uid not in ADMIN_IDS:
        return bot.send_message(uid, "🚫 Доступ запрещен.")

    user_state[uid] = {"mode": "admin"}
    bot.send_message(
        uid,
        "🔑 **Вы вошли в режим Администратора.**\n\nВыберите действие:",
        reply_markup=admin_menu(),
        parse_mode="Markdown",
    )


@bot.message_handler(func=lambda m: m.text == "🚪 Выйти из Admin")
def handle_exit_admin(message):
    uid = message.chat.id
    if user_state.get(uid, {}).get("mode") == "admin":
        user_state[uid] = {}
        bot.send_message(
            uid, "👋 Вы вышли из режима Администратора.", reply_markup=main_menu()
        )
    else:
        bot.send_message(
            uid, "Вы не были в режиме Администратора.", reply_markup=main_menu()
        )


@bot.message_handler(func=lambda m: m.text == "➕ Добавить товар")
def handle_add_product_start(message):
    uid = message.chat.id
    if uid not in ADMIN_IDS:
        return

    user_state[uid] = {
        "mode": "admin",
        "sub_mode": "add_product",
        "step": ADMIN_STATES["A_NAME"],
        "data": {},
    }

    bot.send_message(
        uid,
        "Начнем добавление товара. **Введите название товара** (например, Шишка 1г):",
    )


# Хендлер ввода имени
@bot.message_handler(
    func=lambda m: user_state.get(m.chat.id, {}).get("sub_mode") == "add_product"
    and user_state.get(m.chat.id, {}).get("step") == ADMIN_STATES["A_NAME"]
)
def handle_add_product_name(message):
    uid = message.chat.id
    user_state[uid]["data"]["name"] = message.text
    user_state[uid]["step"] = ADMIN_STATES["A_PRICE"]
    bot.send_message(
        uid, "Теперь **введите цену товара в долларах США** (например, 50.00):"
    )


# Хендлер ввода цены
@bot.message_handler(
    func=lambda m: user_state.get(m.chat.id, {}).get("sub_mode") == "add_product"
    and user_state.get(m.chat.id, {}).get("step") == ADMIN_STATES["A_PRICE"]
)
def handle_add_product_price(message):
    uid = message.chat.id
    try:
        price = float(message.text)
        if price <= 0:
            raise ValueError
    except ValueError:
        return bot.send_message(
            uid, "❌ Некорректный формат цены. Введите число (например, 75.50):"
        )

    user_state[uid]["data"]["price"] = price
    user_state[uid]["step"] = ADMIN_STATES["A_DESC"]
    bot.send_message(
        uid, "✅ Цена сохранена. Теперь **введите полное описание товара**:"
    )


# Хендлер ввода описания
@bot.message_handler(
    func=lambda m: user_state.get(m.chat.id, {}).get("sub_mode") == "add_product"
    and user_state.get(m.chat.id, {}).get("step") == ADMIN_STATES["A_DESC"]
)
def handle_add_product_desc(message):
    uid = message.chat.id
    user_state[uid]["data"]["description"] = message.text
    user_state[uid]["step"] = ADMIN_STATES["A_PHOTO"]
    bot.send_message(
        uid,
        "🖼️ Описание сохранено. Теперь **отправьте фотографию товара (как ФАЙЛ, не сжимая)**:",
    )


# Хендлер загрузки фото
@bot.message_handler(
    content_types=["photo", "document"],
    func=lambda m: user_state.get(m.chat.id, {}).get("sub_mode") == "add_product"
    and user_state.get(m.chat.id, {}).get("step") == ADMIN_STATES["A_PHOTO"],
)
def handle_add_product_photo(message):
    uid = message.chat.id

    # 1. Получаем file_id
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and "image" in message.document.mime_type:
        file_id = message.document.file_id
    else:
        return bot.send_message(
            uid, "❌ Пожалуйста, отправьте именно фотографию или изображение."
        )

    # 2. Получаем ссылку на файл
    file_info = bot.get_file(file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    # 3. Сохраняем файл на сервере
    filename = f"product_photos/prod_{int(time.time())}_{uid}.jpg"

    # Создаем папку, если ее нет
    os.makedirs("product_photos", exist_ok=True)

    try:
        with open(filename, "wb") as new_file:
            new_file.write(downloaded_file)
    except Exception as e:
        print(f"Ошибка сохранения файла: {e}")
        return bot.send_message(
            uid, "❌ Ошибка сохранения фото на сервере. Попробуйте снова."
        )

    user_state[uid]["data"]["file_path"] = filename
    user_state[uid]["step"] = ADMIN_STATES["A_STORE"]

    # 4. Выбор магазина (Store ID)
    stores = get_all_stores()
    if not stores:
        return bot.send_message(
            uid, "❌ Магазины не найдены! Создание товара невозможно."
        )

    markup = types.InlineKeyboardMarkup()
    for store in stores:
        markup.add(
            types.InlineKeyboardButton(
                store["title"], callback_data=f"admin_store_{store['store_id']}"
            )
        )

    bot.send_message(
        uid, "📸 Фото сохранено. Теперь **выберите магазин**:", reply_markup=markup
    )


# Хендлер выбора магазина и подтверждения
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_store_"))
def handle_add_product_store_select(call):
    uid = call.from_user.id
    store_id = int(call.data.split("_")[2])

    if (
        user_state.get(uid, {}).get("sub_mode") != "add_product"
        or user_state[uid]["step"] != ADMIN_STATES["A_STORE"]
    ):
        return bot.send_message(
            uid, "❌ Ошибка состояния. Начните добавление товара снова."
        )

    user_state[uid]["data"]["store_id"] = store_id
    user_state[uid]["step"] = ADMIN_STATES["A_CONFIRM"]

    # 5. Подтверждение итоговых данных
    data = user_state[uid]["data"]
    confirm_text = (
        "🔍 **Проверьте данные перед сохранением:**\n"
        f"**Название:** {data['name']}\n"
        f"**Цена:** {data['price']:.2f} $\n"
        f"**Описание:** {data['description'][:100]}...\n"
        f"**Путь к фото:** {data['file_path']}\n"
        f"**ID Магазина:** {data['store_id']}"
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            "✅ СОХРАНИТЬ в БД", callback_data="admin_save_product"
        )
    )

    bot.edit_message_text(
        confirm_text,
        uid,
        call.message.message_id,
        reply_markup=markup,
        parse_mode="Markdown",
    )
    bot.answer_callback_query(call.id)


# Хендлер сохранения в БД
@bot.callback_query_handler(func=lambda call: call.data == "admin_save_product")
def handle_add_product_save(call):
    uid = call.from_user.id
    data = user_state.get(uid, {}).get("data")

    if not data or user_state.get(uid, {}).get("sub_mode") != "add_product":
        return bot.edit_message_text(
            "❌ Ошибка. Данные для сохранения не найдены.",
            uid,
            call.message.message_id,
            reply_markup=admin_menu(),
        )

    try:
        query = """
            INSERT INTO products (name, price, description, file_path, store_id)
            VALUES (%s, %s, %s, %s, %s);
        """
        execute_query(
            query,
            (
                data["name"],
                data["price"],
                data["description"],
                data["file_path"],
                data["store_id"],
            ),
        )

        user_state[uid] = {"mode": "admin"}

        bot.edit_message_text(
            f"🎉 **Товар '{data['name']}' успешно добавлен в базу данных!**",
            uid,
            call.message.message_id,
            reply_markup=admin_menu(),
            parse_mode="Markdown",
        )
    except Exception as e:
        user_state[uid] = {"mode": "admin"}
        bot.edit_message_text(
            f"❌ **Критическая ошибка при сохранении в БД:** {e}",
            uid,
            call.message.message_id,
            reply_markup=admin_menu(),
            parse_mode="Markdown",
        )
    bot.answer_callback_query(call.id)


# -------------------------
# ЭТАПЫ ПОКУПКИ
# -------------------------


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
        types.InlineKeyboardButton(address, callback_data=f"addr_{product_id}_{i}")
        for i, address in enumerate(ADDRESSES)
    ]

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

    # 1. ПРОВЕРКА ЛИМИТА (3 неоплаченных заказа)
    orders = find_orders_by_user(uid)
    unpaid_count = 0
    now = datetime.now()

    if orders:
        for order_id, data in orders.items():
            if data.get("status") == "waiting_payment":
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
            f"❌ **Лимит неоплаченных заказов ({MAX_UNPAID_ORDERS}) достигнут.**\n\n",
            parse_mode="Markdown",
            reply_markup=back_to_main_menu_inline(),
        )
        return

    # 2. ПОЛУЧЕНИЕ ДАННЫХ
    try:
        _, product_id, address_index = call.data.split("_")
        product_id = int(product_id)
        selected_address = ADDRESSES[int(address_index)]
    except (IndexError, ValueError):
        return bot.send_message(uid, "❌ Ошибка выбора товара/адреса.")

    product_details = get_product_details_by_id(product_id)
    if not product_details:
        return bot.send_message(uid, "❌ Ошибка: товар не найден.")

    price = product_details.get("price", 0)
    product_name = product_details.get("name", "Товар")
    file_path = product_details.get("file_path", "images/placeholder.jpg")
    product_description = product_details.get(
        "description", "Описание не предоставлено."
    )

    # 3. БРОНИРОВАНИЕ (1 час) И СОЗДАНИЕ ИНВОЙСА
    reservation_expires_at = datetime.now() + timedelta(hours=INITIAL_RESERVATION_HOURS)
    payment_url = "https://oxapay.io/pay"

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

    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

    bot.answer_callback_query(call.id, "Заказ создан.")


# -------------------------
# СТАТУСЫ И АДРЕСА (ЗАГЛУШКИ)
# -------------------------


@bot.message_handler(func=lambda m: m.text == "📍 Показать адрес")
@anti_flood
def handle_show_address_button(message):
    bot.send_message(
        message.chat.id, "Функция показа адреса не реализована в этой версии."
    )


@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
@anti_flood
def handle_my_orders(message):
    uid = message.chat.id
    orders = find_orders_by_user(uid)

    if not orders:
        return bot.send_message(uid, "У вас нет активных или завершенных заказов.")

    now = datetime.now()

    for order_id, data in orders.items():
        text = f"**Заказ №{order_id}**\n"
        text += f"Товар: {data.get('product_name', 'N/A')}\n"
        text += f"Цена: {data.get('price', 0):.2f} $\n"

        markup = types.InlineKeyboardMarkup()

        if data["status"] == "waiting_payment":
            if data.get("reservation_expires_at"):
                expiry_dt = datetime.fromtimestamp(data["reservation_expires_at"])

                if expiry_dt > now:
                    remaining_time = expiry_dt - now
                    text += f"Статус: ⏳ **Ожидает оплаты**\n"
                    text += (
                        f"Бронь истекает через: {str(remaining_time).split('.')[0]}\n"
                    )
                else:
                    text += f"Статус: ❌ **Бронь истекла!**\n"
                    text += "Для оплаты нужно создать новый заказ."

            if data.get("payment_url") and expiry_dt > now:
                markup.add(
                    types.InlineKeyboardButton(
                        "💳 Перейти к оплате", url=data["payment_url"]
                    )
                )

        elif data["status"] == "paid":
            text += f"Статус: ✅ **Оплачен**\n"
            text += f"Готов к выдаче."

        elif data["status"] == "canceled":
            text += f"Статус: ❌ Отменен\n"

        bot.send_message(uid, text, reply_markup=markup, parse_mode="Markdown")


# Запуск бота
if __name__ == "__main__":
    print("Бот запущен...")
    bot.polling(none_stop=True)
