# init_db.py
from bot.db import execute_query
from bot.bot import SHOPS # Импортируем каталог из bot.py

def create_tables():
    """Создает таблицы products и orders в БД."""
    print("--- Создание таблицы products...")
    products_table = """
    CREATE TABLE IF NOT EXISTS products (
        product_id SERIAL PRIMARY KEY,
        shop_key TEXT NOT NULL,
        title TEXT NOT NULL,
        name TEXT NOT NULL,
        price_usd NUMERIC(10, 2) NOT NULL,
        delivery_text TEXT NOT NULL,
        file_path TEXT NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """
    execute_query(products_table)
    print("products создана.")

    print("--- Создание таблицы orders...")
    orders_table = """
    CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT PRIMARY KEY,
        user_id BIGINT NOT NULL,
        product_id INTEGER REFERENCES products(product_id),
        pickup_address TEXT NOT NULL,
        price_usd NUMERIC(10, 2) NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', 
        delivery_status TEXT DEFAULT 'pending',
        oxapay_track_id TEXT UNIQUE,
        payment_url TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        paid_at TIMESTAMP WITH TIME ZONE
    );
    """
    execute_query(orders_table)
    print("orders создана.")

def populate_products():
    """Заполняет таблицу products данными из каталога SHOPS."""
    print("--- Заполнение каталога...")
    for key, data in SHOPS.items():
        # Проверяем, существует ли уже этот товар по shop_key
        check_query = "SELECT product_id FROM products WHERE shop_key = %s;"
        existing = execute_query(check_query, (key,), fetch=True)
        
        if not existing:
            product = data["product"]
            insert_query = """
            INSERT INTO products (shop_key, title, name, price_usd, delivery_text, file_path)
            VALUES (%s, %s, %s, %s, %s, %s);
            """
            params = (
                key,
                data["title"],
                product["name"],
                product["price"],
                product["delivery_text"],
                product["file"],
            )
            execute_query(insert_query, params)
            print(f"Добавлен товар: {data['title']}")
        else:
            print(f"Товар {data['title']} уже существует.")

if __name__ == "__main__":
    create_tables()
    populate_products()
    print("База данных инициализирована.")