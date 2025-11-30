# init_db.py
from bot.db import execute_query

# Инициализация для старта
# Тут нет товаров, их добавишь через Админку в боте!
CATALOG = {
    "fruits": {"title": "🍎 Фрукты (Тест)"},
    "vegs": {"title": "🥕 Овощи (Тест)"},
}


def create_tables():
    print("🧹 Удаление старых таблиц...")
    execute_query("DROP TABLE IF EXISTS orders;")
    execute_query("DROP TABLE IF EXISTS products;")
    execute_query("DROP TABLE IF EXISTS stores;")

    print("🛠 Создание таблиц...")

    # Stores
    execute_query(
        """
        CREATE TABLE stores (
            store_id SERIAL PRIMARY KEY,
            title TEXT NOT NULL
        );
    """
    )

    # Products (file_path теперь хранит file_id телеграма)
    execute_query(
        """
        CREATE TABLE products (
            product_id SERIAL PRIMARY KEY,
            store_id INTEGER REFERENCES stores(store_id), 
            name TEXT NOT NULL,
            price_usd NUMERIC(10, 2) NOT NULL,
            delivery_text TEXT NOT NULL,
            file_path TEXT NOT NULL 
        );
    """
    )

    # Orders (добавлен delivery_status)
    execute_query(
        """
        CREATE TABLE orders (
            order_id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            product_id INTEGER REFERENCES products(product_id),
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

    print("✅ Таблицы созданы.")


def populate_stores():
    print("🏪 Создание категорий...")
    for key, data in CATALOG.items():
        execute_query("INSERT INTO stores (title) VALUES (%s)", (data["title"],))
    print("✅ Категории созданы. Товары добавляй через /admin в боте.")


if __name__ == "__main__":
    create_tables()
    populate_stores()
