# bot.py (ОБНОВЛЕННАЯ ВЕРСИЯ)

import telebot
from telebot import types
import time
from bot.config import TELEGRAM_TOKEN

# Внимание: предполагается, что create_invoice теперь создает и сохраняет order_id внутри
from bot.payment import create_invoice

# Внимание: предполагается, что update_order, get_order, find_orders_by_user работают
from bot.storage import update_order, find_orders_by_user, get_order

# -------------------------
# Каталог товаров и мест выдачи
# -------------------------
SHOPS = {
    "fruits": {
        "title": "🍌 Scooby-Doo — Фрукты",
        "product": {
            "name": "Набор фруктов",
            "file": "bot/images/fruits.jpg",  # Фотография тайника
            "price": 5.00,  # Цена в USD
            "delivery_text": "📍 Тайник у фонтана, смотри под скамейкой. Код: FRUITS1.",
        },
    },
    "vegetables": {
        "title": "🥕 MrGrinchShopZp — Овощи",
        "product": {
            "name": "Набор овощей",
            "file": "bot/images/vegs.jpg",  # Фотография тайника
            "price": 7.00,
            "delivery_text": "📍 Тайник у столба, синий мешок. Код: VEGS2.",
        },
    },
}

ADDRESSES = ["Бульвар Шевченко", "Ул. Победы", "Проспект Мира"]
user_state = {}  # Используется для временного хранения выбранного магазина
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
        text += f"• <code>{oid}</code> — {data.get('product_name', 'Товар')} — {data.get('status')}\n"
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


# -------------------------
# Шаг 2: Выбор адреса (Inline-кнопки)
# -------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("shop_"))
def handle_shop_selection(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id

    # 1. Извлекаем ключ магазина (shop_fruits -> fruits)
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
    bot.answer_callback_query(call.id, text="⏳ Создаю инвойс...")

    uid = call.from_user.id

    # 1. Извлекаем данные: 'addr_fruits_Бульвар Шевченко'
    try:
        _, shop_key, address = call.data.split("_", 2)
    except ValueError:
        return bot.send_message(uid, "Ошибка при обработке адреса.")

    shop = SHOPS.get(shop_key)
    if not shop:
        return bot.send_message(uid, "Ошибка: Магазин не найден.")

    product = shop["product"]
    price = product["price"]
    product_name = product["name"]

    # 2. Создаем инвойс (и заказ)
    # create_invoice должен вернуть (order_id, pay_url) и сохранить детали в storage.py
    resp = create_invoice(
        uid, price, product_name
    )  # Предполагаем, что create_invoice теперь принимает product_name, а не file_path
    if not resp:
        return bot.send_message(
            uid, "❌ Ошибка создания платежа.", reply_markup=main_menu()
        )

    order_id, pay_url = resp

    # 3. Дополняем заказ деталями
    # file - это фото тайника, которое должно быть сохранено в заказе для последующей выдачи
    update_order(
        order_id,
        shop=shop_key,
        product_name=product_name,
        address=address,
        file=product["file"],  # Сохраняем путь к фото тайника
        delivery_text=product["delivery_text"],  # Сохраняем текст тайника
    )

    # 4. Отправляем сообщение с кнопкой оплаты (Inline-кнопка)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Оплатить", url=pay_url))

    bot.edit_message_text(
        chat_id=uid,
        message_id=call.message.message_id,
        text=(
            f"✅ **Заказ #{order_id} создан!**\n\n"
            f"Магазин: {shop['title']}\n"
            f"Товар: {product_name}\n"
            f"Адрес получения: *{address}*\n"
            f"Цена: **{price:.2f}$**\n\n"
            "Нажмите кнопку для оплаты. **Фото с местом выдачи придет автоматически после подтверждения оплаты!**"
        ),
        parse_mode="Markdown",
        reply_markup=markup,
    )
    # 5. Очищаем состояние
    user_state.pop(uid, None)


# -------------------------
# Функция выдачи (Экспортируется для server.py)
# -------------------------
def give_product(user_id, order_id):
    """
    Отправляет пользователю ФОТОГРАФИЮ МЕСТА (тайника) и текст.
    Вызывается из server.py после получения IPN со статусом 'paid'.
    """
    od = get_order(order_id)
    if not od:
        return False

    # Защита от повторной выдачи
    if od.get("delivery_status") == "delivered":
        return True

    delivery_text = od.get("delivery_text")
    file_path = od.get("file")  # Путь к фото тайника

    if not delivery_text or not file_path:
        # Этого не должно случиться, если update_order работает правильно
        print(f"ERROR: Missing delivery data for order {order_id}")
        bot.send_message(
            user_id, "❌ Произошла ошибка при выдаче. Свяжитесь с поддержкой."
        )
        return False

    try:
        # 1. Отправляем сообщение о получении оплаты
        bot.send_message(
            user_id,
            "✅ **Оплата получена!** Вот ваше место выдачи:",
            parse_mode="Markdown",
        )

        # 2. Отправляем ФОТОГРАФИЮ ТАЙНИКА и текст
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
