# bot/bot.py
import telebot
from telebot import types
from telebot.types import InputMediaPhoto
import time
import threading
import math
import csv
import io
import os
import zipfile
import random
import socket
from captcha.image import ImageCaptcha
from datetime import datetime
from bot.stats import get_statistics
from bot.db import execute_query
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
    check_user_exists,
)

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML", threaded=False)

# Состояния
user_state = {}
admin_state = {}
flood_control = {}
captcha_users = {}

# Словарь для отслеживания попыток капчи: {user_id: {"attempts": int, "block_until": float}}
captcha_attempts = {}

# Константы для капчи
MAX_CAPTCHA_ATTEMPTS = 2
CAPTCHA_BLOCK_DURATION = 300


PRODUCTS_PER_PAGE = 5
FLOOD_LIMIT = 2.7
MAX_UNPAID_ORDERS = 1

# Фотки
photo_buffer = {}  # Здесь будем копить фото: {user_id: [id1, id2]}
photo_timers = {}
# Тех-пауза
MAINTENANCE_FILE = "maintenance.state"

# --- НАДЕЖНОЕ ХРАНЕНИЕ СТАТУСА (CACHE + DB) ---

# Глобальный кеш, чтобы не дергать БД каждую секунду
# Храним: {"value": True/False, "time": timestamp}
_maintenance_cache = {"value": False, "last_updated": 0}
CACHE_TTL = 60  # Обновлять кеш из БД раз в 60 секунд (на случай ручных правок в БД)

print("PID:", os.getpid())
print("ENV:", os.environ)
print("HOSTNAME:", socket.gethostname())


def init_settings_table():
    """Создает таблицу при старте, если её нет"""
    execute_query(
        """
        CREATE TABLE IF NOT EXISTS bot_settings (
            setting_key VARCHAR(50) PRIMARY KEY,
            setting_value VARCHAR(255)
        );
    """
    )


# Инициализация таблицы (безопасная)
try:
    init_settings_table()
except Exception as e:
    print(f"DB Init Error: {e}")


def is_maintenance_active():
    """Читает статус (Сначала кеш, потом БД)"""
    global _maintenance_cache

    # Если кеш свежий — верим ему
    if time.time() - _maintenance_cache["last_updated"] < CACHE_TTL:
        return _maintenance_cache["value"]

    try:
        # Читаем из БД
        res = execute_query(
            "SELECT setting_value FROM bot_settings WHERE setting_key = 'maintenance_mode';",
            fetch=True,
        )
        status = res and res[0][0] == "1"

        # Обновляем кеш
        _maintenance_cache = {"value": status, "last_updated": time.time()}
        return status
    except Exception as e:
        print(f"Error reading maintenance status: {e}")
        return _maintenance_cache["value"]


def set_maintenance_mode(enable: bool):
    """Пишет статус в БД и обновляет кеш"""
    global _maintenance_cache
    val = "1" if enable else "0"

    # Мгновенно обновляем кеш (чтобы бот не тупил)
    _maintenance_cache = {"value": enable, "last_updated": time.time() + 999999}

    try:
        query = """
        INSERT INTO bot_settings (setting_key, setting_value) 
        VALUES ('maintenance_mode', %s) 
        ON CONFLICT (setting_key) DO UPDATE 
        SET setting_value = EXCLUDED.setting_value;
        """
        execute_query(query, (val,))
    except Exception as e:
        print(f"Critical error saving status: {e}")


# Ссыль на картинку с заказа
ORDER_IMG = "AgACAgUAAxkBAAIR3GkwvRcNA3SAoqDSRicOyT0bFeAlAAJuC2sbRHuIVcqZZBo5CZGgAQADAgADeQADNgQ"

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


@bot.message_handler(
    func=lambda m: is_maintenance_active() and m.from_user.id not in ADMIN_IDS
)
def maintenance_message_block(message):
    """
    Перехватывает ЛЮБЫЕ текстовые сообщения и команды (/start),
    если включен режим обслуживания.
    """
    text = (
        "🚧 <b>МАГАЗИН ВРЕМЕННО ЗАКРЫТ</b> 🚧\n\n"
        "Гринч проводит инвентаризацию подарков.\n"
        "<i>Мы вернемся совсем скоро!</i> 🕐"
    )
    # Можно добавить картинку, если есть, или просто текст
    bot.send_message(message.chat.id, text, parse_mode="HTML")


@bot.callback_query_handler(
    func=lambda c: is_maintenance_active() and c.from_user.id not in ADMIN_IDS
)
def maintenance_callback_block(call):
    """
    Перехватывает ЛЮБЫЕ нажатия на кнопки.
    Показывает всплывающее уведомление (alert), чтобы не спамить в чат.
    """
    try:
        bot.answer_callback_query(
            call.id,
            "⛔️ Магазин на тех. обслуживании! Попробуйте позже.",
            show_alert=True,
        )
    except:
        pass


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
    """Декоратор для защиты от спама"""

    def wrapper(message):
        # 1. Определяем ID
        try:
            if isinstance(message, types.CallbackQuery):
                uid = message.from_user.id
                chat_id = message.message.chat.id
            else:
                uid = message.from_user.id
                chat_id = message.chat.id
        except AttributeError:
            return  # Если непонятный апдейт, пропускаем

        # 2. Админов не проверяем на флуд (чтобы не бесить при тестах)
        if uid in ADMIN_IDS:
            return func(message)

        now = time.time()
        last_time = flood_control.get(uid, 0)

        # 3. ПРОВЕРКА
        if now - last_time < FLOOD_LIMIT:
            # Вычисляем, сколько осталось ждать
            wait_time = int(FLOOD_LIMIT - (now - last_time)) + 1
            print(f"🚫 ФЛУД: Юзер {uid} заблокирован на {wait_time}с")

            # (Опционально) Можно сказать юзеру "Хватит тыкать", но лучше молчать,
            # чтобы не спамить в ответ на спам.
            return

        # 4. Обновляем время И выполняем функцию
        flood_control[uid] = now

        try:
            return func(message)
        except Exception as e:
            print(f"⚠️ Ошибка в обработчике {func.__name__}: {e}")

    return wrapper


def is_user_blocked(chat_id):
    """Проверяет, заблокирован ли пользователь"""
    # 🔥 Админа никогда не блокируем!
    if chat_id in ADMIN_IDS:
        return False

    if chat_id not in captcha_attempts:
        return False

    block_until = captcha_attempts[chat_id].get("block_until", 0)
    if block_until > time.time():
        return True
    return False


def get_remaining_block_time(chat_id):
    """Возвращает оставшееся время блокировки (минуты, секунды)"""
    if chat_id not in captcha_attempts:
        return 0, 0

    block_until = captcha_attempts[chat_id].get("block_until", 0)
    remaining = block_until - time.time()
    if remaining <= 0:
        return 0, 0

    minutes = int(remaining // 60)
    seconds = int(remaining % 60)
    return minutes, seconds


def send_captcha(chat_id):
    """Генерирует картинку с цифрами и отправляет юзеру"""
    print(f"🎲 Генерирую капчу для {chat_id}")

    # 1. Проверка блокировки
    if is_user_blocked(chat_id):
        minutes, seconds = get_remaining_block_time(chat_id)
        bot.send_message(
            chat_id,
            f"🚫 Вы заблокированы на 5 минут за неверный ввод капчи.\n"
            f"Осталось: {minutes} мин {seconds} сек.",
        )
        return

    try:
        code = str(random.randint(1000, 9999))
        image = ImageCaptcha(width=280, height=90)
        data = image.generate(code)

        captcha_users[chat_id] = code
        print(f"🔒 Юзер {chat_id} заперт в капче. Код: {code}")

        bot.send_photo(
            chat_id,
            data,
            caption="🤖 <b>ПРОВЕРКА НА БОТА</b>\nВведите цифры с картинки:",
            parse_mode="HTML",
        )

    except Exception as e:
        print(f"❌ Ошибка отправки капчи: {e}")
        if chat_id in captcha_users:
            del captcha_users[chat_id]
        if chat_id in captcha_attempts:
            del captcha_attempts[chat_id]

        show_main_menu_content(
            types.Message(chat_id, None, None, None, None, None, None, None, None, None)
        )


# 🔥 НОВЫЙ ОБРАБОТЧИК: Ловит ВСЕ сообщения, если юзер в списке капчи
# (Обязательно должен стоять ВЫШЕ других message_handler)
@bot.message_handler(func=lambda m: m.chat.id in captcha_users)
def handle_captcha_response(message):
    chat_id = message.chat.id
    text = message.text

    # Проверка блокировки (на случай, если она наступила в другом потоке)
    if is_user_blocked(chat_id):
        minutes, seconds = get_remaining_block_time(chat_id)
        bot.send_message(
            chat_id, f"🚫 Гринч тебя запер. Жди: {minutes} мин {seconds} сек."
        )
        return

    if not text:
        bot.send_message(
            chat_id, "🔢 Цифры с картинки. Даже Гринч справился бы быстрее."
        )
        return

    if text == "/start":
        send_captcha(chat_id)
        return

    correct_code = captcha_users.get(chat_id)

    if text.strip() == correct_code:
        # ✅ ВЕРНО
        print(f"✅ Юзер {chat_id} прошел капчу!")
        bot.send_message(
            chat_id, "✅ Доступ разрешен, но ты всё равно не спасёшь Новый год!"
        )

        if chat_id in captcha_users:
            del captcha_users[chat_id]

        # Сбрасываем счетчик попыток при успехе
        if chat_id in captcha_attempts:
            del captcha_attempts[chat_id]

        show_main_menu_content(message)
    else:
        # ❌ НЕВЕРНО
        print(f"⛔️ Юзер {chat_id} ошибся (ввел {text}, надо {correct_code})")

        # Инициализируем счетчик, если его нет
        if chat_id not in captcha_attempts:
            captcha_attempts[chat_id] = {"attempts": 0, "block_until": 0}

        captcha_attempts[chat_id]["attempts"] += 1
        attempts_left = MAX_CAPTCHA_ATTEMPTS - captcha_attempts[chat_id]["attempts"]

        if captcha_attempts[chat_id]["attempts"] >= MAX_CAPTCHA_ATTEMPTS:
            # БЛОКИРОВКА
            block_until = time.time() + CAPTCHA_BLOCK_DURATION
            captcha_attempts[chat_id]["block_until"] = block_until

            # Удаляем из активной проверки (чтобы не спамил картинками),
            # но оставляем в словаре блокировок
            if chat_id in captcha_users:
                del captcha_users[chat_id]

            bot.send_message(
                chat_id,
                f"🚫 <b>Два раза мимо, гений!</b>\n"
                f"Гринч запер тебя на 5 минут.\n"
                f"Возвращайся, когда цифры перестанут тебя пугать.",
                parse_mode="HTML",
            )
        else:
            # ПРЕДУПРЕЖДЕНИЕ
            bot.send_message(
                chat_id,
                f"❌ Опять мимо! Осталось попыток: {attempts_left}.\n"
                f"Попробуй еще раз.",
            )
            # Генерируем новую для безопасности
            send_captcha(chat_id)


@bot.message_handler(commands=["start"])
@anti_flood
def cmd_start(message):
    uid = message.from_user.id
    print(f"🚀 Нажат /start пользователем {uid}")

    # 1. Проверка блокировки
    if is_user_blocked(uid):
        minutes, seconds = get_remaining_block_time(uid)
        bot.send_message(uid, f"🚫 Доступ отобран Гринчем. Осталось: {minutes} мин.")
        return

    # 2. Админа пускаем всегда
    if uid in ADMIN_IDS:
        show_main_menu_content(message)
        return

    # 3. 🔥 ПРАВИЛЬНАЯ ПРОВЕРКА СТАРОГО ЮЗЕРА 🔥
    # Если юзер уже есть в базе — пускаем без капчи
    if check_user_exists(uid):
        print(f"{uid}, старый пользователь… на тебя даже Гринч бросает уважительный взгляд.\n Капча? Забудь!")
        show_main_menu_content(message)
        return

    # 4. Иначе капча
    print("🆕 Отправляем капчу...")
    send_captcha(message.chat.id)


# --- МЕНЮ ---
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    # Кнопки с вашими названиями
    kb.add(types.KeyboardButton("🎒 Забрать подарки"))
    kb.row(types.KeyboardButton("📦 Мои подарки"), types.KeyboardButton("🆘 Поддержка"))
    kb.row(types.KeyboardButton("⭐️ Слухи"), types.KeyboardButton("📜 Правила"))
    return kb


# УБРАЛИ ДЕКОРАТОРЫ ЗДЕСЬ, ЧТОБЫ НЕ БЫЛО КОНФЛИКТА С CMD_START
def show_main_menu_content(message):
    """
    Функция, которая показывает главное меню.
    Вызывается ТОЛЬКО после прохождения капчи или если это Админ.
    """
    # Очистка состояний
    if message.chat.id in admin_state:
        del admin_state[message.chat.id]

    # Сохраняем/обновляем юзера в БД
    username = message.from_user.username
    first_name = message.from_user.first_name
    upsert_user(message.chat.id, username, first_name)

    joke = random.choice(GRINCH_JOKES)
    welcome_text = (
        f"🎄 Привет, {first_name}! 🎁"
        " Добро пожаловать к Гринчу!\n\n"
        "Резервы в случае блокировки ⤵️⤵️⤵️\n"
        "Это все актуальные линки \n\n"
        f"<i>{joke}</i>"
    )
    bot.send_message(
        message.chat.id, welcome_text, reply_markup=main_menu(), parse_mode="HTML"
    )


def send_captcha(chat_id):
    """Генерирует картинку с цифрами и отправляет юзеру"""
    try:
        # 1. Генерируем случайный код
        code = str(random.randint(1000, 9999))

        # 2. Создаем картинку
        image = ImageCaptcha(width=280, height=90)
        data = image.generate(code)

        # 3. Запоминаем правильный ответ в словарь
        captcha_users[chat_id] = code

        # 4. Отправляем фото
        bot.send_photo(
            chat_id,
            data,
            caption="🤖 <b>ПРОВЕРКА НА БОТА</b>\nВведите цифры с картинки:",
            parse_mode="HTML",
        )
        # УБРАЛИ register_next_step_handler — он ненадежен на сервере

    except Exception as e:
        print(f"Ошибка капчи: {e}")
        bot.send_message(chat_id, "Капча сломалась, проходи так.")
        show_main_menu_content(
            types.Message(chat_id, None, None, None, None, None, None, None, None, None)
        )  # Костыль для запуска меню


# 🔥 НОВЫЙ ОБРАБОТЧИК: Ловит ВСЕ сообщения, если юзер в списке капчи
@bot.message_handler(func=lambda m: m.chat.id in captcha_users)
def handle_captcha_response(message):
    chat_id = message.chat.id
    text = message.text

    if not text:  # Если прислали стикер или фото вместо текста
        bot.send_message(chat_id, "🔢 Пожалуйста, введите цифры с картинки.")
        return

    # Если юзер нажал /start во время капчи — генерируем новую
    if text == "/start":
        send_captcha(chat_id)
        return

    # Получаем правильный код из памяти
    correct_code = captcha_users.get(chat_id)

    if text.strip() == correct_code:
        # ✅ ВЕРНО
        bot.send_message(chat_id, "✅ Доступ разрешен!")

        # Удаляем из "тюрьмы" капчи
        if chat_id in captcha_users:
            del captcha_users[chat_id]

        # Показываем меню
        show_main_menu_content(message)
    else:
        # ❌ НЕВЕРНО
        bot.send_message(chat_id, "❌ Неверно! Попробуйте еще раз.")
        send_captcha(chat_id)


@bot.message_handler(commands=["start"])
@anti_flood
@bot.message_handler(commands=["start"])
@anti_flood
def cmd_start(message):
    uid = message.from_user.id
    print(f"🚀 Нажат /start пользователем {uid}")

    # 1. СНАЧАЛА проверяем Админа (чтобы пустить даже если есть бан)
    if uid in ADMIN_IDS:
        # Если админ был в списке капчи - выпускаем
        if uid in captcha_users:
            del captcha_users[uid]
        show_main_menu_content(message)
        return

    # 2. Проверка блокировки для обычных смертных
    if is_user_blocked(uid):
        minutes, seconds = get_remaining_block_time(uid)
        bot.send_message(
            uid,
            f"🚫 Вы заблокированы на 5 минут за ошибки в капче.\n"
            f"Осталось: {minutes} мин {seconds} сек.",
        )
        return

    # 3. Если юзер старый - пускаем (раскомментируйте, если нужно)
    all_users = get_all_users()
    if message.chat.id in all_users:
        show_main_menu_content(message)
        return

    # 4. Иначе капча
    print("🆕 Отправляем капчу...")
    send_captcha(message.chat.id)


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


# --- БЛОКИРОВЩИК (ТЕХ. ПАУЗА) ---
@bot.message_handler(
    func=lambda m: is_maintenance_active() and m.from_user.id not in ADMIN_IDS
)
def maintenance_filter(call_or_message):
    # Определяем ID чата и пользователя
    if isinstance(call_or_message, types.CallbackQuery):
        chat_id = call_or_message.message.chat.id
        # Обязательно отвечаем на колбэк, чтобы кнопка не крутилась
        try:
            bot.answer_callback_query(call_or_message.id, "⛔️ Технические работы!")
        except:
            pass
    else:
        chat_id = call_or_message.chat.id

    text = (
        "🚧 <b>МАГАЗИН НА ТЕХ. ОБСЛУЖИВАНИИ</b> 🚧\n\n"
        "Гринч временно закрыл лавочку, чтобы пересчитать добычу.\n"
        "<i>Возвращайся чуть позже!</i> 🕐"
    )
    try:
        bot.send_message(chat_id, text, parse_mode="HTML")
    except:
        pass
    # Больше ничего не делаем, прерываем обработку для этого юзера


# --- ПОКУПКА ---
@bot.message_handler(func=lambda m: m.text == "🎒 Забрать подарки")
@anti_flood
def handle_buy(message):

    if is_maintenance_active() and message.from_user.id not in ADMIN_IDS:
        return bot.send_message(
            message.chat.id, "⛔️ Магазин закрыт на тех. обслуживание!"
        )

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

    if is_maintenance_active() and call.from_user.id not in ADMIN_IDS:
        return bot.answer_callback_query(
            call.id, "⛔️ Магазин на паузе!", show_alert=True
        )

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

    # --- ИСПРАВЛЕННИЕ ЛОГИКИ КНОПКИ НАЗАД ---
    # Получаем store_id товара, используя ref_id, для корректного возврата
    try:
        from bot.db import execute_query

        res = execute_query(
            "SELECT store_id FROM products WHERE product_id = %s", (ref_id,), fetch=True
        )
        real_store_id = res[0][0] if res else "1"
    except Exception as e:
        # Fallback, если что-то пошло не так
        print(f"Ошибка получения store_id: {e}")
        real_store_id = "1"

    kb.add(
        types.InlineKeyboardButton(
            "🔙 Сбежать", callback_data=f"store_{real_store_id}_0"
        )
    )
    # ----------------------------------------

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
    if is_maintenance_active() and call.from_user.id not in ADMIN_IDS:
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        return bot.answer_callback_query(
            call.id, "⛔️ ОШИБКА: Магазин закрыт на тех. работы!", show_alert=True
        )
    try:
        bot.answer_callback_query(call.id)
    except:
        pass

    uid = call.from_user.id

    # Умный лимит
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
            f"❌ ЛИМИТ. У тебя уже {unpaid} неоплаченных покупок.\nСначала плати, потом заходи опять!",
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
            uid, f"❌ В районе {target_info['address']} товар украден. Выберите другой."
        )

    details = get_product_details_by_id(real_pid)
    temp_oid = f"ORD-{int(time.time())}-{uid}"

    # Анимация
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

    raw_username = call.from_user.username
    username = f"@{raw_username}" if raw_username else "Нет ника"

    # 2. Передаем его в функцию БД в
    real_oid = add_order(
        user_id=uid,
        user_username=username,  # <--- ВАЖНО: передаем юзернейм
        product_id=real_pid,
        price_usd=details["price_usd"],
        pickup_address=details["address"],
        order_id=temp_oid,
        oxapay_track_id=track_id,
        payment_url=pay_url,
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
        f" Оплатить на карту можно\n с помощью 👉 <a href='https://t.me/braumilka'>@braumilka</a>\n\n"
        f"🔴 <b>ОПЛАЧИВАТЬ ТОЧНУЮ СУММУ!!! Внимательно </b>"
        f"⚠️ <i>Фото и описание свалятся тебе автоматически после оплаты… если уж так надо.</i>\n"
        f"✅Жми кнопку оплатить\n\n"
        f"Выбирай  Usdt bep 20\n"
        f"(Или как удобно в этой сети просто маленькая комса)"
    )

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Оплатить", url=pay_url))
    kb.add(types.InlineKeyboardButton("🔙 Отмена", callback_data=f"pname_{target_id}"))

    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass

    try:
        bot.send_photo(uid, ORDER_IMG, caption=text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        # Если с фото проблема — шлем текст
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
@bot.callback_query_handler(func=lambda c: c.data.startswith("check_"))
def check_pay(call):
    oid = call.data.split("_")[1]

    # 1. Быстрая проверка
    order = get_order(oid)
    if not order:
        return bot.answer_callback_query(call.id, "Заказ не найден 🤷‍♂️")

    if order["status"] == "paid":
        try:
            bot.edit_message_reply_markup(
                call.message.chat.id, call.message.message_id, reply_markup=None
            )
        except:
            pass
        return bot.answer_callback_query(
            call.id, "✅ Этот заказ уже был выдан!", show_alert=True
        )

    bot.answer_callback_query(call.id, "Связываюсь с банком... ⏳")

    # 2. Проверка оплаты через API
    if verify_payment_via_api(order.get("oxapay_track_id")):

        # 3. Финальная защита от повторного нажатия
        fresh_order_check = get_order(oid)
        if fresh_order_check["status"] == "paid":
            return bot.send_message(call.from_user.id, "⚠️ Вы уже получили этот товар.")

        # 4. БЛОКИРУЕМ ЗАКАЗ И ТОВАР
        update_order(oid, status="paid", delivery_status="delivered")
        mark_product_as_sold(order["product_id"])

        # ======================================================
        # 🚀 НОВАЯ ФИШКА: КИКАЕМ КОНКУРЕНТОВ
        # ======================================================
        try:
            # Ищем всех, кто сидит на ЭТОМ ЖЕ товаре и ждет оплаты, КРОМЕ текущего победителя
            losers = execute_query(
                "SELECT order_id, user_id FROM orders WHERE product_id = %s AND status = 'waiting_payment' AND order_id != %s;",
                (order["product_id"], oid),
                fetch=True,
            )

            if losers:
                # Массово отменяем их заказы в базе
                execute_query(
                    "UPDATE orders SET status = 'cancelled' WHERE product_id = %s AND status = 'waiting_payment' AND order_id != %s;",
                    (order["product_id"], oid),
                )

                # Пишем им грустную новость
                for loser_oid, loser_uid in losers:
                    try:
                        bot.send_message(
                            loser_uid,
                            f"😈🤮 <b>Хе-хе-хе! Твой заказ {loser_oid} превратился в пыль!</b>\n"
                            f"Пока ты копался, кто-то более наглый и быстрый увел добычу прямо у тебя из-под носа!\n"
                            f"Смирись с поражением и выбери что-то другое (если успеешь, ха-ха!).",
                            parse_mode="HTML",
                        )
                    except:
                        pass  # Если юзер заблочил бота
        except Exception as e:
            print(f"Ошибка при кике конкурентов: {e}")
        # ======================================================

        # 5. Получаем данные товара для выдачи
        details = get_product_details_by_id(order["product_id"])

        if not details:
            return bot.send_message(
                call.from_user.id,
                "🆘 Оплата прошла, но товар не найден! Срочно пишите админу.",
            )

        # 6. Выдаем товар
        msg = (
            f"✅ <b>Оплата получена!</b>\n"
            f"📦 {details['product_name']}\n"
            f"📍 {details['delivery_text']}\n\n"
            f"<i>Спасибо за покупку! Заглядывайте еще.</i> 😈"
        )
        try:
            send_product_visuals(call.from_user.id, details["file_path"], msg)
            bot.edit_message_text(
                f"✅ Заказ {oid} успешно выдан.",
                call.message.chat.id,
                call.message.message_id,
            )

            # Уведомление админу
            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(
                        admin_id,
                        f"💰 <b>ПРОДАЖА!</b> {details['price_usd']}$ | {details['product_name']}",
                        parse_mode="HTML",
                    )
                except:
                    pass

        except Exception as e:
            bot.send_message(
                call.from_user.id,
                f"😱 Оплата прошла, но я не смог отправить фото: {e}\nПиши админу!",
            )
    else:
        bot.send_message(
            call.from_user.id, "❌ Оплаты пока нет. Попробуйте через минуту."
        )


# --- АДМИНКА ---
@bot.message_handler(commands=["admin"])
def admin_panel(message):

    if message.from_user.id in admin_state:
        del admin_state[message.from_user.id]

    if message.from_user.id not in ADMIN_IDS:
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Добавить товар", "✏️ Изменить товар")
    kb.add("📢 Рассылка", "🎁 Выдать товар")
    kb.add("💾 Бэкап БД", "📥 Импорт (CSV)")
    kb.add("📊 Статистика", "📸 Генератор ID")
    kb.add("🛠 Тех. пауза", "🏭 Конвейер")
    kb.add("🔙 Меню")
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

    # ИСПРАВЛЕНО: Очистка старого состояния перед началом
    if m.from_user.id in admin_state:
        del admin_state[m.from_user.id]

    stores = get_all_stores()
    kb = types.InlineKeyboardMarkup()
    for s in stores:
        kb.add(
            types.InlineKeyboardButton(
                s["title"], callback_data=f"aadd_s_{s['store_id']}"
            )
        )
    bot.send_message(m.chat.id, "Куда?", reply_markup=kb)


# Вспомогательная клавиатура "Назад"
def get_back_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add("🔙 Назад")
    return kb


@bot.callback_query_handler(func=lambda c: c.data.startswith("aadd_s_"))
def aadd_step1(c):
    # Начало: сохраняем ID магазина
    sid = c.data.split("_")[2]
    admin_state[c.from_user.id] = {"sid": sid}

    # Спрашиваем Название
    msg = bot.send_message(
        c.message.chat.id, "1️⃣ Введите Название товара:", reply_markup=get_back_kb()
    )
    bot.register_next_step_handler(msg, aadd_step2)


def aadd_step2(m):
    # Если нажали Назад -> Выход в меню
    if m.text == "🔙 Назад":
        return admin_panel(m)

    admin_state[m.from_user.id]["name"] = m.text
    msg = bot.send_message(
        m.chat.id, "2️⃣ Введите Цену (в USD, только число):", reply_markup=get_back_kb()
    )
    bot.register_next_step_handler(msg, aadd_step3)


def aadd_step3(m):
    uid = m.from_user.id
    # Если нажали Назад -> Возвращаемся к вводу Имени
    if m.text == "🔙 Назад":
        msg = bot.send_message(
            m.chat.id, "1️⃣ Введите Название товара:", reply_markup=get_back_kb()
        )
        bot.register_next_step_handler(msg, aadd_step2)
        return

    try:
        admin_state[uid]["price"] = float(m.text.replace(",", "."))
        msg = bot.send_message(
            m.chat.id, "3️⃣ Введите Район/Адрес (виден всем):", reply_markup=get_back_kb()
        )
        bot.register_next_step_handler(msg, aadd_step4)
    except:
        msg = bot.send_message(
            m.chat.id,
            "❌ Ошибка! Нужно ввести число (например 10.5). Попробуй еще раз:",
            reply_markup=get_back_kb(),
        )
        bot.register_next_step_handler(m, aadd_step3)


def aadd_step4(m):
    # Если нажали Назад -> Возвращаемся к вводу Цены
    if m.text == "🔙 Назад":
        msg = bot.send_message(
            m.chat.id, "2️⃣ Введите Цену (в USD):", reply_markup=get_back_kb()
        )
        bot.register_next_step_handler(msg, aadd_step3)
        return

    admin_state[m.from_user.id]["addr"] = m.text
    msg = bot.send_message(
        m.chat.id,
        "4️⃣ Введите Секретное описание (Товар/Клад):",
        reply_markup=get_back_kb(),
    )
    bot.register_next_step_handler(msg, aadd_step5)


def aadd_step5(m):
    # Если нажали Назад -> Возвращаемся к вводу Адреса
    if m.text == "🔙 Назад":
        msg = bot.send_message(
            m.chat.id, "3️⃣ Введите Район/Адрес:", reply_markup=get_back_kb()
        )
        bot.register_next_step_handler(msg, aadd_step4)
        return

    admin_state[m.from_user.id]["desc"] = m.text
    admin_state[m.from_user.id]["photos"] = []

    # Для фото клавиатура немного другая
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row("✅ Готово, сохранить", "🔙 Назад")

    msg = bot.send_message(
        m.chat.id,
        "5️⃣ Отправьте **Фото товара** (по одному):",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(msg, aadd_photo_loop)


def aadd_photo_loop(m):
    uid = m.from_user.id

    # Логика кнопки НАЗАД на этапе фото
    if m.text == "🔙 Назад":
        # Если фото еще не добавляли - возвращаемся к описанию
        if not admin_state[uid]["photos"]:
            msg = bot.send_message(
                m.chat.id, "4️⃣ Введите Секретное описание:", reply_markup=get_back_kb()
            )
            bot.register_next_step_handler(msg, aadd_step5)
        else:
            # Если фото уже были, очищаем их и просим заново
            admin_state[uid]["photos"] = []
            kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            kb.row("✅ Готово, сохранить", "🔙 Назад")
            msg = bot.send_message(
                m.chat.id,
                "🗑 Фото сброшены. Отправьте фото заново или нажмите Назад еще раз для шага назад:",
                reply_markup=kb,
            )
            bot.register_next_step_handler(msg, aadd_photo_loop)
        return

    if m.content_type == "photo":
        admin_state[uid]["photos"].append(m.photo[-1].file_id)
        count = len(admin_state[uid]["photos"])

        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.row("✅ Готово, сохранить", "🔙 Назад")

        msg = bot.send_message(
            m.chat.id,
            f"📸 Принято фото #{count}. Шли еще или жми Готово:",
            reply_markup=kb,
        )
        bot.register_next_step_handler(msg, aadd_photo_loop)
        return

    elif m.text == "✅ Готово, сохранить":
        if not admin_state[uid]["photos"]:
            kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            kb.row("✅ Готово, сохранить", "🔙 Назад")
            msg = bot.send_message(
                m.chat.id, "⚠️ Нужно добавить хотя бы одно фото!", reply_markup=kb
            )
            bot.register_next_step_handler(msg, aadd_photo_loop)
            return
        aadd_finish(m)
    else:
        msg = bot.send_message(m.chat.id, "Я жду картинку или нажатие кнопки.")
        bot.register_next_step_handler(m, aadd_photo_loop)


def aadd_finish(m):
    d = admin_state[m.from_user.id]
    photos_str = ",".join(d["photos"])
    # Проверка на наличие ключей на всякий случай
    try:
        insert_product(
            d["sid"], d["name"], d["price"], d["desc"], photos_str, d["addr"]
        )
        bot.send_message(
            m.chat.id,
            "✅ Товар успешно добавлен!",
            reply_markup=types.ReplyKeyboardRemove(),
        )
    except Exception as e:
        bot.send_message(m.chat.id, f"❌ Ошибка при сохранении: {e}")

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
        add_order(uid, "GiftUser", pid, 0, "Gift", fake_oid, "GIFT", "GIFT")
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
            # --- НАЧАЛО ИЗМЕНЕНИЙ ---
            # 1. Берем адрес. Если его нет в базе, пишем пустую строку
            addr = p.get("address", "")
            # 2. Обрезаем адрес, если он длиннее 10 букв (чтобы кнопка не была гигантской)
            short_addr = addr[:10] + ".." if len(addr) > 10 else addr

            # 3. Формируем текст кнопки: Название | Район | #ID
            # Пример: ❌ iPhone 15 | 📍Центр.. | #145
            btn_text = f"❌ {p['name']} | 📍{short_addr} | #{p['product_id']}"

            kb.add(
                types.InlineKeyboardButton(
                    btn_text,
                    callback_data=f"adel_do_{p['product_id']}",
                )
            )
            # --- КОНЕЦ ИЗМЕНЕНИЙ ---

        # Кнопка назад к категориям удаления
        kb.add(
            types.InlineKeyboardButton("🔙 Назад", callback_data="adel_back_to_cats")
        )

        bot.edit_message_text(
            "Выберите товар для удаления (В кнопках: Имя | Район | ID):",
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

    if not prods:
        return bot.answer_callback_query(c.id, "Категория пуста!", show_alert=True)

    kb = types.InlineKeyboardMarkup()
    for p in prods:
        # --- НАЧАЛО ИЗМЕНЕНИЙ ---
        # То же самое: берем адрес и ID
        addr = p.get("address", "")
        short_addr = addr[:10] + ".." if len(addr) > 10 else addr

        # Текст кнопки: ✏️ Имя | Район | #ID
        btn_text = f"✏️ {p['name']} | 📍{short_addr} | #{p['product_id']}"

        kb.add(
            types.InlineKeyboardButton(
                btn_text, callback_data=f"edit_p_{p['product_id']}"
            )
        )
        # --- КОНЕЦ ИЗМЕНЕНИЙ ---

    # Добавляем кнопку назад в меню категорий (опционально, но удобно)
    kb.add(
        types.InlineKeyboardButton("🔙 Назад к категориям", callback_data="cmd_start")
    )  # Или верните в edit_start

    bot.edit_message_text(
        "Какой товар изменить? (В кнопках: Имя | Район | ID)",
        c.message.chat.id,
        c.message.message_id,
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("edit_p_"))
def edit_field(c):
    pid = c.data.split("_")[2]
    admin_state[c.from_user.id] = {"edit_pid": pid}

    details = get_product_details_by_id(pid)
    if not details:
        return bot.answer_callback_query(c.id, "Товар не найден (возможно, удален).")

    info = (
        f"📦 <b>{details['product_name']}</b>\n"
        f"📍 {details['address']}\n"
        f"💵 {details['price_usd']} $\n"
    )

    kb = types.InlineKeyboardMarkup()
    # Основные поля
    kb.add(
        types.InlineKeyboardButton("Название", callback_data="edf_name"),
        types.InlineKeyboardButton("Цена", callback_data="edf_price_usd"),
    )
    kb.add(
        types.InlineKeyboardButton("Адрес", callback_data="edf_address"),
    )

    # НОВЫЕ КНОПКИ: Клад, Фото, Удалить
    kb.add(
        types.InlineKeyboardButton("Изменить Клад", callback_data="edf_delivery_text")
    )
    kb.add(
        types.InlineKeyboardButton("📸 ИЗМЕНИТЬ ФОТО", callback_data="edf_file_path")
    )

    # Кнопка удаления (красная, если бы можно было красить, но визуально отделена)
    kb.add(
        types.InlineKeyboardButton(
            "🗑 УДАЛИТЬ ТОВАР", callback_data=f"del_from_edit_{pid}"
        )
    )

    # Кнопка назад к списку
    # (Нужно знать store_id, попробуем достать его)
    try:
        res = execute_query(
            "SELECT store_id FROM products WHERE product_id = %s", (pid,), fetch=True
        )
        sid = res[0][0] if res else "1"
    except:
        sid = "1"

    kb.add(
        types.InlineKeyboardButton("🔙 Назад к списку", callback_data=f"edit_s_{sid}")
    )

    bot.edit_message_text(
        f"{info}\n\nЧто меняем?",
        c.message.chat.id,
        c.message.message_id,
        reply_markup=kb,
        parse_mode="HTML",
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("edf_"))
def edit_val(c):
    field = c.data.replace("edf_", "")
    admin_state[c.from_user.id]["edit_field"] = field

    text = "Введите новое значение:"
    if field == "file_path":
        text = "📸 Пришлите НОВОЕ фото (или несколько):"
    elif field == "delivery_text":
        text = "📦 Введите новый текст клада:"

    msg = bot.send_message(c.message.chat.id, text)
    # Для фото нужен отдельный обработчик, но используем общий edit_save, он справится
    bot.register_next_step_handler(msg, edit_save)


def edit_save(m):
    uid = m.from_user.id
    if uid not in admin_state:
        return

    d = admin_state[uid]
    field = d["edit_field"]

    val = ""

    # Обработка ФОТО
    if field == "file_path":
        if m.content_type == "photo":
            # Берем ID фото
            val = m.photo[-1].file_id
        else:
            return bot.send_message(
                m.chat.id, "❌ Это не фото. Попробуйте снова через меню."
            )
    else:
        # Обработка ТЕКСТА
        if not m.text:
            return bot.send_message(m.chat.id, "❌ Ожидался текст.")
        val = m.text

        # Проверка цены
        if field == "price_usd":
            try:
                val = float(val.replace(",", "."))
            except:
                return bot.send_message(
                    m.chat.id, "❌ Ошибка. Цена должна быть числом (например 10.5)."
                )

    update_product_field(d["edit_pid"], field, val)

    bot.send_message(m.chat.id, "✅ Успешно обновлено!")


@bot.callback_query_handler(func=lambda c: c.data.startswith("del_from_edit_"))
def delete_from_edit(c):
    pid = c.data.split("_")[3]

    # 1. Узнаем ID магазина перед удалением, чтобы вернуться назад
    sid = "1"
    try:
        res = execute_query(
            "SELECT store_id FROM products WHERE product_id = %s", (pid,), fetch=True
        )
        if res:
            sid = res[0][0]
    except:
        pass

    # 2. Удаляем
    delete_product(pid)
    bot.answer_callback_query(c.id, "Товар удален.")

    # 3. Возвращаем к списку товаров этой категории
    # Вызываем функцию списка товаров, подменяя callback.data
    c.data = f"edit_s_{sid}"
    edit_list_prods(c)


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
        errors = 0  # ИСПРАВЛЕНО: Считаем ошибки

        for row in reader:
            if len(row) < 6:
                continue
            # Разбираем строку
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
                except Exception as e:
                    # ИСПРАВЛЕНО: Логируем ошибку в консоль и считаем её
                    print(f"Ошибка импорта строки {row}: {e}")
                    errors += 1
            else:
                errors += 1  # Магазин не найден

        # ИСПРАВЛЕНО: Показываем статистику ошибок
        bot.send_message(
            message.chat.id,
            f"✅ <b>Импорт завершен!</b>\n"
            f"➕ Добавлено: {success}\n"
            f"⚠️ Ошибок/Пропусков: {errors}",
            parse_mode="HTML",
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Критическая ошибка файла: {e}")


# --- ГЕНЕРАТОР ID ДЛЯ EXCEL ---


@bot.message_handler(func=lambda m: m.text == "📸 Генератор ID")
def photo_gen_instruction(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    text = (
        "📸 <b>Режим генерации ID для Excel</b>\n\n"
        "1. Просто отправь мне фото (или выдели сразу 2-10 штук и отправь как альбом).\n"
        "2. Я подожду пару секунд, соберу их в кучу.\n"
        "3. Выдам тебе готовую строку кодов через запятую.\n\n"
        "<i>Эту строку копируй и вставляй в колонку File_ID в Excel.</i>"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML")


def process_photo_buffer(chat_id, user_id):
    """Эта функция запускается через 1.5 сек после последнего фото"""
    # Если буфер пуст - выходим
    if user_id not in photo_buffer or not photo_buffer[user_id]:
        return

    # Берем список накопленных ID
    file_ids = photo_buffer[user_id]
    count = len(file_ids)

    # 1. Формируем заголовок сообщения
    msg = (
        f"📦 <b>Пакет обработан!</b>\n"
        f"Загружено фото: {count} шт.\n"
        f"👇 <i>Нажимай на код, чтобы скопировать ID для конкретного товара:</i>\n\n"
    )

    # 2. Добавляем КАЖДОЕ фото отдельным блоком с номером
    # enumerate(file_ids, 1) начинает нумерацию с 1
    for i, fid in enumerate(file_ids, 1):
        msg += f"🖼 <b>Фото №{i}</b>\n<code>{fid}</code>\n\n"

    # 3. (Опционально) Добавляем общую строку в конце, вдруг пригодится для галереи
    combined = ",".join(file_ids)
    if count > 1:
        msg += f"📚 <b>Весь пак (если надо 1 товар с {count} фото):</b>\n<code>{combined}</code>"

    # Очищаем буфер
    del photo_buffer[user_id]
    if user_id in photo_timers:
        del photo_timers[user_id]

    # Отправляем
    try:
        # Telegram имеет лимит на длину сообщения.
        # Если фоток очень много (больше 10-15), сообщение может не влезть.
        # Поэтому на всякий случай разбиваем, если msg слишком длинный.
        if len(msg) > 4000:
            # Если слишком длинно - шлем кусками (упрощенно: по 1 фото)
            bot.send_message(
                chat_id, "📦 <b>Пакет большой, шлю частями:</b>", parse_mode="HTML"
            )
            for i, fid in enumerate(file_ids, 1):
                bot.send_message(
                    chat_id,
                    f"🖼 <b>Фото №{i}</b>\n<code>{fid}</code>",
                    parse_mode="HTML",
                )
        else:
            bot.send_message(chat_id, msg, parse_mode="HTML")

    except Exception as e:
        bot.send_message(chat_id, f"Ошибка отправки: {e}")


@bot.message_handler(content_types=["photo"])
def universal_photo_handler(message):
    uid = message.from_user.id
    if uid not in ADMIN_IDS:
        return

    # 1. ПРОВЕРКА: Если мы в режиме КОНВЕЙЕРА (добавляем товары)
    if uid in admin_state and admin_state[uid].get("waiting_photos"):
        fid = message.photo[-1].file_id
        admin_state[uid]["photos"].append(fid)

        if uid in photo_timers:
            photo_timers[uid].cancel()

        t = threading.Timer(2.0, pipe_process_buffer, args=[message.chat.id, uid])
        t.start()
        photo_timers[uid] = t
        return

    # 2. ИНАЧЕ: Работает режим ГЕНЕРАТОРА ID (просто показывает коды)
    # (Код из предыдущего ответа про process_photo_buffer)

    fid = message.photo[-1].file_id
    if uid not in photo_buffer:
        photo_buffer[uid] = []
    photo_buffer[uid].append(fid)

    if uid in photo_timers:
        photo_timers[uid].cancel()

    t = threading.Timer(1.5, process_photo_buffer, args=[message.chat.id, uid])
    t.start()
    photo_timers[uid] = t


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


# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ СОЗДАНИЯ БЭКАПА ---
def create_backup_zip():
    tables = ["users", "orders", "products", "stores"]
    zip_buffer = io.BytesIO()
    try:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for table in tables:
                headers, rows = get_table_data(table)
                if not headers:
                    continue
                csv_buffer = io.StringIO()
                csv_buffer.write("\ufeff")  # BOM для Excel
                writer = csv.writer(csv_buffer, delimiter=";")
                writer.writerow(headers)
                writer.writerows(rows)
                zip_file.writestr(f"{table}.csv", csv_buffer.getvalue())
        zip_buffer.seek(0)
        return zip_buffer
    except:
        return None


# --- ФОНОВАЯ ЗАДАЧА АВТО-БЭКАПА ---
def auto_backup_loop():
    while True:
        # 1. Ждем 1 час перед следующей проверкой (чтобы не грузить базу)
        time.sleep(3600)

        # Получаем текущую дату
        today = datetime.now().strftime("%Y-%m-%d")

        try:
            # 2. Проверяем в БД, был ли уже бэкап сегодня
            res = execute_query(
                "SELECT setting_value FROM bot_settings WHERE setting_key = 'last_backup_date';",
                fetch=True,
            )
            last_date = res[0][0] if res else ""

            # Если сегодня уже делали — пропускаем
            if last_date == today:
                continue

            # 3. Если не делали — создаем бэкап
            zip_file = create_backup_zip()
            if zip_file:
                filename = f"AUTO_BACKUP_{today}.zip"

                # Рассылаем админам
                for admin_id in ADMIN_IDS:
                    try:
                        zip_file.seek(0)
                        bot.send_document(
                            admin_id,
                            zip_file,
                            caption=f"🕒 <b>Ежедневный авто-бэкап</b>\n📅 {today}",
                            visible_file_name=filename,
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        print(f"Ошибка отправки бэкапа {admin_id}: {e}")

                # 4. ЗАПИСЫВАЕМ ДАТУ В БД (Чтобы другие потоки не отправили второй раз)
                execute_query(
                    """
                    INSERT INTO bot_settings (setting_key, setting_value) 
                    VALUES ('last_backup_date', %s) 
                    ON CONFLICT (setting_key) DO UPDATE 
                    SET setting_value = EXCLUDED.setting_value;
                """,
                    (today,),
                )

                print(f"✅ Авто-бэкап за {today} выполнен.")

        except Exception as e:
            print(f"Backup loop error: {e}")


# ==========================================
#          ЛОГИКА КОНВЕЙЕРА (PIPELINE)
# ==========================================


@bot.message_handler(func=lambda m: m.text == "🏭 Конвейер")
def pipeline_start(m):
    if m.from_user.id not in ADMIN_IDS:
        return

    # Очищаем состояние
    admin_state[m.from_user.id] = {"mode": "pipeline", "photos": []}

    msg = bot.send_message(
        m.chat.id,
        "🏭 <b>Режим Конвейера</b>\n\n"
        "Мы создадим много одинаковых товаров, отличающихся ТОЛЬКО фото.\n"
        "1️⃣ Введите количество товаров (число):",
        reply_markup=get_back_kb(),
        parse_mode="HTML",
    )
    bot.register_next_step_handler(msg, pipe_step_count)


def pipe_step_count(m):
    if m.text == "🔙 Назад":
        return admin_panel(m)

    try:
        count = int(m.text)
        admin_state[m.from_user.id]["count"] = count
    except:
        msg = bot.send_message(m.chat.id, "❌ Введите число (например: 10).")
        return bot.register_next_step_handler(msg, pipe_step_count)

    # Выбор магазина
    stores = get_all_stores()
    kb = types.InlineKeyboardMarkup()
    for s in stores:
        kb.add(
            types.InlineKeyboardButton(
                s["title"], callback_data=f"pipe_s_{s['store_id']}"
            )
        )

    bot.send_message(m.chat.id, "2️⃣ Выберите категорию (Магазин):", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("pipe_s_"))
def pipe_step_store(c):
    sid = c.data.split("_")[2]
    admin_state[c.from_user.id]["sid"] = sid

    msg = bot.send_message(
        c.message.chat.id, "3️⃣ Введите ОБЩЕЕ Название:", reply_markup=get_back_kb()
    )
    bot.register_next_step_handler(msg, pipe_step_name)


def pipe_step_name(m):
    if m.text == "🔙 Назад":
        return admin_panel(m)
    admin_state[m.from_user.id]["name"] = m.text

    msg = bot.send_message(
        m.chat.id, "4️⃣ Введите ОБЩУЮ Цену (число):", reply_markup=get_back_kb()
    )
    bot.register_next_step_handler(msg, pipe_step_price)


def pipe_step_price(m):
    if m.text == "🔙 Назад":
        return admin_panel(m)
    try:
        price = float(m.text.replace(",", "."))
        admin_state[m.from_user.id]["price"] = price
    except:
        msg = bot.send_message(m.chat.id, "❌ Нужно число. Попробуй еще раз:")
        return bot.register_next_step_handler(msg, pipe_step_price)

    msg = bot.send_message(
        m.chat.id, "5️⃣ Введите ОБЩИЙ Район/Адрес:", reply_markup=get_back_kb()
    )
    bot.register_next_step_handler(msg, pipe_step_addr)


def pipe_step_addr(m):
    if m.text == "🔙 Назад":
        return admin_panel(m)
    admin_state[m.from_user.id]["addr"] = m.text

    msg = bot.send_message(
        m.chat.id,
        "6️⃣ Введите ОБЩЕЕ Секретное описание (Клад):\n"
        "<i>(Если у каждого клада свое описание - лучше используйте CSV импорт. "
        "Здесь описание будет одинаковым для всех, разница только в фото).</i>",
        reply_markup=get_back_kb(),
        parse_mode="HTML",
    )
    bot.register_next_step_handler(msg, pipe_step_desc)


def pipe_step_desc(m):
    if m.text == "🔙 Назад":
        return admin_panel(m)
    uid = m.from_user.id
    admin_state[uid]["desc"] = m.text

    count = admin_state[uid]["count"]

    # Инструкция по фото
    bot.send_message(
        m.chat.id,
        f"🏁 <b>ФИНАЛ: Загрузка фото</b>\n\n"
        f"Я жду от тебя <b>{count} фотографий</b>.\n"
        f"Просто выдели их в галерее и отправь (можно альбомом).\n"
        f"Я автоматически создам {count} товаров, прикрепив к каждому по 1 фото.",
        reply_markup=get_back_kb(),  # Можно нажать назад если передумал
        parse_mode="HTML",
    )
    # Переводим бота в режим ожидания фото для конвейера
    admin_state[uid]["waiting_photos"] = True


# --- ОБРАБОТЧИК ФОТО ДЛЯ КОНВЕЙЕРА ---
def pipe_process_buffer(chat_id, user_id):
    """Срабатывает, когда поток фото прекратился. Выводит ПРОВЕРКУ."""
    if user_id not in admin_state or "photos" not in admin_state[user_id]:
        return

    data = admin_state[user_id]
    photos = data["photos"]
    target_count = data["count"]
    received_count = len(photos)

    if not photos:
        return

    # Формируем текст проверки
    warning = ""
    if received_count != target_count:
        warning = (
            f"\n⚠️ <b>ВНИМАНИЕ:</b> Вы хотели {target_count}, а фото {received_count}!\n"
        )

    msg = (
        f"🔍 <b>ПРОВЕРКА КОНВЕЙЕРА</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"📦 <b>Товар:</b> {data['name']}\n"
        f"💰 <b>Цена:</b> {data['price']} $\n"
        f"📍 <b>Район:</b> {data['addr']}\n"
        f"📝 <b>Описание:</b> {data['desc'][:20]}...\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"📸 <b>Загружено фото:</b> {received_count} шт.\n"
        f"{warning}\n"
        f"Создать {received_count} товаров?"
    )

    # Кнопки подтверждения
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            f"✅ Создать ({received_count} шт)", callback_data="pipe_confirm"
        )
    )
    kb.add(types.InlineKeyboardButton("❌ Отмена / Сброс", callback_data="pipe_cancel"))

    bot.send_message(chat_id, msg, reply_markup=kb, parse_mode="HTML")


@bot.callback_query_handler(func=lambda c: c.data == "pipe_confirm")
def pipe_finalize_creation(c):
    uid = c.from_user.id
    chat_id = c.message.chat.id

    if uid not in admin_state or "photos" not in admin_state[uid]:
        return bot.answer_callback_query(c.id, "❌ Данные устарели. Начните заново.")

    data = admin_state[uid]
    photos = data["photos"]

    bot.edit_message_text(
        "⏳ <b>Создаю товары...</b>", chat_id, c.message.message_id, parse_mode="HTML"
    )

    success = 0
    # Цикл создания товаров (теперь он тут)
    for file_id in photos:
        try:
            insert_product(
                data["sid"],
                data["name"],
                data["price"],
                data["desc"],
                file_id,
                data["addr"],
            )
            success += 1
        except Exception as e:
            print(f"Error inserting pipe prod: {e}")

    # Финальное сообщение
    bot.send_message(
        chat_id,
        f"✅ <b>Конвейер успешно завершен!</b>\n\n"
        f"🎉 Создано товаров: <b>{success}</b>\n"
        f"📂 Категория: {data['name']}",
        parse_mode="HTML",
    )

    # Очистка
    if uid in admin_state:
        del admin_state[uid]
    if uid in photo_timers:
        del photo_timers[uid]

    # Возврат в меню
    try:
        # Небольшой хак, чтобы вызвать меню без message
        m_fake = types.Message(
            chat_id, None, None, None, None, None, None, None, None, None
        )
        m_fake.from_user = types.User(uid, False, "admin")
        m_fake.chat = types.Chat(chat_id, "private")
        admin_panel(m_fake)
    except:
        pass


@bot.callback_query_handler(func=lambda c: c.data == "pipe_cancel")
def pipe_cancel_creation(c):
    uid = c.from_user.id

    # Очистка
    if uid in admin_state:
        del admin_state[uid]
    if uid in photo_timers:
        del photo_timers[uid]

    bot.edit_message_text(
        "❌ <b>Конвейер отменен.</b> Товары не созданы.",
        c.message.chat.id,
        c.message.message_id,
        parse_mode="HTML",
    )

    # Возврат в меню
    m_fake = types.Message(
        c.message.chat.id, None, None, None, None, None, None, None, None, None
    )
    m_fake.from_user = types.User(uid, False, "admin")
    m_fake.chat = types.Chat(c.message.chat.id, "private")
    admin_panel(m_fake)


@bot.message_handler(content_types=["photo"])
def handle_pipeline_photos(message):
    uid = message.from_user.id
    if uid not in ADMIN_IDS:
        return

    # Проверяем, в режиме ли мы конвейера
    if uid in admin_state and admin_state[uid].get("waiting_photos"):

        # Сохраняем фото
        fid = message.photo[-1].file_id
        admin_state[uid]["photos"].append(fid)

        # Логика таймера (ждем пока перестанут сыпаться фото)
        if uid in photo_timers:
            photo_timers[uid].cancel()

        t = threading.Timer(2.0, pipe_process_buffer, args=[message.chat.id, uid])
        t.start()
        photo_timers[uid] = t

    else:
        # Если не конвейер - отдаем управление другим функциям (генератору ID и т.д.)
        # Вам нужно убедиться, что handle_photos_smart (из прошлого ответа) не перехватывает это
        # Лучше всего объединить их или проверять state.

        # Если у вас стоит handle_photos_smart, добавьте туда проверку:
        # if uid in admin_state and admin_state[uid].get("waiting_photos"): return

        # А пока просто вызовем старую логику показа ID если она нужна
        # get_photo_id_helper(message)
        pass


# ЗАПУСК ПОТОКА БЭКАПА (Вставьте эту строку один раз, чтобы она сработала при старте)
threading.Thread(target=auto_backup_loop, daemon=True).start()

# --- УПРАВЛЕНИЕ ТЕХ. ПАУЗОЙ ---


@bot.message_handler(func=lambda m: m.text == "🛠 Тех. пауза")
def maintenance_menu(message):
    if message.from_user.id not in ADMIN_IDS:
        return

    # Проверяем текущий статус
    status_text = (
        "🔴 ВКЛЮЧЕНА (Магазин закрыт)"
        if is_maintenance_active()
        else "🟢 ВЫКЛЮЧЕНА (Магазин работает)"
    )

    kb = types.InlineKeyboardMarkup()
    if is_maintenance_active():
        # Если включена - кнопка выключить
        kb.add(
            types.InlineKeyboardButton("🟢 ОТКРЫТЬ МАГАЗИН", callback_data="maint_off")
        )
    else:
        # Если выключена - кнопка включить с подтверждением
        kb.add(
            types.InlineKeyboardButton("🔴 ЗАКРЫТЬ МАГАЗИН", callback_data="maint_ask")
        )

    bot.send_message(
        message.chat.id,
        f"🛠 <b>Статус тех. паузы:</b>\n{status_text}",
        reply_markup=kb,
        parse_mode="HTML",
    )


@bot.callback_query_handler(func=lambda c: c.data == "maint_ask")
def maintenance_ask(c):
    # Спрашиваем подтверждение
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Да, закрыть доступ", callback_data="maint_on"))
    kb.add(types.InlineKeyboardButton("Нет, отмена", callback_data="maint_cancel"))

    bot.edit_message_text(
        "⚠️ <b>Вы уверены?</b>\nПользователи не смогут ничего купить, пока вы не отключите паузу.",
        c.message.chat.id,
        c.message.message_id,
        reply_markup=kb,
        parse_mode="HTML",
    )


@bot.callback_query_handler(func=lambda c: c.data == "maint_on")
def maintenance_on(c):
    # 1. Включаем режим (пишем в БД)
    set_maintenance_mode(True)

    # 2. Логика отмены заказов
    canceled_count = 0
    try:
        pending_orders = execute_query(
            "SELECT order_id, user_id FROM orders WHERE status = 'waiting_payment';",
            fetch=True,
        )
        execute_query(
            "UPDATE orders SET status = 'cancelled' WHERE status = 'waiting_payment';"
        )

        if pending_orders:
            for row in pending_orders:
                oid, uid = row
                try:
                    bot.send_message(
                        uid,
                        f"⛔️ Заказ {oid} отменен из-за тех. работ.",
                        parse_mode="HTML",
                    )
                    canceled_count += 1
                except:
                    pass
    except:
        pass

    bot.answer_callback_query(c.id, "Магазин закрыт!")
    msg = "🔴 <b>ТЕХ. ПАУЗА ВКЛЮЧЕНА.</b>"
    if canceled_count > 0:
        msg += f"\n🗑 Отменено заказов: {canceled_count}"
    bot.edit_message_text(
        msg, c.message.chat.id, c.message.message_id, parse_mode="HTML"
    )


@bot.callback_query_handler(func=lambda c: c.data == "maint_off")
def maintenance_off(c):
    # 1. Выключаем режим (пишем в БД)
    set_maintenance_mode(False)

    bot.answer_callback_query(c.id, "Магазин открыт!")
    bot.edit_message_text(
        "🟢 <b>ТЕХ. ПАУЗА ВЫКЛЮЧЕНА.</b>\nМагазин снова работает.",
        c.message.chat.id,
        c.message.message_id,
        parse_mode="HTML",
    )


@bot.callback_query_handler(func=lambda c: c.data == "maint_cancel")
def maintenance_cancel(c):
    bot.delete_message(c.message.chat.id, c.message.message_id)
    admin_panel(c.message)


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


@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def show_stats(message):
    if message.from_user.id not in ADMIN_IDS:
        return

    # Вызываем функцию из нашего нового файла
    report = get_statistics()

    bot.send_message(message.chat.id, report, parse_mode="HTML")


def auto_cancel_expired_loop():
    while True:
        try:
            # 1. Ждем 1 минуту перед следующей проверкой
            time.sleep(60)

            # 2. Находим и отменяем заказы старше 40 минут
            # RETURNING user_id нужен, чтобы узнать, кого уведомить (PostgreSQL фишка)
            query = """
            UPDATE orders 
            SET status = 'cancelled' 
            WHERE status = 'waiting_payment' 
              AND created_at < NOW() - INTERVAL '40 minutes'
            RETURNING order_id, user_id;
            """
            expired_orders = execute_query(query, fetch=True)

            # 3. Пишем пользователям, что время вышло
            if expired_orders:
                for row in expired_orders:
                    oid, uid = row
                    try:
                        bot.send_message(
                            uid,
                            f"⏰ <b>Время вышло!</b>\n"
                            f"Бронь на заказ {oid} снята (прошло 40 минут).\n"
                            f"Товар вернулся на витрину.",
                            parse_mode="HTML",
                        )
                    except:
                        pass

        except Exception as e:
            print(f"Ошибка в авто-отмене: {e}")


def start_background_tasks():
    """Запускает фоновые потоки один раз"""
    if threading.active_count() < 5:
        threading.Thread(target=auto_backup_loop, daemon=True).start()
        threading.Thread(target=auto_cancel_expired_loop, daemon=True).start()
        print("✅ Фоновые задачи запущены.")


# Если файл запущен напрямую (локально)
if __name__ == "__main__":
    print("🤖 Бот запущен локально (Polling)...")
    start_background_tasks()
    bot.infinity_polling()
