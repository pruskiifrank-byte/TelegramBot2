# init_db.py
from bot.db import execute_query

# Каталог для примера (пустой, так как добавляем через админку)
CATALOG = {"test": {"title": "📂 Тестовая категория"}}


def create_tables():
    print("🛠 Проверка и обновление таблиц...")

    # 1. Таблица пользователей (НОВАЯ)
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

    # 2. Магазины
    execute_query(
        """
        CREATE TABLE IF NOT EXISTS stores (
            store_id SERIAL PRIMARY KEY,
            title TEXT NOT NULL
        );
    """
    )

    # 3. Товары
    execute_query(
        """
        CREATE TABLE IF NOT EXISTS products (
            product_id SERIAL PRIMARY KEY,
            store_id INTEGER REFERENCES stores(store_id), 
            name TEXT NOT NULL,
            price_usd NUMERIC(10, 2) NOT NULL,
            delivery_text TEXT NOT NULL,
            file_path TEXT NOT NULL 
        );
    """
    )

    # 4. Заказы
    execute_query(
        """
        CREATE TABLE IF NOT EXISTS orders (
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

    print("✅ Таблицы готовы.")


def populate_stores():
    # Проверка, есть ли магазины, если нет - создаем тестовый
    res = execute_query("SELECT count(*) FROM stores;", fetch=True)
    if res and res[0][0] == 0:
        print("🏪 Создание базовых категорий...")
        for key, data in CATALOG.items():
            execute_query("INSERT INTO stores (title) VALUES (%s)", (data["title"],))


if __name__ == "__main__":
    create_tables()
    populate_stores()
    # init_db.py (добавь эту функцию и вызови её)


def update_table_structure():
    print("🛠 Обновление структуры таблиц...")
    # Добавляем колонку is_sold, если её нет
    try:
        execute_query("ALTER TABLE products ADD COLUMN is_sold BOOLEAN DEFAULT FALSE;")
        print("✅ Колонка 'is_sold' добавлена.")
    except Exception as e:
        print(f"ℹ️ Колонка уже есть или ошибка: {e}")


if __name__ == "__main__":
    # create_tables() # Это если с нуля
    update_table_structure()  # <-- ЗАПУСТИ ЭТО
