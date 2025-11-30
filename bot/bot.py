# bot/bot.py

import telebot
from telebot import types
import time
from bot.config import TELEGRAM_TOKEN
from bot.payment import create_invoice
from bot.storage import update_order, find_orders_by_user, get_order, add_order
from bot.storage import get_all_stores, get_products_by_store, get_product_details_by_id
from bot.db import execute_query

# -------------------------
# Константы и состояние
# -------------------------
ADDRESSES = ["Бульвар Шевченко", "Ул. Победы", "Проспект Мира"]
user_state = {}

# Создаём бота
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML", threaded=False)

# -------------------------
# Клавиатуры и команды
# -------------------------


def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("🛒 Купить"))
    kb.add(types.KeyboardButton("📦 Мои заказы"))
    return kb


def back_to_main_menu():
    return types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🔙 Главное меню", callback_data="cmd_main_menu")
    )


@bot.message_handler(commands=["start"])
def cmd_start(message):
    bot.send_message(
        message.chat.id, "Добро пожаловать! Меню:", reply_markup=main_menu()
    )


@bot.message_handler(func=lambda m: m.text == "🛒 Купить")
def handle_buy_button(message):
    uid = message.chat.id

    # 1. Получаем список магазинов из БД
    stores = get_all_stores()
    if not stores:
        return bot.send_message(uid, "❌ Каталог магазинов пуст.")

    # 2. Формируем кнопки
    markup = types.InlineKeyboardMarkup()
    for store in stores:
        markup.add(
            types.InlineKeyboardButton(
                store["title"], callback_data=f"store_{store['store_id']}"
            )
        )

    bot.send_message(uid, "Выберите магазин:", reply_markup=markup)


# -------------------------
# ЭТАП 2: Выбор магазина
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("store_"))
def handle_store_selection(call):
    bot.answer_callback_query(call.id, text="Загружаю товары...", show_alert=False)
    uid = call.from_user.id

    try:
        store_id = int(call.data.split("_")[1])
    except:
        return bot.send_message(uid, "Ошибка ID магазина.")

    # 1. Получаем товары из БД по store_id
    products = get_products_by_store(store_id)

    if not products:
        return bot.edit_message_text(
            chat_id=uid,
            message_id=call.message.message_id,
            text="В этом магазине пока нет товаров.",
            reply_markup=None,
        )

    # 2. Формируем кнопки с ценами
    markup = types.InlineKeyboardMarkup()
    text = "Выберите товар в этом магазине:"

    for product in products:
        button_text = f"{product['name']} ({product['price_usd']:.2f}$)"
        markup.add(
            types.InlineKeyboardButton(
                button_text, callback_data=f"product_{product['product_id']}"
            )
        )

    # 3. Редактируем сообщение для выбора товара
    bot.edit_message_text(
        chat_id=uid, message_id=call.message.message_id, text=text, reply_markup=markup
    )


# -------------------------
# ЭТАП 3: Выбор товара
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("product_"))
def handle_product_selection(call):
    bot.answer_callback_query(call.id, text="Загружаю адреса...", show_alert=False)
    uid = call.from_user.id

    try:
        product_id = int(call.data.split("_")[1])
    except:
        return bot.send_message(uid, "Ошибка ID товара.")

    # 1. Сохраняем product_id в состоянии
    user_state[uid] = {"product_id": product_id}

    # 2. Создаем Inline-кнопки для адресов
    markup = types.InlineKeyboardMarkup()
    for addr in ADDRESSES:
        markup.add(
            types.InlineKeyboardButton(addr, callback_data=f"addr_{product_id}_{addr}")
        )

    # 3. Редактируем сообщение
    bot.edit_message_text(
        chat_id=uid,
        message_id=call.message.message_id,
        text="Отлично! Выберите место, где хотите забрать товар:",
        reply_markup=markup,
    )


# -------------------------
# ЭТАП 4: Выбор адреса и создание инвойса
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("addr_"))
def handle_address_selection(call):
    bot.answer_callback_query(call.id, text="⏳ Создаю инвойс...", show_alert=False)
    uid = call.from_user.id

    # 1. Извлекаем данные (product_id и адрес)
    try:
        _, product_id_str, address = call.data.split("_", 2)
        product_id = int(product_id_str)
    except ValueError:
        return bot.send_message(uid, "Ошибка при обработке адреса.")

    # 2. ПОЛУЧЕНИЕ ДЕТАЛЕЙ ТОВАРА ИЗ БД
    details = get_product_details_by_id(product_id)
    if not details:
        return bot.send_message(uid, "Ошибка: Товар не найден в каталоге.")

    price = details["price_usd"]
    product_name = details["product_name"]
    shop_title = details["shop_title"]

    # 3. Создаем заказ в БД
    order_id = add_order(uid, product_id, price)

    # 4. Создаем инвойс OxaPay
    resp = create_invoice(uid, price, order_id)

    if not resp or len(resp) != 2:
        update_order(order_id, status="error")
        return bot.send_message(
            uid,
            "❌ Ошибка создания платежа. Попробуйте снова.",
            reply_markup=main_menu(),
        )

    pay_url, track_id = resp

    # 5. Дополняем заказ деталями в БД
    update_order(
        order_id,
        pickup_address=address,
        status="waiting_payment",
        payment_url=pay_url,
        oxapay_track_id=track_id,
    )

    # 6. Отправляем сообщение с кнопкой оплаты
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Оплатить", url=pay_url))

    bot.edit_message_text(
        chat_id=uid,
        message_id=call.message.message_id,
        text=(
            f"✅ **Заказ `{order_id}` создан!**\n\n"
            f"Магазин: {shop_title}\n"
            f"Товар: {product_name}\n"
            f"Адрес получения: *{address}*\n"
            f"Цена: **{price:.2f}$**\n\n"
            "Нажмите кнопку для оплаты. **Фото с местом выдачи придет автоматически после подтверждения оплаты!**"
        ),
        parse_mode="Markdown",
        reply_markup=markup,
    )
    # 7. Очищаем состояние
    user_state.pop(uid, None)


# -------------------------
# ЭТАП 6: Функция выдачи (give_product)
# -------------------------
def give_product(user_id, order_id):
    """Отправляет пользователю фотографию тайника и текст."""
    od = get_order(order_id)
    if not od or od.get("delivery_status") == "delivered":
        return True

    # 1. Получаем данные тайника из таблицы PRODUCTS
    query = "SELECT file_path, delivery_text FROM products WHERE product_id = %s;"
    product_info = execute_query(query, (od["product_id"],), fetch=True)

    if not product_info:
        bot.send_message(
            user_id, "❌ Произошла ошибка. Информация о тайнике не найдена."
        )
        return False

    file_path, delivery_text = product_info[0]

    try:
        # 2. Отправляем фото и текст тайника
        bot.send_message(
            user_id,
            "✅ **Оплата получена!** Вот ваше место выдачи:",
            parse_mode="Markdown",
        )

        with open(file_path, "rb") as f:
            bot.send_photo(
                user_id,
                f,
                caption=f"**Ваш тайник:**\n\n{delivery_text}",
                parse_mode="Markdown",
            )

        # 3. Обновляем статус
        update_order(order_id, delivery_status="delivered")
        return True
    except Exception as e:
        print(f"Error giving product for order {order_id}: {e}")
        return False


# -------------------------
# Хендлер "Мои заказы" (добавлен для полноты)
# -------------------------


@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
def handle_my_orders(message):
    uid = message.chat.id
    orders = find_orders_by_user(uid)

    if not orders:
        return bot.send_message(uid, "У вас пока нет активных заказов.")

    text = "История ваших заказов:\n"
    for order_id, data in orders.items():
        # Преобразуем статус из БД в читаемый вид
        status_display = {
            "pending": "⏳ Ожидает оплаты",
            "waiting_payment": "⏳ Ожидает оплаты",
            "paid": "✅ Оплачен",
            "delivered": "📦 Выдан",
            "error": "❌ Ошибка",
        }.get(data["status"], data["status"])

        text += (
            f"\n`{order_id}`\n"
            f"  Товар: {data['product_name']}\n"
            f"  Цена: {data['price']:.2f}$\n"
            f"  Статус: **{status_display}**"
        )   

    bot.send_message(uid, text, parse_mode="Markdown")
