import telebot
from telebot import types
from bot.config import TELEGRAM_TOKEN
from bot.payment import create_invoice
from bot.storage import orders, update_order, find_orders_by_user, get_order

# Создаём бота
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML", threaded=False)

# -------------------------
# Товары
# -------------------------
SHOPS = {
    "fruits": {
        "title": "🍌 Scooby-Doo — Фрукты",
        "product": {
            "name": "Набор фруктов",
            "file": "bot/images/fruits.jpg", # Убедитесь, что этот файл существует!
            "price": 5,
            "delivery_text": "📍 Тайник у фонтана, смотри под скамейкой."
        },
    },
    "vegetables": {
        "title": "🥕 MrGrinchShopZp — Овощи",
        "product": {
            "name": "Набор овощей",
            "file": "bot/images/vegs.jpg", # Убедитесь, что этот файл существует!
            "price": 7,
            "delivery_text": "📍 Тайник у столба, синий мешок."
        },
    },
}

ADDRESSES = ["Бульвар Шевченко", "Ул. Победы", "Проспект Мира"]
user_state = {}

# -------------------------
# Клавиатуры
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
# Команды
# -------------------------
@bot.message_handler(commands=["start"])
def cmd_start(message):
    bot.send_message(message.chat.id, "Добро пожаловать! Меню:", reply_markup=main_menu())

@bot.message_handler(commands=["buy"])
def cmd_buy(message):
    bot.send_message(message.chat.id, "Выберите магазин:", reply_markup=shop_menu())

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
    bot.send_message(uid, text)

@bot.message_handler(commands=["check"])
def cmd_check(message):
    uid = message.chat.id
    user_orders = find_orders_by_user(uid)
    if not user_orders:
        bot.send_message(uid, "У вас нет активных заказов.")
        return
    
    found_paid = False
    for oid, d in user_orders.items():
        if d.get("status") == "paid" and d.get("delivery_status") != "delivered":
            # Выдаем товар
            give_product(d["user_id"], oid)
            found_paid = True
        elif d.get("status") == "paid" and d.get("delivery_status") == "delivered":
             bot.send_message(uid, f"Заказ #{oid} уже выдан.")
        else:
            bot.send_message(uid, f"Статус заказа #{oid}: {d.get('status')}")
    
    if found_paid:
        bot.send_message(uid, "Все оплаченные заказы выданы!")

# -------------------------
# Обработка текста
# -------------------------
@bot.message_handler(func=lambda m: True)
def handle_buttons(message):
    text = message.text
    uid = message.chat.id

    if text == "🛒 Купить":
        bot.send_message(uid, "Выберите магазин:", reply_markup=shop_menu())
        return

    if text == "📦 Мои заказы":
        cmd_orders(message)
        return

    if text == "🔙 Назад":
        bot.send_message(uid, "Меню:", reply_markup=main_menu())
        return

    # Выбор магазина
    if text == SHOPS["fruits"]["title"]:
        user_state[uid] = {"shop": "fruits"}
        bot.send_message(uid, "Вы выбрали Scooby-Doo (фрукты). Выберите адрес:", reply_markup=address_menu())
        return

    if text == SHOPS["vegetables"]["title"]:
        user_state[uid] = {"shop": "vegetables"}
        bot.send_message(uid, "Вы выбрали MrGrinchShopZp (овощи). Выберите адрес:", reply_markup=address_menu())
        return

    # Выбор адреса
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

        bot.send_message(uid, "⏳ Создаю счет на оплату...")

        resp = create_invoice(uid, price, file_path)
        if not resp:
            bot.send_message(uid, "❌ Ошибка создания платежа. Проверьте консоль сервера.")
            return

        order_id, pay_url = resp

        # Дополняем заказ деталями
        update_order(order_id, shop=shop_key, product_name=product_name, address=text)

        bot.send_message(
            uid,
            f"✅ <b>Заказ #{order_id} создан!</b>\n\n"
            f"Магазин: {shop['title']}\n"
            f"Товар: {product_name}\n"
            f"Адрес: {text}\n"
            f"Цена: <b>{price}$</b>\n\n"
            f"💳 <a href='{pay_url}'>Нажмите сюда для оплаты</a>\n\n"
            f"После оплаты товар придёт автоматически.",
            reply_markup=main_menu()
        )
        user_state.pop(uid, None)
        return

    bot.send_message(uid, "Неизвестная команда.", reply_markup=main_menu())

# -------------------------
# Функция выдачи (Экспортируется для server.py)
# -------------------------
def give_product(user_id, order_id):
    """
    Отправляет товар пользователю и меняет статус на delivered.
    """
    od = get_order(order_id)
    if not od:
        return False
    
    # Защита от повторной выдачи
    if od.get("delivery_status") == "delivered":
        return True

    delivery_text = od.get("delivery_text") # Это нужно добавить в update_order при создании, или брать из SHOPS сейчас
    
    # Так как delivery_text статический в SHOPS, лучше найдем его снова
    # (Или лучше сохранять его в orders при создании. Давайте возьмем из order если есть, или найдем)
    if not delivery_text:
        # Попытка восстановить из SHOPS
        shop_key = od.get("shop")
        if shop_key and shop_key in SHOPS:
            delivery_text = SHOPS[shop_key]["product"]["delivery_text"]
    
    file_path = od.get("file")

    try:
        bot.send_message(user_id, "✅ <b>Оплата получена!</b> Держите ваш заказ:", parse_mode="HTML")
        
        if delivery_text:
            bot.send_message(user_id, delivery_text)
        
        if file_path:
            with open(file_path, "rb") as f:
                bot.send_photo(user_id, f)
        
        # Обновляем статус
        update_order(order_id, delivery_status="delivered")
        return True
    except Exception as e:
        print(f"Error giving product: {e}")
        return False