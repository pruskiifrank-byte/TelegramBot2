from telebot import TeleBot, types
import os
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
CALLBACK_URL = os.getenv("CALLBACK_URL")
CARD_NUMBER = os.getenv("CARD_NUMBER")

bot = TeleBot(API_TOKEN, parse_mode="HTML")


# -----------------------------------------
# Команда /start
# -----------------------------------------
@bot.message_handler(commands=["start"])
def start(message):
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("💳 Оплатить", callback_data="pay")
    markup.add(btn)
    bot.send_message(message.chat.id, "Привет! Хочешь оплатить?", reply_markup=markup)


# -----------------------------------------
# Кнопка Оплатить
# -----------------------------------------
@bot.callback_query_handler(func=lambda call: call.data == "pay")
def pay_button(call):
    invoice_url = f"https://global24pay.com/create?amount=10&order_id={call.message.chat.id}&callback={CALLBACK_URL}"

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Оплатить", url=invoice_url))

    bot.send_message(
        call.message.chat.id, "👉 Перейдите по ссылке для оплаты:", reply_markup=markup
    )


# -----------------------------------------
# Обязательный pre_checkout (для Telegram платежей)
# -----------------------------------------
@bot.pre_checkout_query_handler(func=lambda q: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


# -----------------------------------------
# Сообщение после успеха
# -----------------------------------------
@bot.message_handler(content_types=["successful_payment"])
def got_payment(message):
    bot.send_message(message.chat.id, "🎉 Платёж прошёл успешно через Telegram!")


# -----------------------------------------
# ВАЖНО: НЕТ polling!
# -----------------------------------------
