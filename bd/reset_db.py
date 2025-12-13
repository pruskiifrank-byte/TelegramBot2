# reset_db.py
import os
from dotenv import load_dotenv

# Загружаем переменные из .env (чтобы работало локально)
load_dotenv()

from bot.db import execute_query


def full_reset():
    print("🔥 НАЧИНАЕМ ПОЛНЫЙ СБРОС...")

    # 1. Удаляем все таблицы (CASCADE удаляет и связи)
    tables = ["orders", "products", "stores", "users"]
    for t in tables:
        execute_query(f"DROP TABLE IF EXISTS {t} CASCADE;")
    print("🗑 Старые данные удалены.")

    # 2. Создаем таблицу Пользователей
    execute_query(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """
    )

    # 3. Создаем таблицу Магазинов (Категорий)
    execute_query(
        """
        CREATE TABLE IF NOT EXISTS stores (
            store_id SERIAL PRIMARY KEY,
            title TEXT NOT NULL
        );
    """
    )

    # 4. Создаем таблицу Товаров
    execute_query(
        """
        CREATE TABLE IF NOT EXISTS products (
            product_id SERIAL PRIMARY KEY,
            store_id INTEGER REFERENCES stores(store_id), 
            name TEXT NOT NULL,
            price_usd NUMERIC(10, 2) NOT NULL,
            delivery_text TEXT NOT NULL,
            file_path TEXT NOT NULL,
            address TEXT DEFAULT 'Не указан', 
            is_sold BOOLEAN DEFAULT FALSE
        );
    """
    )

    # 5. Создаем таблицу Заказов
    # ИСПРАВЛЕНО: Убран дубликат buyer_username
    execute_query(
        """
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            product_id INTEGER REFERENCES products(product_id),
            
            -- СНИМКИ ДАННЫХ ДЛЯ АДМИНА
            product_name TEXT,            -- Название товара на момент покупки
            buyer_username TEXT,          -- Юзернейм покупателя
            store_title TEXT,             -- Название магазина
            
            pickup_address TEXT, 
            price_usd NUMERIC(10, 2) NOT NULL,
            status TEXT NOT NULL DEFAULT 'waiting_payment', 
            delivery_status TEXT DEFAULT 'pending',
            oxapay_track_id TEXT,
            payment_url TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP WITH TIME ZONE
        );
    """
    )
    print("🛠 Таблицы пересозданы с правильной структурой.")

    # 6. Создаем категории для старта
    execute_query("INSERT INTO stores (title) VALUES ('MrGrinchShopZp');")
    execute_query("INSERT INTO stores (title) VALUES ('ScoobyDoo');")
    print("✅ Добавлена категория '📂 Магазины'.")

    print("\n🚀 БАЗА ДАННЫХ ПОЛНОСТЬЮ ОБНОВЛЕНА И ГОТОВА К РАБОТЕ!")


if __name__ == "__main__":
    confirm = input(
        "⚠️ ВНИМАНИЕ: Это удалит ВСЕ данные (товары, заказы, юзеров).\nНапишите 'yes' для подтверждения: "
    )
    if confirm.lower() == "yes":
        full_reset()
    else:
        print("Отмена.")
