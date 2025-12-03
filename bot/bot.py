# bot/bot.py
import telebot
from telebot import types
from telebot.types import InputMediaPhoto
import time
import math
import csv
import io
import zipfile
import random
from datetime import datetime
from bot.config import TELEGRAM_TOKEN, ADMIN_IDS, SUPPORT_LINK, REVIEWS_LINK, NEWS_LINK
from bot.payment import create_invoice, verify_payment_via_api
from bot.storage import (
    get_all_stores,
    get_products_by_store,
    get_product_details_by_id,
    add_order,
    find_orders_by_user,
    insert_product,
    delete_product,
    upsert_user,
    get_all_users,
    update_product_field,
    get_order,
    mark_product_as_sold,
    update_order,
    cancel_order_db,
    get_unique_products_by_store,
    get_districts_for_product,
    get_fresh_product_id,
    get_table_data,
    get_store_id_by_title,
)

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML", threaded=False)

# Состояния
user_state = {}
admin_state = {}
flood_control = {}

PRODUCTS_PER_PAGE = 5
FLOOD_LIMIT = 0.5
MAX_UNPAID_ORDERS = 1

GRINCH_JOKES = [
    "💚 «Не переживай, я почти добрый сегодня!»",
    "👀 «Если что-то пойдёт не так — это не я!»",
    "🎁 Гринч шепчет: «Это не подарок… это стратегическая пакость!»",
    "😈 «Будь осторожен: я могу случайно сделать что-то приличное.»",
    "🎄 «Праздник? Хм… звучит как повод что-нибудь украсть.»",
    "🎁 «Это не сюрприз — это сюрприииизс! (Ты поймёшь позже.)»",
    "🤏 «Я почти хороший. Примерно на сантиметр.»",
    "🎁 «Это подарок? Нет, это тщательно завернутая проблема.»",
    "😏 «Спокойно. Моя пакость сертифицирована и почти безопасна.»",
    "🎁 «Упаковал с любовью. Разворачивай на свой страх и риск.»",
]


def send_product_visuals(chat_id, file_path_str, caption):
    photos = file_path_str.split(",")
    if len(photos) == 1:
        bot.send_photo(chat_id, photos[0], caption=caption, parse_mode="HTML")
    else:
        media = []
        for i, file_id in enumerate(photos):
            if i == 0:
                media.append(
                    InputMediaPhoto(file_id, caption=caption, parse_mode="HTML")
                )
            else:
                media.append(InputMediaPhoto(file_id))
        bot.send_media_group(chat_id, media)


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
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    # Кнопки с вашими названиями
    kb.add(types.KeyboardButton("🎒 Забрать подарки"))
    kb.row(types.KeyboardButton("📦 Мои подарки"), types.KeyboardButton("🆘 Поддержка"))
    kb.row(types.KeyboardButton("⭐️ Слухи"), types.KeyboardButton("📜 Правила"))
    return kb


@bot.message_handler(commands=["start"])
@anti_flood
def cmd_start(message):
    upsert_user(
        message.chat.id, message.from_user.username, message.from_user.first_name
    )
    joke = random.choice(GRINCH_JOKES)

    welcome_text = (
        f"🎄 Привет,  {message.from_user.first_name}! 🎁"
        " Добро пожаловать к Гринчу!\n\n"
        f"<i>{joke}</i>"
    )
    bot.send_message(
        message.chat.id, welcome_text, reply_markup=main_menu(), parse_mode="HTML"
    )


@bot.callback_query_handler(func=lambda c: c.data == "cmd_main_menu")
def back_to_main(call):
    joke = random.choice(GRINCH_JOKES)
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    bot.send_message(
        call.message.chat.id, f"Главное меню:\n<i>{joke}</i>", reply_markup=main_menu()
    )


# --- ПОКУПКА ---
@bot.message_handler(func=lambda m: m.text == "🎒 Забрать подарки")
@anti_flood
def handle_buy(message):
    # ИСПРАВЛЕНО: bot.send_message вместо bot.send.message
    bot.send_message(
        message.chat.id,
        "Эти товары почти так же хороши, как украденные подарки.\n Хватай, пока не передумал!",
    )
    stores = get_all_stores()
    if not stores:
        return bot.send_message(message.chat.id, "❌ Витрина пуста.")

    kb = types.InlineKeyboardMarkup()
    for s in stores:
        kb.add(
            types.InlineKeyboardButton(
                s["title"], callback_data=f"store_{s['store_id']}_0"
            )
        )

    bot.send_message(message.chat.id, "📂 Выберите Магазин:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("store_"))
def handle_store(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass

    parts = call.data.split("_")
    store_id = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0

    # Уникальные имена
    products = get_unique_products_by_store(store_id)
    if not products:
        return bot.send_message(call.message.chat.id, "В этой категории пока пусто.")

    total_pages = math.ceil(len(products) / PRODUCTS_PER_PAGE)
    start = page * PRODUCTS_PER_PAGE
    end = start + PRODUCTS_PER_PAGE
    page_products = products[start:end]

    kb = types.InlineKeyboardMarkup()
    for p in page_products:
        kb.add(
            types.InlineKeyboardButton(
                f"{p['name']} — {p['price_usd']}$", callback_data=f"pname_{p['ref_id']}"
            )
        )

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
    kb.add(types.InlineKeyboardButton("🔙 Сбежать", callback_data="cmd_buy_callback"))

    try:
        bot.edit_message_text(
            "📦 Выберите товар:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
        )
    except:
        bot.send_message(call.message.chat.id, "📦 Выберите подарок:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "cmd_buy_callback")
def back_to_cats(call):
    handle_buy(call.message)


@bot.callback_query_handler(func=lambda c: c.data == "noop")
def noop(c):
    bot.answer_callback_query(c.id)


# --- ВЫБОР РАЙОНА ---
@bot.callback_query_handler(func=lambda c: c.data.startswith("pname_"))
def handle_district_selection(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass

    ref_id = int(call.data.split("_")[1])
    ref_details = get_product_details_by_id(ref_id)
    if not ref_details:
        return bot.send_message(call.from_user.id, "🤢 Витрина пуста. Я всё украл!")

    name = ref_details["product_name"]
    price = ref_details["price_usd"]
    districts = get_districts_for_product(name)

    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    for d in districts:
        btn_text = f"{d['address']}"
        buttons.append(
            types.InlineKeyboardButton(btn_text, callback_data=f"prod_{d['target_id']}")
        )

    kb.add(*buttons)
    store_id = user_state.get(call.from_user.id, {}).get("store_id", "1")
    kb.add(
        types.InlineKeyboardButton("🔙 Сбежать", callback_data=f"store_{store_id}_0")
    )

    text = f"<b>{name}</b>\n\nЦена: {price} $\nВыберите подходящий район:"
    try:
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode="HTML",
        )
    except:
        bot.send_message(call.message.chat.id, text, reply_markup=kb, parse_mode="HTML")


# --- СОЗДАНИЕ ЗАКАЗА ---
@bot.callback_query_handler(func=lambda c: c.data.startswith("prod_"))
def handle_prod_payment(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass

    uid = call.from_user.id

    # Умный лимит (свежие долги < 2 часов)
    orders = find_orders_by_user(uid)
    unpaid = 0
    now = time.time()
    for d in orders.values():
        if (
            d.get("status") == "waiting_payment"
            and d.get("delivery_status") != "delivered"
        ):
            if (now - d.get("created_at_ts", 0)) < 7200:
                unpaid += 1

    if unpaid >= MAX_UNPAID_ORDERS:
        return bot.send_message(
            uid,
            f"❌ ЛИМИТ. У тебя уже {unpaid} неоплаченных бесполезных покупок.\nСначала плати, потом заходи опять!",
            parse_mode="HTML",
        )

    try:
        target_id = int(call.data.split("_")[1])
        target_info = get_product_details_by_id(target_id)
    except:
        target_info = None

    if not target_info:
        return bot.send_message(uid, "❌ Ошибка: товар не найден.")

    real_pid = get_fresh_product_id(target_info["product_name"], target_info["address"])
    if not real_pid:
        return bot.send_message(
            uid,
            f"❌ В этом районе {target_info['address']} товар украден. Выберите другой.",
        )

    details = get_product_details_by_id(real_pid)
    temp_oid = f"ORD-{int(time.time())}-{uid}"

    # Гринч шутит
    msg = bot.send_message(uid, "😈 Гринч спускается в дымоход...")
    time.sleep(1)
    try:
        bot.edit_message_text("🎒 Упаковываем добычу...", uid, msg.message_id)
    except:
        pass
    time.sleep(1)
    try:
        bot.delete_message(uid, msg.message_id)
    except:
        pass

    res = create_invoice(uid, details["price_usd"], temp_oid)
    if not res:
        return bot.send_message(uid, "❌ Ошибка создания ссылки.")

    pay_url, track_id = res
    real_oid = add_order(
        uid,
        real_pid,
        details["price_usd"],
        details["address"],
        temp_oid,
        track_id,
        pay_url,
    )

    bot.send_message(
        uid,
        "✅ <b>Заказ создан! ⏰ БРОНЬ 1 ЧАС! Если ты не оплатишь это за 60 минут, я ЛИЧНО сожгу твой подарок и продам его снова. Тик-так.</b>",
        parse_mode="HTML",
    )
    bot.send_message(
        uid,
        "ℹ️ Статус своего жалкого заказика глянь в <b>📦 Мои подарки</b>.",
        parse_mode="HTML",
    )

    text = (
        f"🧾 <b>Заказ №{real_oid}</b>\n\n"
        f"📦 Товар: <b>{details['product_name']}</b>\n"
        f"📍 Район: <b>{details['address']}</b>\n"
        f"💰 К оплате: <b>{details['price_usd']} $</b>\n\n"
        f"⚠️ <i>Фото и описание свалятся тебе автоматически после оплаты… если уж так надо.</i>"
    )

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Оплатить", url=pay_url))
    kb.add(types.InlineKeyboardButton("🔙 Отмена", callback_data=f"pname_{target_id}"))

    try:
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
            parse_mode="HTML",
        )
    except:
        bot.send_message(uid, text, reply_markup=kb, parse_mode="HTML")


# --- ТЕКСТОВЫЕ КНОПКИ ---
@bot.message_handler(func=lambda m: m.text == "🤮 Поныть Гринчу")
@anti_flood
def handle_support(message):
    text = (
        f"👨‍💻 <b>Возникли вопросы?</b>\n"
        f"Проблема с оплатой или ненаход?\n\n"
        f"ЭТО ТВОИ ПРОБЛЕМЫ , Шучу\n"
        f"✍️ Пиши оператору: {SUPPORT_LINK}\n"
        f"<i>(Работаем с 10:00 до 22:00)(Возможно 😈)</i>"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Написать оператору ✈️", url=SUPPORT_LINK))
    bot.send_message(message.chat.id, text, reply_markup=kb, parse_mode="HTML")


@bot.message_handler(func=lambda m: m.text == "⭐️ Слухи")
@anti_flood
def handle_reviews(message):
    text = f"💬 Читайте слухи наших довольных клиентов тут:\n{REVIEWS_LINK}"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Перейти к слухам ⭐️", url=REVIEWS_LINK))
    bot.send_message(message.chat.id, text, reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "📜 Правила")
@anti_flood
def handle_rules(message):
    text = (
        "📜 <b>Правила в которых магазин расматривает ПЗ </b>\n\n"
        "1. Видео подхода к месту .\n"
        "2. Иметь 5 покупок .\n"
        "3. Спам оператору = бан.\n"
        "4. Оплата только через бота.\n\n"
        "<i>Покупая у нас, вы соглашаетесь с этими правилами.</i>"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML")


# --- МОИ ЗАКАЗЫ ---
@bot.message_handler(func=lambda m: m.text == "📦 Мои подарки")
@anti_flood
def my_orders(message):
    orders = find_orders_by_user(message.chat.id)
    if not orders:
        return bot.send_message(message.chat.id, "📭 История пуста… как твои ожидания.")

    text = "📦 <b>ВАШИ ПОСЛЕДНИЕ ПОДАРКИ:</b>\n\n"
    for i, (oid, data) in enumerate(orders.items()):
        if i >= 5:
            break
        status = data["status"]
        kb = types.InlineKeyboardMarkup()

        icon = "❓"
        if data["delivery_status"] == "delivered":
            icon = "🎁 Хватай, раз уж выдали"
        elif status == "paid":
            icon = "✅ Ну ладно, оплачено"
        elif status == "cancelled":
            icon = "🗑 Сам же и отменил, молодец"
        elif status == "waiting_payment":
            icon = "⏳ Ждёт твоей щедрости"
            kb.add(
                types.InlineKeyboardButton(
                    "🔄 Ну проверь...", callback_data=f"check_{oid}"
                ),
                types.InlineKeyboardButton(
                    "❌ Отменить(Фу таким быть)", callback_data=f"cancel_{oid}"
                ),
            )
            kb.add(types.InlineKeyboardButton("💳 Заплати уж", url=data["payment_url"]))

        text += f"🛒 <b>{data['product_name']}</b>\n🆔 <code>{oid}</code> | {data['price']}$\nСтатус: {icon}\n➖➖➖➖➖➖\n"

        if status == "waiting_payment":
            bot.send_message(message.chat.id, text, reply_markup=kb, parse_mode="HTML")
            text = ""
    if text:
        bot.send_message(message.chat.id, text, parse_mode="HTML")


@bot.callback_query_handler(func=lambda c: c.data.startswith("cancel_"))
def cancel_order_handler(call):
    oid = call.data.split("_")[1]
    cancel_order_db(oid)
    bot.answer_callback_query(call.id, "Заказ отменен , Блеее🤮 Блееергх!.")
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, f"🗑 Заказ {oid} отменен.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("check_"))
def check_pay(call):
    oid = call.data.split("_")[1]
    order = get_order(oid)
    if not order:
        return bot.answer_callback_query(call.id, "Не найден… как и твоя удача.")
    if order["status"] == "paid":
        return bot.answer_callback_query(call.id, "Уже оплачен, не жми зря.")

    bot.answer_callback_query(call.id, "Проверяю...")
    if verify_payment_via_api(order.get("oxapay_track_id")):
        details = get_product_details_by_id(order["product_id"])
        msg = f"✅ <b>Оплата прошла, ну хоть что-то </b>\n📦 {details['product_name']}\n📍 {details['delivery_text']}\n\n Пользуйся, раз уж купил."
        try:
            send_product_visuals(call.from_user.id, details["file_path"], msg)
            update_order(oid, status="paid", delivery_status="delivered")
            mark_product_as_sold(order["product_id"])
            bot.edit_message_text(
                f"✅ Заказ {oid} выдан. Хватай, пока не передумал.",
                call.message.chat.id,
                call.message.message_id,
            )
        except Exception as e:
            bot.send_message(call.from_user.id, f"🤮 Что-то пошло не так: {e}")
    else:
        bot.send_message(call.from_user.id, "❌ Оплаты нет. И Гринчу это не нравится.")


# --- АДМИНКА ---
@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Добавить товар", "✏️ Изменить товар")
    kb.add("❌ Удалить товар", "🎁 Выдать товар")
    kb.add("📢 Рассылка", "💾 Бэкап БД")
    kb.add("📥 Импорт (CSV)", "🔙 Меню")
    bot.send_message(message.chat.id, "Админка Гринча 😈", reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "🔙 Меню")
def exit_admin(m):
    if m.from_user.id in ADMIN_IDS:
        bot.send_message(m.chat.id, "Выход.", reply_markup=main_menu())


# --- ДОБАВЛЕНИЕ ТОВАРА ---
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
    bot.send_message(m.chat.id, "Куда?", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("aadd_s_"))
def aadd_step1(c):
    admin_state[c.from_user.id] = {"sid": c.data.split("_")[2]}
    msg = bot.send_message(c.message.chat.id, "Название товара?")
    bot.register_next_step_handler(msg, aadd_step2)


def aadd_step2(m):
    admin_state[m.from_user.id]["name"] = m.text
    msg = bot.send_message(m.chat.id, "Цена (USD)?")
    bot.register_next_step_handler(msg, aadd_step3)


def aadd_step3(m):
    try:
        admin_state[m.from_user.id]["price"] = float(m.text.replace(",", "."))
        msg = bot.send_message(m.chat.id, "Район/Адрес (виден всем):")
        bot.register_next_step_handler(msg, aadd_step4)
    except:
        bot.send_message(m.chat.id, "Ошибка числа.")


def aadd_step4(m):
    admin_state[m.from_user.id]["addr"] = m.text
    msg = bot.send_message(m.chat.id, "Секретное описание/Клад:")
    bot.register_next_step_handler(msg, aadd_step5)


def aadd_step5(m):
    admin_state[m.from_user.id]["desc"] = m.text
    admin_state[m.from_user.id]["photos"] = []
    msg = bot.send_message(m.chat.id, "5️⃣ Отправьте **Первое фото**:")
    bot.register_next_step_handler(msg, aadd_photo_loop)


def aadd_photo_loop(m):
    uid = m.from_user.id
    if m.content_type == "photo":
        admin_state[uid]["photos"].append(m.photo[-1].file_id)
        count = len(admin_state[uid]["photos"])
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("✅ Готово, сохранить")
        msg = bot.send_message(
            m.chat.id, f"📸 Фото: {count}. Шли еще или жми Готово:", reply_markup=kb
        )
        bot.register_next_step_handler(msg, aadd_photo_loop)
        return
    elif m.text == "✅ Готово, сохранить":
        if not admin_state[uid]["photos"]:
            msg = bot.send_message(m.chat.id, "Нужно хоть одно фото!")
            bot.register_next_step_handler(msg, aadd_photo_loop)
            return
        aadd_finish(m)
    else:
        bot.send_message(m.chat.id, "Жду фото или кнопку.")
        bot.register_next_step_handler(m, aadd_photo_loop)


def aadd_finish(m):
    d = admin_state[m.from_user.id]
    photos_str = ",".join(d["photos"])
    insert_product(d["sid"], d["name"], d["price"], d["desc"], photos_str, d["addr"])
    kb = types.ReplyKeyboardRemove()
    bot.send_message(m.chat.id, "✅ Товар добавлен!", reply_markup=kb)
    admin_panel(m)


# --- ВЫДАЧА (GIVE) ---
@bot.message_handler(func=lambda m: m.text == "🎁 Выдать товар")
def give_start(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    stores = get_all_stores()
    kb = types.InlineKeyboardMarkup()
    for s in stores:
        kb.add(
            types.InlineKeyboardButton(
                s["title"], callback_data=f"give_s_{s['store_id']}"
            )
        )
    bot.send_message(m.chat.id, "Категория?", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("give_s_"))
def give_list(c):
    sid = c.data.split("_")[2]
    prods = get_products_by_store(sid)
    kb = types.InlineKeyboardMarkup()
    for p in prods:
        kb.add(
            types.InlineKeyboardButton(
                f"{p['name']} ({p['price_usd']}$)",
                callback_data=f"give_p_{p['product_id']}",
            )
        )
    bot.edit_message_text(
        "Товар?", c.message.chat.id, c.message.message_id, reply_markup=kb
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("give_p_"))
def give_ask(c):
    admin_state[c.from_user.id] = {"pid": c.data.split("_")[2]}
    msg = bot.send_message(c.message.chat.id, "ID пользователя?")
    bot.register_next_step_handler(msg, give_final)


def give_final(m):
    try:
        uid = int(m.text)
        pid = admin_state[m.from_user.id]["pid"]
        details = get_product_details_by_id(pid)
        if not details:
            return bot.send_message(m.chat.id, "Нет товара.")

        msg = (
            f"🎁 <b>ВАМ ПОДАРОК!</b>\n📦 {details['product_name']}\n📍 {details['delivery_text']}\n\n"
            f"Спасибо за покупку!\n"
            f"—————————————"
        )

        send_product_visuals(uid, details["file_path"], msg)
        mark_product_as_sold(pid)

        fake_oid = f"GIFT-{int(time.time())}"
        add_order(uid, pid, 0, "Gift", fake_oid, "GIFT", "GIFT")
        update_order(fake_oid, status="paid", delivery_status="delivered")

        bot.send_message(m.chat.id, "✅ Выдано!")
    except Exception as e:
        bot.send_message(m.chat.id, f"Ошибка: {e}")


# --- УДАЛЕНИЕ ---
@bot.message_handler(func=lambda m: m.text == "❌ Удалить товар")
def adm_del(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    stores = get_all_stores()
    kb = types.InlineKeyboardMarkup()
    for s in stores:
        kb.add(
            types.InlineKeyboardButton(
                s["title"], callback_data=f"adel_s_{s['store_id']}"
            )
        )
    bot.send_message(m.chat.id, "Откуда?", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("adel_s_"))
def adm_del_list(c):
    try:
        sid = c.data.split("_")[2]
        # Получаем список товаров
        prods = get_products_by_store(sid)

        # --- ПРОВЕРКА: ЕСТЬ ЛИ ТОВАРЫ? ---
        if not prods:
            return bot.answer_callback_query(
                c.id,
                "❌ В этой категории пусто (или все товары проданы)!",
                show_alert=True,
            )
        # ---------------------------------

        kb = types.InlineKeyboardMarkup()
        for p in prods:
            note = p.get("admin_note", "")
            note_str = f" | {note}" if note else ""
            # Добавляем кнопку для каждого товара
            kb.add(
                types.InlineKeyboardButton(
                    f"❌ {p['name']}{note_str} ({p['price_usd']}$)",
                    callback_data=f"adel_do_{p['product_id']}",
                )
            )

        # Кнопка назад к категориям удаления
        kb.add(
            types.InlineKeyboardButton("🔙 Назад", callback_data="adel_back_to_cats")
        )

        bot.edit_message_text(
            "Выберите товар для удаления:",
            c.message.chat.id,
            c.message.message_id,
            reply_markup=kb,
        )

    except Exception as e:
        bot.answer_callback_query(c.id, f"Ошибка: {e}")


@bot.callback_query_handler(func=lambda c: c.data.startswith("adel_do_"))
def adm_del_act(c):
    adm_del(c.message)
    delete_product(c.data.split("_")[2])
    bot.answer_callback_query(c.id, "Удалено!")
    bot.delete_message(c.message.chat.id, c.message.message_id)


# --- РЕДАКТИРОВАНИЕ (EDIT) ---
@bot.message_handler(func=lambda m: m.text == "✏️ Изменить товар")
def edit_start(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    stores = get_all_stores()
    kb = types.InlineKeyboardMarkup()
    for s in stores:
        kb.add(
            types.InlineKeyboardButton(
                s["title"], callback_data=f"edit_s_{s['store_id']}"
            )
        )
    bot.send_message(m.chat.id, "Категория?", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("edit_s_"))
def edit_list_prods(c):
    sid = c.data.split("_")[2]
    prods = get_products_by_store(sid)
    kb = types.InlineKeyboardMarkup()
    for p in prods:
        note = p.get("admin_note", "")
        note_str = f" | {note}" if note else ""
        kb.add(
            types.InlineKeyboardButton(
                f"{p['name']}{note_str}", callback_data=f"edit_p_{p['product_id']}"
            )
        )
    bot.edit_message_text(
        "Товар?", c.message.chat.id, c.message.message_id, reply_markup=kb
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("edit_p_"))
def edit_field(c):
    pid = c.data.split("_")[2]
    admin_state[c.from_user.id] = {"edit_pid": pid}

    details = get_product_details_by_id(pid)
    info = f"📦 {details['product_name']}\n📍 {details['address']}\n📝 Note: {details.get('admin_note', '-')}"

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("Название", callback_data="edf_name"),
        types.InlineKeyboardButton("Цена", callback_data="edf_price_usd"),
    )
    kb.add(
        types.InlineKeyboardButton("Адрес", callback_data="edf_address"),
        types.InlineKeyboardButton("Заметка", callback_data="edf_admin_note"),
    )
    kb.add(types.InlineKeyboardButton("🗑 УДАЛИТЬ", callback_data=f"adel_do_{pid}"))

    bot.edit_message_text(
        f"{info}\nЧто меняем?", c.message.chat.id, c.message.message_id, reply_markup=kb
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("edf_"))
def edit_val(c):
    field = c.data.replace("edf_", "")
    admin_state[c.from_user.id]["edit_field"] = field
    msg = bot.send_message(c.message.chat.id, "Новое значение:")
    bot.register_next_step_handler(msg, edit_save)


def edit_save(m):
    d = admin_state[m.from_user.id]
    val = m.text
    if d["edit_field"] == "price_usd":
        try:
            val = float(val)
        except:
            return bot.send_message(m.chat.id, "Ошибка. Нужно число.")
    update_product_field(d["edit_pid"], d["edit_field"], val)
    bot.send_message(m.chat.id, "✅ Обновлено!")


# --- РАССЫЛКА ---
@bot.message_handler(func=lambda m: m.text == "📢 Рассылка")
def broadcast(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    msg = bot.send_message(m.chat.id, "Введите текст для ВСЕХ:")
    bot.register_next_step_handler(msg, do_broadcast)


def do_broadcast(m):
    users = get_all_users()
    n = 0
    for u in users:
        try:
            bot.send_message(u, f"📢 <b>Новости:</b>\n{m.text}", parse_mode="HTML")
            n += 1
            time.sleep(0.05)
        except:
            pass
    bot.send_message(m.chat.id, f"Отправлено {n} людям.")


# --- ИМПОРТ (CSV) ---
@bot.message_handler(func=lambda m: m.text == "📥 Импорт (CSV)")
def import_start(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    text = "📄 Пришлите CSV файл (разделитель ;).\nФормат: Категория;Название;Цена;Район;Описание;File_ID"
    bot.send_message(message.chat.id, text)


@bot.message_handler(content_types=["document"])
def handle_csv_import(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.document.file_name.lower().endswith(".csv"):
        return bot.send_message(
            message.chat.id, "❌ Это не CSV файл!", parse_mode="HTML"
        )

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        try:
            csv_text = downloaded_file.decode("utf-8")
        except:
            csv_text = downloaded_file.decode("cp1251")

        csv_file = io.StringIO(csv_text)
        reader = csv.reader(csv_file, delimiter=";")

        success = 0
        for row in reader:
            if len(row) < 6:
                continue
            cat, name, price, addr, desc, fid = (
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
            )
            sid = get_store_id_by_title(cat.strip())
            if sid:
                try:
                    insert_product(
                        sid,
                        name.strip(),
                        float(price.replace(",", ".").strip()),
                        desc.strip(),
                        fid.strip(),
                        addr.strip(),
                    )
                    success += 1
                except:
                    pass
        bot.send_message(
            message.chat.id,
            f"✅ <b>Импорт завершен!</b>\nДобавлено: {success}",
            parse_mode="HTML",
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")


@bot.message_handler(content_types=["photo"])
def get_photo_id_helper(message):
    if message.from_user.id in ADMIN_IDS:
        fid = message.photo[-1].file_id
        try:
            bot.send_message(
                message.chat.id, f"🆔 Код фото:\n<code>{fid}</code>", parse_mode="HTML"
            )
        except:
            pass


# --- БЭКАП ---
@bot.message_handler(func=lambda m: m.text == "💾 Бэкап БД")
def admin_backup(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    msg = bot.send_message(message.chat.id, "Архивирую...")
    tables = ["users", "orders", "products", "stores"]
    zip_buffer = io.BytesIO()

    try:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for table in tables:
                headers, rows = get_table_data(table)
                if not headers:
                    continue
                csv_buffer = io.StringIO()
                csv_buffer.write("\ufeff")
                writer = csv.writer(csv_buffer, delimiter=";")
                writer.writerow(headers)
                writer.writerows(rows)
                zip_file.writestr(f"{table}.csv", csv_buffer.getvalue())

        zip_buffer.seek(0)
        date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
        bot.send_document(
            message.chat.id,
            zip_buffer,
            caption=f"✅ <b>Бэкап от {date_str}</b>",
            visible_file_name=f"backup_{date_str}.zip",
            parse_mode="HTML",
        )
        bot.delete_message(message.chat.id, msg.message_id)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")


@bot.message_handler(commands=["img"])
def view_photo_by_id(message):
    # Проверка на админа
    if message.from_user.id not in ADMIN_IDS:
        return

    try:
        # Разделяем сообщение "/img AgAC..." на части
        args = message.text.split()

        # Если нет ID (просто написали /img)
        if len(args) < 2:
            return bot.send_message(
                message.chat.id,
                "⚠️ Используйте так:\n<code>/img AgAC...ваш_код...</code>",
                parse_mode="HTML",
            )

        file_id = args[1]  # Берем код

        # Бот отправляет фото
        bot.send_photo(message.chat.id, file_id, caption="✅ Вот фото по этому ID")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка. Возможно код неверный.\n{e}")
