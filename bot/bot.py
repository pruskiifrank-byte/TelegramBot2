# bot/bot.py
import telebot
from telebot import types
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
)

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML", threaded=False)

# Состояния
user_state = {}
admin_state = {}
flood_control = {}

PRODUCTS_PER_PAGE = 5
FLOOD_LIMIT = 0.5


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
    # Сохраняем пользователя в БД для рассылки
    upsert_user(
        message.chat.id, message.from_user.username, message.from_user.first_name
    )

    bot.send_message(
        message.chat.id,
        f"👋 Привет, {message.from_user.first_name}!\nДобро пожаловать в магазин!\n"
        "🎁 Выбирай быстрее. (Или я заберу это себе!)",
        reply_markup=main_menu(),
    )


@bot.callback_query_handler(func=lambda c: c.data == "cmd_main_menu")
def back_to_main(call):
    # Пытаемся удалить сообщение, но если не выйдет — игнорируем ошибку
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass  # Сообщение уже удалено, ничего страшного

    bot.send_message(call.message.chat.id, "Главное меню:", reply_markup=main_menu())


# --- ПОКУПКА (ИЗМЕНЕНО: Без фото, Без адреса) ---


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
    kb.add(
        types.InlineKeyboardButton("🔙 Назад", callback_data="cmd_buy_callback")
    )  # Исправил callback

    bot.edit_message_text(
        "📦 Выберите товар:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda c: c.data == "cmd_buy_callback")
def back_to_cats(call):
    # Возврат к категориям
    handle_buy(call.message)


@bot.callback_query_handler(func=lambda c: c.data == "noop")
def noop(c):
    bot.answer_callback_query(c.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("prod_"))
def handle_prod_selection(call):
    """Показывает товар и СРАЗУ кнопку оплаты (без фото, без адреса)."""
    pid = int(call.data.split("_")[1])
    details = get_product_details_by_id(pid)
    if not details:
        return bot.answer_callback_query(call.id, "Ошибка товара")

    uid = call.from_user.id

    # Генерируем ссылку на оплату сразу
    temp_oid = f"ORD-{int(time.time())}-{uid}"
    res = create_invoice(uid, details["price_usd"], temp_oid)

    if not res:
        return bot.send_message(uid, "❌ Ошибка платежной системы.")

    pay_url, track_id = res

    # Сохраняем заказ (Адрес теперь просто 'Online')
    real_oid = add_order(
        uid, pid, details["price_usd"], "Digital/Online", temp_oid, track_id, pay_url
    )

    # Формируем сообщение БЕЗ ФОТО
    text = (
        f"🧾 **Заказ №{real_oid}**\n\n"
        f"📦 Товар: **{details['product_name']}**\n"
        f"💰 К оплате: **{details['price_usd']} $**\n\n"
        f"⚠️ _Фото и данные для получения вы получите автоматически после оплаты или не получите_ 😈"
    )

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Оплатить (Крипта)", url=pay_url))
    kb.add(
        types.InlineKeyboardButton(
            "🔙 Отмена",
            callback_data=f"store_{user_state.get(uid, {}).get('store_id', '1')}_0",
        )
    )  # Пробуем вернуть в магаз

    # Отправляем новое сообщение, чтобы не путать с редактированием
    bot.send_message(uid, text, reply_markup=kb, parse_mode="Markdown")
    bot.answer_callback_query(call.id)


# --- МОИ ЗАКАЗЫ ---
@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
@anti_flood
def my_orders(message):
    orders = find_orders_by_user(message.chat.id)
    if not orders:
        return bot.send_message(message.chat.id, "📭 У вас пока нет заказов.")

    text = "📦 <b>ВАШИ ПОСЛЕДНИЕ ЗАКАЗЫ:</b>\n\n"

    # Отправляем каждый заказ отдельным сообщением или блоком с кнопкой
    # Для удобства сделаем список с инлайн-кнопками под сообщением, если заказов немного
    # Но проще сделать так:

    for i, (oid, data) in enumerate(orders.items()):
        if i >= 5:
            break

        status_text = "❌ Ошибка"
        kb = types.InlineKeyboardMarkup()

        if data["delivery_status"] == "delivered":
            status_text = "🎁 ВЫДАН"
        elif data["status"] == "paid":
            status_text = "✅ ОПЛАЧЕН (Выдача...)"
        elif data["status"] == "waiting_payment":
            status_text = "⏳ ОЖИДАЕТ ОПЛАТЫ"
            # Кнопка проверки оплаты
            kb.add(
                types.InlineKeyboardButton(
                    "🔄 Проверить оплату / Получить", callback_data=f"check_{oid}"
                )
            )
            kb.add(
                types.InlineKeyboardButton(
                    "💳 Ссылка на оплату", url=data["payment_url"]
                )
            )

        msg_text = (
            f"🛒 <b>{data['product_name']}</b>\n"
            f"🆔 <code>{oid}</code> | 💰 {data['price']} $\n"
            f"Статус: {status_text}"
        )
        bot.send_message(message.chat.id, msg_text, reply_markup=kb, parse_mode="HTML")


# ==========================================
#              АДМИН ПАНЕЛЬ
# ==========================================


@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Добавить товар", "✏️ Изменить товар")
    kb.add("❌ Удалить товар", "📢 Рассылка")
    kb.add("🎁 Выдать товар")
    kb.add("🔙 Меню")
    bot.send_message(message.chat.id, "👨‍💻 Админка v2.0", reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "🔙 Меню")
def exit_admin(m):
    if m.from_user.id in ADMIN_IDS:
        bot.send_message(m.chat.id, "Выход.", reply_markup=main_menu())


# --- 1. РАССЫЛКА (BROADCAST) ---


@bot.message_handler(func=lambda m: m.text == "📢 Рассылка")
def broadcast_menu(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🗣 Всем пользователям", callback_data="bc_all"))
    kb.add(types.InlineKeyboardButton("👤 Одному человеку", callback_data="bc_one"))
    bot.send_message(m.chat.id, "Кому пишем?", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "bc_all")
def bc_all_start(c):
    msg = bot.send_message(c.message.chat.id, "✍️ Введите текст сообщения для ВСЕХ:")
    bot.register_next_step_handler(msg, bc_all_send)


def bc_all_send(m):
    users = get_all_users()
    count = 0
    for uid in users:
        try:
            bot.send_message(
                uid, f"📢 <b>Объявление:</b>\n\n{m.text}", parse_mode="HTML"
            )
            count += 1
            time.sleep(0.05)  # Небольшая задержка
        except:
            pass
    bot.send_message(m.chat.id, f"✅ Отправлено {count} пользователям.")


@bot.callback_query_handler(func=lambda c: c.data == "bc_one")
def bc_one_start(c):
    msg = bot.send_message(c.message.chat.id, "🆔 Введите ID пользователя (цифры):")
    bot.register_next_step_handler(msg, bc_one_text)


def bc_one_text(m):
    try:
        uid = int(m.text)
        admin_state[m.from_user.id] = {"target_uid": uid}
        msg = bot.send_message(m.chat.id, "✍️ Введите текст сообщения:")
        bot.register_next_step_handler(msg, bc_one_send)
    except:
        bot.send_message(m.chat.id, "❌ Это не ID.")


def bc_one_send(m):
    uid = admin_state[m.from_user.id]["target_uid"]
    try:
        bot.send_message(
            uid,
            f"📩 <b>Сообщение от администратора:</b>\n\n{m.text}",
            parse_mode="HTML",
        )
        bot.send_message(m.chat.id, "✅ Доставлено.")
    except Exception as e:
        bot.send_message(m.chat.id, f"❌ Ошибка доставки: {e}")


# --- 2. ИЗМЕНЕНИЕ ТОВАРА (EDIT) ---


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
    bot.send_message(m.chat.id, "В какой категории товар?", reply_markup=kb)


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
        "Выберите товар для правки:",
        c.message.chat.id,
        c.message.message_id,
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("edit_p_"))
def edit_choose_field(c):
    pid = c.data.split("_")[2]
    # Сохраняем ID товара
    admin_state[c.from_user.id] = {"edit_pid": pid}

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("Название", callback_data="edf_name"),
        types.InlineKeyboardButton("Цена", callback_data="edf_price_usd"),
    )
    kb.add(
        types.InlineKeyboardButton("Описание/Клад", callback_data="edf_delivery_text"),
        types.InlineKeyboardButton("Фото", callback_data="edf_file_path"),
    )

    bot.edit_message_text(
        "Что меняем?", c.message.chat.id, c.message.message_id, reply_markup=kb
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("edf_"))
def edit_input_val(c):
    field = c.data.replace("edf_", "")  # name, price_usd ...
    admin_state[c.from_user.id]["edit_field"] = field

    msg_text = "Введите новое значение:"
    if field == "file_path":
        msg_text = "Отправьте новое ФОТО:"

    msg = bot.send_message(c.message.chat.id, msg_text)
    bot.register_next_step_handler(msg, edit_save_val)


def edit_save_val(m):
    data = admin_state[m.from_user.id]
    field = data["edit_field"]
    pid = data["edit_pid"]

    new_val = m.text

    # Обработка разных типов
    if field == "file_path":
        if not m.photo:
            return bot.send_message(m.chat.id, "Нужно фото! Отмена.")
        new_val = m.photo[-1].file_id
    elif field == "price_usd":
        try:
            new_val = float(m.text.replace(",", "."))
        except:
            return bot.send_message(m.chat.id, "Ошибка цены. Отмена.")

    update_product_field(pid, field, new_val)
    bot.send_message(m.chat.id, "✅ Успешно обновлено!")
    admin_panel(m)  # Возврат в меню


# --- 3. ДОБАВЛЕНИЕ И УДАЛЕНИЕ (Старый код, сокращенно) ---


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
    bot.send_message(m.chat.id, "Откуда удаляем?", reply_markup=kb)


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
def adm_del_ok(c):
    delete_product(c.data.split("_")[2])
    bot.answer_callback_query(c.id, "Удалено!")
    bot.delete_message(c.message.chat.id, c.message.message_id)


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
def aadd_name(c):
    admin_state[c.from_user.id] = {"sid": c.data.split("_")[2]}
    msg = bot.send_message(c.message.chat.id, "Название?")
    bot.register_next_step_handler(msg, aadd_price)


def aadd_price(m):
    admin_state[m.from_user.id]["name"] = m.text
    msg = bot.send_message(m.chat.id, "Цена (USD)?")
    bot.register_next_step_handler(msg, aadd_desc)


def aadd_desc(m):
    try:
        admin_state[m.from_user.id]["price"] = float(m.text.replace(",", "."))
        msg = bot.send_message(m.chat.id, "Описание (будет выдано ПОСЛЕ оплаты):")
        bot.register_next_step_handler(msg, aadd_photo)
    except:
        bot.send_message(m.chat.id, "Число!")


def aadd_photo(m):
    admin_state[m.from_user.id]["desc"] = m.text
    msg = bot.send_message(m.chat.id, "Фото товара:")
    bot.register_next_step_handler(msg, aadd_fin)


def aadd_fin(m):
    if not m.photo:
        return
    insert_product(
        admin_state[m.from_user.id]["sid"],
        admin_state[m.from_user.id]["name"],
        admin_state[m.from_user.id]["price"],
        admin_state[m.from_user.id]["desc"],
        m.photo[-1].file_id,
    )
    bot.send_message(m.chat.id, "✅ Добавлено!")


# --- 📦 МОИ ЗАКАЗЫ (ОБНОВЛЕНИЕ) ---


@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
@anti_flood
@bot.message_handler(func=lambda m: m.text == "📦 Мои заказы")
@anti_flood
def my_orders(message):
    orders = find_orders_by_user(message.chat.id)

    if not orders:
        return bot.send_message(message.chat.id, "📭 У вас пока нет заказов.")

    text = "📦 <b>ВАШИ ПОСЛЕДНИЕ ЗАКАЗЫ:</b>\n\n"

    # Показываем только последние 10, чтобы не спамить
    for i, (oid, data) in enumerate(orders.items()):
        if i >= 10:
            break

        # --- ЛОГИКА СТАТУСОВ ---
        status_line = ""

        # 1. Если товар уже выдан
        if data["delivery_status"] == "delivered":
            status_line = "🎁 <b>СТАТУС: ВЫДАН</b>"

        # 2. Если оплачен, но почему-то не выдан (сбой)
        elif data["status"] == "paid":
            status_line = "✅ <b>СТАТУС: ОПЛАЧЕН</b> (Обработка...)"

        # 3. Если ждет оплаты
        elif data["status"] == "waiting_payment":
            status_line = f"⏳ <b>СТАТУС: ОЖИДАЕТ ОПЛАТЫ</b>\n🔗 <a href='{data['payment_url']}'>Оплатить сейчас</a>"

        # 4. Другое (Expired, Error)
        else:
            status_line = f"❌ <b>СТАТУС: {data['status'].upper()}</b>"

        # Формируем красивый блок
        text += (
            f"🛒 <b>{data['product_name']}</b>\n"
            f"🆔 <code>{oid}</code> | 💰 {data['price']} $\n"
            f"{status_line}\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
        )

    # Добавляем кнопку "disable_web_page_preview", чтобы ссылки не разворачивались
    bot.send_message(
        message.chat.id, text, parse_mode="HTML", disable_web_page_preview=True
    )


# Хендлер для нажатия на кнопку заказа в списке
@bot.callback_query_handler(func=lambda c: c.data.startswith("myord_"))
def get_purchased_product(call):
    uid = call.from_user.id
    order_id = call.data.split("_")[1]

    # 1. Ищем заказ
    order = get_order(order_id)  # Эта функция из storage.py

    if not order:
        return bot.answer_callback_query(call.id, "Заказ не найден.")

    # 2. Проверяем, реально ли он оплачен
    if order["status"] != "paid" and order["delivery_status"] != "delivered":
        return bot.answer_callback_query(
            call.id, "Этот заказ еще не оплачен!", show_alert=True
        )

    # 3. Достаем детали товара
    details = get_product_details_by_id(order["product_id"])
    if not details:
        return bot.answer_callback_query(call.id, "Товар был удален из базы.")

    # 4. Отправляем данные снова
    text = (
        f"✅ **Заказ:** {order_id}\n"
        f"📦 **Товар:** {details['product_name']}\n\n"
        f"📍 **ВАШИ ДАННЫЕ:**\n{details['delivery_text']}"
    )

    try:
        # Отправляем фото по ID
        bot.send_photo(uid, details["file_path"], caption=text, parse_mode="Markdown")
        bot.answer_callback_query(call.id, "Данные отправлены!")
    except Exception as e:
        bot.send_message(uid, text + "\n\n(Фото недоступно)", parse_mode="Markdown")


# --- 4. РУЧНАЯ ВЫДАЧА ТОВАРА (GIVE) ---


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
    bot.send_message(m.chat.id, "В какой категории товар для выдачи?", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("give_s_"))
def give_list_prods(c):
    sid = c.data.split("_")[2]
    prods = get_products_by_store(sid)
    if not prods:
        return bot.answer_callback_query(
            c.id, "В этой категории пусто.", show_alert=True
        )

    kb = types.InlineKeyboardMarkup()
    for p in prods:
        kb.add(
            types.InlineKeyboardButton(
                f"{p['name']} ({p['price_usd']}$)",
                callback_data=f"give_p_{p['product_id']}",
            )
        )
    bot.edit_message_text(
        "Выберите товар, который хотите выдать:",
        c.message.chat.id,
        c.message.message_id,
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("give_p_"))
def give_ask_user(c):
    pid = c.data.split("_")[2]
    admin_state[c.from_user.id] = {"give_pid": pid}

    msg = bot.send_message(
        c.message.chat.id, "🆔 Введите ID пользователя, которому выдать товар (цифры):"
    )
    bot.register_next_step_handler(msg, give_process)


def give_process(m):
    try:
        target_uid = int(m.text)
        pid = admin_state[m.from_user.id]["give_pid"]
    except:
        return bot.send_message(m.chat.id, "❌ Некорректный ID. Операция отменена.")

    # Получаем детали товара
    details = get_product_details_by_id(pid)
    if not details:
        return bot.send_message(m.chat.id, "❌ Товар не найден (возможно, уже продан).")

    # Формируем сообщение для клиента
    text = (
        f"🎁 <b>ВАМ ВЫДАН ТОВАР (Администратором)</b>\n"
        f"📦 Товар: <b>{details['product_name']}</b>\n\n"
        f"📍 <b>ВАШ КЛАД:</b>\n{details['delivery_text']}\n\n"
        f"—————————————\n"
        f"Спасибо за покупку \n"
        f"быстрого подъёма и мягкого покура🥰\n\n"
        f"Отзывы довольных клиентов⤵️\n"
        f"https://t.me/+NW9rf1wPSl5lZmM6\n\n"
        f"Резервы в случае блокировки ⤵️⤵️⤵️\n"
        f"@scooby_doorezerv1\n"
        f"@scooby_doorezerv2\n"
        f"@scoobbyy_doo\n\n"
        f"Это все актуальные линки \n"
        f"Остальное скам-мошенники\n"
        f"—————————————"
    )

    try:
        # 1. Отправляем товар клиенту
        bot.send_photo(
            target_uid, details["file_path"], caption=text, parse_mode="HTML"
        )

        # 2. Помечаем как проданный в БД (функция должна быть импортирована из storage)
        from bot.storage import mark_product_as_sold

        mark_product_as_sold(pid)

        # 3. Создаем запись в заказах (для истории)
        # Генерируем фейковый ID заказа
        fake_oid = f"MANUAL-{int(time.time())}"
        # add_order требует много параметров, передадим заглушки
        add_order(target_uid, pid, 0.0, "Manual Delivery", fake_oid, "MANUAL", "MANUAL")
        # Обновляем статус на delivered
        from bot.storage import update_order

        update_order(fake_oid, status="manual_gift", delivery_status="delivered")

        bot.send_message(
            m.chat.id,
            f"✅ Товар успешно выдан пользователю {target_uid} и убран с витрины.",
        )

    except Exception as e:
        bot.send_message(
            m.chat.id,
            f"❌ Ошибка отправки (возможно бот заблокирован пользователем): {e}",
        )

    # Возврат в админку
    admin_panel(m)


@bot.callback_query_handler(func=lambda c: c.data.startswith("check_"))
def check_payment_status(call):
    oid = call.data.split("_")[1]
    order = get_order(oid)

    if not order:
        return bot.answer_callback_query(call.id, "Заказ не найден.")

    if order["delivery_status"] == "delivered":
        return bot.answer_callback_query(
            call.id, "✅ Этот товар уже выдан!", show_alert=True
        )

    bot.answer_callback_query(call.id, "🔄 Проверяю в блокчейне...")

    # 1. Проверяем через API OxaPay
    # Убедитесь, что в базе есть oxapay_track_id. В add_order мы его сохраняли.
    # Если его нет в get_order, нужно добавить в storage.py в SELECT

    # Предполагаем, что track_id есть в таблице orders, но get_order его может не возвращать.
    # ВАЖНО: Проверьте bot/storage.py -> get_order. Он должен возвращать 'oxapay_track_id'.
    # Если нет, добавьте его в return.

    # Временное решение: делаем запрос к БД напрямую за track_id, если его нет в dict
    track_id = order.get("oxapay_track_id")
    # (Если в get_order вы не добавили это поле, то проверка не сработает)

    is_paid = verify_payment_via_api(track_id)

    if is_paid:
        # === ВЫДАЧА ТОВАРА ===
        details = get_product_details_by_id(order["product_id"])

        text = (
            f"✅ <b>Оплата подтверждена!</b>\n"
            f"📦 Товар: <b>{details['product_name']}</b>\n\n"
            f"📍 <b>ВАШ КЛАД:</b>\n{details['delivery_text']}\n\n"
            f"—————————————\n"
            f"Спасибо за покупку!\n"
            f"—————————————"
        )

        try:
            bot.send_photo(
                call.from_user.id, details["file_path"], caption=text, parse_mode="HTML"
            )

            # Обновляем статусы
            update_order(oid, status="paid", delivery_status="delivered")
            mark_product_as_sold(order["product_id"])

            bot.edit_message_text(
                f"✅ Заказ {oid} успешно выдан!",
                call.message.chat.id,
                call.message.message_id,
            )
        except Exception as e:
            bot.send_message(call.from_user.id, "Ошибка выдачи фото. Пишите админу.")
    else:
        bot.send_message(
            call.from_user.id,
            "❌ Оплата пока не поступила или подтверждается сетью. Подождите пару минут и нажмите кнопку снова.",
        )
