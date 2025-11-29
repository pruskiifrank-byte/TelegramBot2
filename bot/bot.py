# bot/bot.py
import telebot
from telebot import types
from bot.config import TELEGRAM_TOKEN
from bot.payment import create_invoice
from bot.storage import orders, add_order, update_order, find_orders_by_user, get_order

# создаём бота (экпортируемая переменная)
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML", threaded=False)

# -------------------------
# данные товаров (по магазину)
# -------------------------
# каждый магазин содержит словарь товаров — пока по одному товару, можно расширить
SHOPS = {
    "fruits": {
        "title": "🍌 Scooby-Doo — Фрукты",
        "product_key": "fruit_1",
        "product": {
            "name": "Набор фруктов",
            "file": "bot/images/fruits.jpg",      # путь относительно проекта
            "price": 5,
            "delivery_text": "📍 Тайник у фонтана, смотри под скамейкой."
        },
    },
    "vegetables": {
        "title": "🥕 MrGrinchShopZp — Овощи",
        "product_key": "veg_1",
        "product": {
            "name": "Набор овощей",
            "file": "bot/images/vegs.jpg",
            "price": 7,
            "delivery_text": "📍 Тайник у столба, синий мешок."
        },
    },
}

ADDRESSES = ["Бульвар Шевченко", "Ул. Победы", "Проспект Мира"]

# временное состояние пользователей (в памяти)
user_state = {}

# -------------------------
# клавиатуры
# -------------------------
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("🛒 Купить"))
    kb.add(types.KeyboardButton("📦 Мои заказы"))
    return kb

def shop_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton(SHOPS["fruits"]["title"]))
    kb.add(types.KeyboardButton(SHOPS["vegetables"]["title"]))
    kb.add(types.KeyboardButton("🔙 Назад"))
    return kb

def address_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for addr in ADDRESSES:
        kb.add(types.KeyboardButton(addr))
    kb.add(types.KeyboardButton("🔙 Назад"))
    return kb

# -------------------------
# утилиты
# -------------------------
def send_temp_message(chat_id, text, reply_markup=None):
    msg = bot.send_message(chat_id, text, reply_markup=reply_markup)
    return msg

# -------------------------
# команда /start
# -------------------------
@bot.message_handler(commands=["start"])
def cmd_start(message):
    bot.send_message(message.chat.id, "Добро пожаловать! Меню:", reply_markup=main_menu())

# -------------------------
# команда /buy
# -------------------------
@bot.message_handler(commands=["buy"])
def cmd_buy(message):
    bot.send_message(message.chat.id, "Выберите магазин:", reply_markup=shop_menu())

# -------------------------
# команда /orders (показывает активные заказы)
# -------------------------
@bot.message_handler(commands=["orders"])
def cmd_orders(message):
    uid = message.chat.id
    user_orders = find_orders_by_user(uid)
    if not user_orders:
        bot.send_message(uid, "У вас нет заказов.")
        return
    text = "Ваши заказы:\n\n"
    for oid, data in user_orders.items():
        text += f"• #{oid} — {data.get('product_name')} — статус: {data.get('status')}\n"
    bot.send_message(uid, text)

# -------------------------
# check (как раньше) — проверяет и выдаёт, если paid
# -------------------------
@bot.message_handler(commands=["check"])
def cmd_check(message):
    uid = message.chat.id
    user_orders = find_orders_by_user(uid)
    if not user_orders:
        bot.send_message(uid, "У вас нет активных заказов.")
        return
    for oid, d in user_orders.items():
        if d.get("status") == "paid":
            # выдаём товар и помечаем delivered
            give_product(d["user_id"], oid)
            update_order(oid, status="delivered")
            bot.send_message(uid, "Спасибо за покупку!")
            return
        else:
            bot.send_message(uid, f"Статус заказа #{oid}: {d.get('status')}")
            return

# -------------------------
# Обработка текстовых кнопок (магазины, адреса)
# -------------------------
@bot.message_handler(func=lambda m: True)
def handle_buttons(message):
    text = message.text
    uid = message.chat.id

    # главное меню
    if text == "🛒 Купить":
        bot.send_message(uid, "Выберите магазин:", reply_markup=shop_menu())
        return

    if text == "📦 Мои заказы":
        cmd_orders(message)
        return

    if text == "🔙 Назад":
        bot.send_message(uid, "Меню:", reply_markup=main_menu())
        return

    # выбор магазина
    if text == SHOPS["fruits"]["title"]:
        user_state[uid] = {"shop": "fruits"}
        bot.send_message(uid, "Вы выбрали Scooby-Doo (фрукты). Выберите адрес:", reply_markup=address_menu())
        return

    if text == SHOPS["vegetables"]["title"]:
        user_state[uid] = {"shop": "vegetables"}
        bot.send_message(uid, "Вы выбрали MrGrinchShopZp (овощи). Выберите адрес:", reply_markup=address_menu())
        return

    # выбор адреса — создаём заказ и инвойс
    if text in ADDRESSES:
        if uid not in user_state or "shop" not in user_state[uid]:
            bot.send_message(uid, "Сначала выберите магазин (/buy).")
            return

        shop_key = user_state[uid]["shop"]
        shop = SHOPS[shop_key]
        product = shop["product"]
        price = product["price"]
        file_path = product["file"]
        product_name = product["name"]

        # создаём инвойс через OxaPay (модуль payment_oxapay.create_invoice)
        resp = create_invoice(uid, price, file_path)
        if not resp:
            bot.send_message(uid, "Ошибка создания платежа. Попробуйте позже.")
            return

        order_id, pay_url = resp

        # обновляем хранилище (create_invoice уже сохраняет в storage.orders)
        update_order(order_id, shop=shop_key, product_name=product_name, address=text, price=price)

        # отправляем пользователю информацию и ссылку
        bot.send_message(
            uid,
            f"✅ Заказ #{order_id} создан!\n\n"
            f"Магазин: {shop['title']}\n"
            f"Товар: {product_name}\n"
            f"Адрес: {text}\n"
            f"Цена: {price}$\n\n"
            f"💳 Оплатите по ссылке: {pay_url}\n\n"
            f"После оплаты OxaPay пришлёт уведомление — заказ автоматически подтвердится, либо нажмите /check"
        )
        # очищаем состояние
        user_state.pop(uid, None)
        return

    # fallback — нераспознанный текст
    # можно оставить для теста
    bot.send_message(uid, "Неизвестная команда. Используйте главное меню.", reply_markup=main_menu())

# -------------------------
# Выдача товара (используется при paid)
# -------------------------
def give_product(chat_id: int, order_id: str):
    """
    Оправляет товар по заказу order_id; order must be in storage.orders
    """
    od = get_order(order_id)
    if not od:
        try:
            bot.send_message(chat_id, "Ошибка: заказ не найден.")
        except:
            pass
        return

    # отправляем delivery text + photo (если есть)
    delivery_text = od.get("delivery_text")
    file_path = od.get("file")

    if delivery_text:
        try:
            bot.send_message(chat_id, delivery_text)
        except:
            pass

    if file_path:
        try:
            with open(file_path, "rb") as f:
                bot.send_photo(chat_id, f)
        except:
            pass

# -------------------------
# process_update (для Flask)
# -------------------------
def process_update(update_json):
    try:
        update = telebot.types.Update.de_json(update_json)
        bot.process_new_updates([update])
    except Exception:
        pass
