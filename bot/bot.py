# bot/bot.py

import telebot
from telebot import types
import time
from bot.config import TELEGRAM_TOKEN
from bot.payment import create_invoice
from bot.storage import (
    update_order,
    find_orders_by_user,
    get_order,
    get_product_by_shop_key,
    add_order,
)
from bot.db import execute_query  # Для give_product

# -------------------------
# Каталог товаров (Теперь только ключи и заголовки, данные в БД)
# -------------------------
SHOPS = {
    "fruits": {"title": "🍌 Scooby-Doo — Фрукты"},
    "vegetables": {"title": "🥕 MrGrinchShopZp — Овощи"},
}

ADDRESSES = ["Бульвар Шевченко", "Ул. Победы", "Проспект Мира"]
user_state = {}

# Создаём бота
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML", threaded=False)


# -------------------------
# Клавиатуры
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


# -------------------------
# Команды и обработка текста
# -------------------------


@bot.message_handler(commands=["start"])
def cmd_start(message):
    bot.send_message(
        message.chat.id, "Добро пожаловать! Меню:", reply_markup=main_menu()
    )


@bot.message_handler(commands=["orders"])
def cmd_orders(message):
    uid = message.chat.id
    user_orders = find_orders_by_user(uid)
    if not user_orders:
        bot.send_message(uid, "У вас нет заказов.")
        return
    text = "Ваши заказы:\n\n"
    for oid, data in user_orders.items():
        text += f"• <code>{oid}</code> — {data.get('product_name', 'Товар')} — **{data.get('status')}**\n"
    bot.send_message(uid, text, parse_mode="HTML")


# -------------------------
# Обработка кнопок основного меню
# -------------------------
@bot.message_handler(func=lambda m: m.text in ["🛒 Купить", "📦 Мои заказы"])
def handle_main_menu_buttons(message):
    text = message.text
    uid = message.chat.id

    if text == "🛒 Купить":
        # Шаг 1: Выбор магазина (Inline-кнопки)
        markup = types.InlineKeyboardMarkup()
        for shop_key, shop_data in SHOPS.items():
            # data: 'shop_fruits'
            markup.add(
                types.InlineKeyboardButton(
                    shop_data["title"], callback_data=f"shop_{shop_key}"
                )
            )
        bot.send_message(uid, "Выберите магазин:", reply_markup=markup)

    elif text == "📦 Мои заказы":
        cmd_orders(message)


@bot.message_handler(func=lambda m: m.text == "🔙 Назад")
def handle_back(message):
    bot.send_message(message.chat.id, "Меню:", reply_markup=main_menu())


# -------------------------
# Шаг 2: Выбор адреса (Inline-кнопки)
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("shop_"))
def handle_shop_selection(call):
    # 🚨 РЕШЕНИЕ ТАЙМАУТА: Отвечаем немедленно
    bot.answer_callback_query(call.id, text="Загружаю адреса...", show_alert=False)

    uid = call.from_user.id

    # 1. Извлекаем ключ магазина
    shop_key = call.data.split("_")[1]
    shop = SHOPS.get(shop_key)

    if not shop:
        return bot.edit_message_text(
            chat_id=uid,
            message_id=call.message.message_id,
            text="Ошибка: Магазин не найден.",
            reply_markup=back_to_main_menu(),
        )

    # 2. Сохраняем выбранный магазин во временное состояние
    user_state[uid] = {"shop": shop_key}

    # 3. Создаем Inline-кнопки для адресов
    markup = types.InlineKeyboardMarkup()
    for addr in ADDRESSES:
        # data: 'addr_fruits_Бульвар Шевченко'
        markup.add(
            types.InlineKeyboardButton(addr, callback_data=f"addr_{shop_key}_{addr}")
        )

    # 4. Редактируем сообщение для перехода к выбору адреса
    bot.edit_message_text(
        chat_id=uid,
        message_id=call.message.message_id,
        text=f"Вы выбрали **{shop['title']}**. Теперь выберите место, где хотите забрать товар:",
        parse_mode="Markdown",
        reply_markup=markup,
    )


# -------------------------
# Шаг 3: Выбор адреса и создание инвойса
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("addr_"))
def handle_address_selection(call):
    # 🚨 РЕШЕНИЕ ТАЙМАУТА: Отвечаем немедленно (перед долгими операциями)
    bot.answer_callback_query(call.id, text="⏳ Создаю инвойс...", show_alert=False)
    uid = call.from_user.id

    # 1. Извлекаем данные
    try:
        _, shop_key, address = call.data.split("_", 2)
    except ValueError:
        return bot.send_message(uid, "Ошибка при обработке адреса.")

    # 2. ПОЛУЧЕНИЕ ДАННЫХ ТОВАРА ИЗ БД
    product_data = get_product_by_shop_key(shop_key)
    if not product_data:
        return bot.send_message(uid, "Ошибка: Товар не найден в каталоге.")

    product_id = product_data["product_id"]
    price = product_data["price_usd"]
    product_name = product_data["name"]
    shop_title = product_data["title"]

    # 3. Создаем заказ в БД и инвойс OxaPay
    order_id = add_order(uid, product_id, price)
    resp = create_invoice(
        uid, price, order_id
    )  # create_invoice должен вернуть pay_url и track_id

    if not resp or len(resp) != 2:
        update_order(order_id, status="error")
        return bot.send_message(
            uid,
            "❌ Ошибка создания платежа. Попробуйте снова.",
            reply_markup=main_menu(),
        )

    pay_url, track_id = resp

    # 4. Дополняем заказ деталями в БД
    update_order(
        order_id,
        pickup_address=address,
        status="waiting_payment",
        payment_url=pay_url,
        oxapay_track_id=track_id,
    )

    # 5. Отправляем сообщение с кнопкой оплаты (Inline-кнопка)
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
    # 6. Очищаем состояние
    user_state.pop(uid, None)


# -------------------------
# Функция выдачи (Экспортируется для server.py)
# -------------------------
def give_product(user_id, order_id):
    """
    Отправляет пользователю ФОТОГРАФИЮ МЕСТА (тайника) и текст,
    получая данные из БД.
    """
    od = get_order(order_id)
    if not od:
        return False

    if od.get("delivery_status") == "delivered":
        return True

    # 1. Получаем данные тайника из таблицы PRODUCTS
    query = "SELECT file_path, delivery_text FROM products WHERE product_id = %s;"
    product_info = execute_query(query, (od["product_id"],), fetch=True)

    if not product_info:
        print(f"ERROR: Missing delivery data for product ID {od['product_id']}")
        bot.send_message(
            user_id, "❌ Произошла ошибка. Информация о товаре не найдена."
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
