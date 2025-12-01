# bot/bot.py
import telebot
from telebot import types
from telebot.types import InputMediaPhoto
import time
import math
from bot.config import TELEGRAM_TOKEN, ADMIN_IDS
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
)

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML", threaded=False)

user_state = {}
admin_state = {}
flood_control = {}

PRODUCTS_PER_PAGE = 5
FLOOD_LIMIT = 0.5
MAX_UNPAID_ORDERS = 5


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
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🛒 Купить", "📦 Мои заказы")
    return kb


@bot.message_handler(commands=["start"])
@anti_flood
def cmd_start(message):
    upsert_user(
        message.chat.id, message.from_user.username, message.from_user.first_name
    )
    bot.send_message(
        message.chat.id,
        f"👋 Привет, {message.from_user.first_name}!\nДобро пожаловать в магазин!",
        reply_markup=main_menu(),
    )


@bot.callback_query_handler(func=lambda c: c.data == "cmd_main_menu")
def back_to_main(call):
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=main_menu())


# --- ПОКУПКА ---
@bot.message_handler(func=lambda m: m.text == "🛒 Купить")
@anti_flood
def handle_buy(message):
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
    bot.send_message(message.chat.id, "📂 Выберите категорию:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("store_"))
def handle_store(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass

    parts = call.data.split("_")
    store_id = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0
    products = get_products_by_store(store_id)
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
                f"{p['name']} — {p['price_usd']}$",
                callback_data=f"prod_{p['product_id']}",
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
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="cmd_buy_callback"))

    try:
        bot.edit_message_text(
            "📦 Выберите товар:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb,
        )
    except:
        bot.send_message(call.message.chat.id, "📦 Выберите товар:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "cmd_buy_callback")
def back_to_cats(call):
    handle_buy(call.message)


@bot.callback_query_handler(func=lambda c: c.data == "noop")
def noop(c):
    bot.answer_callback_query(c.id)


# --- ВЫБОР ТОВАРА ---
@bot.callback_query_handler(func=lambda c: c.data.startswith("prod_"))
def handle_prod_selection(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass

    uid = call.from_user.id

    # --- 🛡 УМНАЯ ПРОВЕРКА ЛИМИТА ---
    orders = find_orders_by_user(uid)
    unpaid_count = 0
    current_time = time.time()

    for d in orders.values():
        # 1. Заказ ждет оплаты?
        is_waiting = d.get("status") == "waiting_payment"
        # 2. Товар еще не выдан?
        not_delivered = d.get("delivery_status") != "delivered"
        # 3. Заказ свежий? (Меньше 2 часов / 7200 секунд)
        # Если заказу больше 2 часов, ссылка на оплату все равно сгорела, не считаем его.
        is_fresh = (current_time - d.get("created_at_ts", 0)) < 7200

        if is_waiting and not_delivered and is_fresh:
            unpaid_count += 1

    if unpaid_count >= MAX_UNPAID_ORDERS:
        return bot.send_message(
            uid,
            f"🚫 <b>Лимит заказов превышен!</b>\nУ вас уже есть {unpaid_count} активных счетов на оплату.\nОплатите их или дождитесь (2 часа), пока они сгорят.",
            parse_mode="HTML",
        )
    # --------------------------------

    try:
        pid = int(call.data.split("_")[1])
        details = get_product_details_by_id(pid)
    except:
        details = None

    if not details:
        return bot.send_message(uid, "❌ Товар не найден.")

    temp_oid = f"ORD-{int(time.time())}-{uid}"
    res = create_invoice(uid, details["price_usd"], temp_oid)
    if not res:
        return bot.send_message(uid, "❌ Ошибка создания ссылки.")

    pay_url, track_id = res
    real_oid = add_order(
        uid, pid, details["price_usd"], "Online", temp_oid, track_id, pay_url
    )

    text = (
        f"🧾 <b>Заказ №{real_oid}</b>\n\n"
        f"📦 Товар: <b>{details['product_name']}</b>\n"
        f"📍 Район: <b>{details.get('address', 'Не указан')}</b>\n"
        f"💰 К оплате: <b>{details['price_usd']} $</b>\n\n"
        f"⚠️ <i>Фото и описание придут автоматически после оплаты.</i>"
    )

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Оплатить", url=pay_url))
    sid = user_state.get(uid, {}).get("store_id", "1")
    kb.add(
        types.InlineKeyboardButton(
            "🔙 Отмена", callback_data=f"store_{sid}_0" if sid else "cmd_buy_callback"
        )
    )

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


# --- МОИ ЗАКАЗЫ ---
@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
@anti_flood
def my_orders(message):
    orders = find_orders_by_user(message.chat.id)
    if not orders:
        return bot.send_message(message.chat.id, "📭 История пуста.")

    text = "📦 <b>ВАШИ ПОСЛЕДНИЕ ЗАКАЗЫ:</b>\n\n"
    for i, (oid, data) in enumerate(orders.items()):
        if i >= 5:
            break
        status = data["status"]
        kb = types.InlineKeyboardMarkup()

        icon = "❓"
        if data["delivery_status"] == "delivered":
            icon = "🎁 ВЫДАН"
        elif status == "paid":
            icon = "✅ ОПЛАЧЕН"
        elif status == "cancelled":
            icon = "🗑 ОТМЕНЕН"
        elif status == "waiting_payment":
            icon = "⏳ ОЖИДАЕТ ОПЛАТЫ"
            kb.add(
                types.InlineKeyboardButton(
                    "🔄 Проверить", callback_data=f"check_{oid}"
                ),
                types.InlineKeyboardButton(
                    "❌ Отменить", callback_data=f"cancel_{oid}"
                ),
            )
            kb.add(types.InlineKeyboardButton("💳 Оплатить", url=data["payment_url"]))

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
    bot.answer_callback_query(call.id, "Заказ отменен.")
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, f"🗑 Заказ {oid} отменен.")


@bot.callback_query_handler(func=lambda c: c.data.startswith("check_"))
def check_pay(call):
    oid = call.data.split("_")[1]
    order = get_order(oid)
    if not order:
        return bot.answer_callback_query(call.id, "Не найден.")
    if order["status"] == "paid":
        return bot.answer_callback_query(call.id, "Уже оплачен!")

    bot.answer_callback_query(call.id, "Проверяю...")
    if verify_payment_via_api(order.get("oxapay_track_id")):
        details = get_product_details_by_id(order["product_id"])
        msg = f"✅ <b>Оплата прошла!</b>\n📦 {details['product_name']}\n📍 {details['delivery_text']}\n\nСпасибо за покупку!"
        try:
            send_product_visuals(call.from_user.id, details["file_path"], msg)
            update_order(oid, status="paid", delivery_status="delivered")
            mark_product_as_sold(order["product_id"])
            bot.edit_message_text(
                f"✅ Заказ {oid} выдан!", call.message.chat.id, call.message.message_id
            )
        except Exception as e:
            bot.send_message(call.from_user.id, f"Ошибка выдачи: {e}")
    else:
        bot.send_message(call.from_user.id, "❌ Оплата пока не найдена.")


# --- АДМИНКА ---
@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Добавить товар", "✏️ Изменить товар")
    kb.add("❌ Удалить товар", "🎁 Выдать товар")
    kb.add("📢 Рассылка", "🔙 Меню")
    bot.send_message(message.chat.id, "Админка:", reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "🔙 Меню")
def exit_admin(m):
    if m.from_user.id in ADMIN_IDS:
        bot.send_message(m.chat.id, "Выход.", reply_markup=main_menu())


# --- ДОБАВЛЕНИЕ (МУЛЬТИ-ФОТО) ---
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
                p["name"], callback_data=f"give_p_{p['product_id']}"
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
        "Жми для удаления:", c.message.chat.id, c.message.message_id, reply_markup=kb
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("adel_do_"))
def adm_del_act(c):
    delete_product(c.data.split("_")[2])
    bot.answer_callback_query(c.id, "Удалено!")
    bot.delete_message(c.message.chat.id, c.message.message_id)


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
        kb.add(
            types.InlineKeyboardButton(
                p["name"], callback_data=f"edit_p_{p['product_id']}"
            )
        )
    bot.edit_message_text(
        "Товар?", c.message.chat.id, c.message.message_id, reply_markup=kb
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("edit_p_"))
def edit_field(c):
    pid = c.data.split("_")[2]
    admin_state[c.from_user.id] = {"edit_pid": pid}
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("Название", callback_data="edf_name"),
        types.InlineKeyboardButton("Цена", callback_data="edf_price_usd"),
        types.InlineKeyboardButton("Адрес", callback_data="edf_address"),
    )
    bot.edit_message_text(
        "Что меняем?", c.message.chat.id, c.message.message_id, reply_markup=kb
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
            return bot.send_message(m.chat.id, "Ошибка.")
    update_product_field(d["edit_pid"], d["edit_field"], val)
    bot.send_message(m.chat.id, "Обновлено!")


# 1 d
