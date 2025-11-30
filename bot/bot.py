# bot/bot.py
import telebot
from telebot import types
import time
from datetime import datetime, timedelta
import math
import random

from bot.config import TELEGRAM_TOKEN, ADMIN_IDS
from bot.payment import create_invoice
from bot.storage import (
    get_all_stores,
    get_products_by_store,
    get_product_details_by_id,
    add_order,
    find_orders_by_user,
    insert_product,
    delete_product,
)

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML", threaded=False)

# Глобальные переменные
user_state = {}
admin_state = {}
flood_control = {}
ADDRESSES = ["Тайник (Магнит)", "Прикоп", "Клумба"]  # Пример адресов
PRODUCTS_PER_PAGE = 5
FLOOD_LIMIT = 0.8
INITIAL_RESERVATION_HOURS = 1


# Анти-флуд
def anti_flood(func):
    def wrapper(message):
        uid = (
            message.from_user.id
            if isinstance(message, types.CallbackQuery)
            else message.chat.id
        )
        if time.time() - flood_control.get(uid, 0) < FLOOD_LIMIT:
            return
        flood_control[uid] = time.time()
        return func(message)

    return wrapper


# --- МЕНЮ ---
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🛒 Купить", "📦 Мои заказы")
    return kb


@bot.message_handler(commands=["start"])
@anti_flood
def cmd_start(message):
    bot.send_message(
        message.chat.id,
        f"👋 Привет, {message.from_user.first_name}!\nДобро пожаловать в магазин Гринча! 🎄",
        reply_markup=main_menu(),
    )


@bot.callback_query_handler(func=lambda c: c.data == "cmd_main_menu")
def back_to_main(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=main_menu())


# --- ПОКУПКА И ПАГИНАЦИЯ ---


@bot.message_handler(func=lambda m: m.text == "🛒 Купить")
@anti_flood
def handle_buy(message):
    stores = get_all_stores()
    if not stores:
        return bot.send_message(message.chat.id, "❌ Магазины пусты.")

    kb = types.InlineKeyboardMarkup()
    for s in stores:
        kb.add(
            types.InlineKeyboardButton(
                s["title"], callback_data=f"store_{s['store_id']}_0"
            )
        )

    bot.send_message(message.chat.id, "🏪 Выберите категорию:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("store_"))
def handle_store(call):
    parts = call.data.split("_")
    store_id = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0

    products = get_products_by_store(store_id)
    if not products:
        return bot.answer_callback_query(call.id, "Нет товаров!", show_alert=True)

    # Пагинация
    total_pages = math.ceil(len(products) / PRODUCTS_PER_PAGE)
    start = page * PRODUCTS_PER_PAGE
    end = start + PRODUCTS_PER_PAGE
    page_products = products[start:end]

    kb = types.InlineKeyboardMarkup()
    for p in page_products:
        kb.add(
            types.InlineKeyboardButton(
                f"{p['name']} — {p['price_usd']}$",
                callback_data=f"prod_{p['product_id']}",
            )
        )

    # Навигация
    nav = []
    if page > 0:
        nav.append(
            types.InlineKeyboardButton("⬅️", callback_data=f"store_{store_id}_{page-1}")
        )
    nav.append(
        types.InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        nav.append(
            types.InlineKeyboardButton("➡️", callback_data=f"store_{store_id}_{page+1}")
        )
    kb.row(*nav)
    kb.add(types.InlineKeyboardButton("🔙 Меню", callback_data="cmd_main_menu"))

    bot.edit_message_text(
        "📦 Выберите товар:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda c: c.data == "noop")
def noop(c):
    bot.answer_callback_query(c.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("prod_"))
def handle_prod(call):
    pid = int(call.data.split("_")[1])
    details = get_product_details_by_id(pid)
    if not details:
        return bot.answer_callback_query(call.id, "Ошибка товара")

    # Сохраняем во временное состояние
    user_state[call.from_user.id] = {"pid": pid, "details": details}

    kb = types.InlineKeyboardMarkup()
    for i, addr in enumerate(ADDRESSES):
        kb.add(types.InlineKeyboardButton(addr, callback_data=f"buy_{pid}_{i}"))
    kb.add(types.InlineKeyboardButton("🔙 Отмена", callback_data="cmd_main_menu"))

    text = f"🎁 <b>{details['product_name']}</b>\n💰 Цена: {details['price_usd']}$\n\n📍 Выберите тип клада:"
    bot.edit_message_text(
        text, call.message.chat.id, call.message.message_id, reply_markup=kb
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def handle_buy_confirm(call):
    uid = call.from_user.id
    try:
        _, pid, addr_idx = call.data.split("_")
        address = ADDRESSES[int(addr_idx)]
        pid = int(pid)
    except:
        return

    details = get_product_details_by_id(pid)

    # Генерация оплаты
    temp_oid = f"ORD-{int(time.time())}-{uid}"
    res = create_invoice(uid, details["price_usd"], temp_oid)
    if not res:
        return bot.send_message(uid, "Ошибка создания ссылки на оплату.")

    pay_url, track_id = res

    # Сохранение в БД
    real_oid = add_order(
        uid, pid, details["price_usd"], address, temp_oid, track_id, pay_url
    )

    # Отправка фото (File ID)
    caption = f"✅ <b>Заказ {real_oid} создан!</b>\nТовар забронирован.\nОплатите для получения фото и координат."

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Оплатить", url=pay_url))

    try:
        # details['file_path'] теперь содержит FILE_ID
        bot.send_photo(uid, details["file_path"], caption=caption, reply_markup=kb)
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception as e:
        bot.send_message(uid, caption + "\n(Фото недоступно)", reply_markup=kb)


# --- МОИ ЗАКАЗЫ ---
@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
def my_orders(message):
    orders = find_orders_by_user(message.chat.id)
    if not orders:
        return bot.send_message(message.chat.id, "📭 Пусто.")

    text = "📦 <b>Ваши последние 10 заказов:</b>\n\n"
    for i, (oid, data) in enumerate(orders.items()):
        if i >= 10:
            break
        icon = "✅" if data["status"] == "paid" else "⏳"
        if data["delivery_status"] == "delivered":
            icon = "🎁"
        text += f"{icon} <b>{data['product_name']}</b>\n🆔 <code>{oid}</code> | {data['price']}$\n\n"

    bot.send_message(message.chat.id, text)


# --- АДМИН ПАНЕЛЬ ---


@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Добавить товар", "❌ Удалить товар")
    kb.add("🔙 Меню")
    bot.send_message(message.chat.id, "Админка:", reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "🔙 Меню")
def exit_admin(m):
    if m.from_user.id in ADMIN_IDS:
        bot.send_message(m.chat.id, "Выход.", reply_markup=main_menu())


# Удаление
@bot.message_handler(func=lambda m: m.text == "❌ Удалить товар")
def adm_del(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    stores = get_all_stores()
    kb = types.InlineKeyboardMarkup()
    for s in stores:
        kb.add(
            types.InlineKeyboardButton(
                s["title"], callback_data=f"adel_store_{s['store_id']}"
            )
        )
    bot.send_message(m.chat.id, "Откуда удаляем?", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("adel_store_"))
def adm_del_prod_list(c):
    sid = c.data.split("_")[2]
    prods = get_products_by_store(sid)
    kb = types.InlineKeyboardMarkup()
    for p in prods:
        kb.add(
            types.InlineKeyboardButton(
                f"❌ {p['name']}", callback_data=f"adel_do_{p['product_id']}"
            )
        )
    bot.edit_message_text(
        "Жми чтоб удалить:", c.message.chat.id, c.message.message_id, reply_markup=kb
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("adel_do_"))
def adm_del_confirm(c):
    pid = c.data.split("_")[2]
    delete_product(pid)
    bot.answer_callback_query(c.id, "Удалено!")
    bot.delete_message(c.message.chat.id, c.message.message_id)


# Добавление (Wizard)
@bot.message_handler(func=lambda m: m.text == "➕ Добавить товар")
def adm_add(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    stores = get_all_stores()
    kb = types.InlineKeyboardMarkup()
    for s in stores:
        kb.add(
            types.InlineKeyboardButton(
                s["title"], callback_data=f"aadd_s_{s['store_id']}"
            )
        )
    bot.send_message(m.chat.id, "Куда добавляем?", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("aadd_s_"))
def adm_step_name(c):
    sid = c.data.split("_")[2]
    admin_state[c.from_user.id] = {"sid": sid}
    msg = bot.send_message(c.message.chat.id, "Название товара?")
    bot.register_next_step_handler(msg, step_price)


def step_price(m):
    admin_state[m.from_user.id]["name"] = m.text
    msg = bot.send_message(m.chat.id, "Цена (в USD)? (Например: 5.5)")
    bot.register_next_step_handler(msg, step_desc)


def step_desc(m):
    try:
        price = float(m.text.replace(",", "."))
        admin_state[m.from_user.id]["price"] = price
        msg = bot.send_message(m.chat.id, "Описание/Клад (этот текст получит клиент):")
        bot.register_next_step_handler(msg, step_photo)
    except:
        bot.send_message(m.chat.id, "Ошибка числа. Начни заново /admin")


def step_photo(m):
    admin_state[m.from_user.id]["desc"] = m.text
    msg = bot.send_message(m.chat.id, "Пришли ФОТО товара:")
    bot.register_next_step_handler(msg, step_finish)


def step_finish(m):
    if not m.photo:
        return bot.send_message(m.chat.id, "Это не фото!")
    # БЕРЕМ FILE ID
    fid = m.photo[-1].file_id
    data = admin_state[m.from_user.id]

    insert_product(data["sid"], data["name"], data["price"], data["desc"], fid)
    bot.send_message(m.chat.id, "✅ Товар добавлен и сохранен в БД!")
