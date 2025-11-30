# init_db.py
from bot.db import execute_query

# Полный каталог для инициализации БД
CATALOG = {
    "fruits": {
        "title": "🍌 Scooby-Doo — Фрукты",
        "products": [
            {
                "name": "Набор фруктов (Малый)",
                "file": "bot/images/fruits_s.jpg",
                "price": 1.00,
                "delivery_text": "📍 Тайник у фонтана, смотри под скамейкой. Код: FRUITS1.",
            },
            {
                "name": "Набор фруктов (Средний)",
                "file": "bot/images/fruits_m.jpg",
                "price": 2.00,
                "delivery_text": "📍 У большого дерева, под камнем. Код: FRUITS2.",
            },
        ],
    },
    "vegetables": {
        "title": "🥕 MrGrinchShopZp — Овощи",
        "products": [
            {
                "name": "Набор овощей (Зима)",
                "file": "bot/images/vegs_w.jpg",
                "price": 1.00,
                "delivery_text": "📍 Тайник у столба, синий мешок. Код: VEGS2.",
            },
            {
                "name": "Набор овощей (Лето)",
                "file": "bot/images/vegs_s.jpg",
                "price": 3.00,
                "delivery_text": "📍 На крыше парковки, в вентиляции. Код: VEGS3.",
            },
        ],
    },
    "meat": {
        "title": "🥩 BeefMaster — Мясо",
        "products": [
            {
                "name": "Стейк Премиум",
                "file": "bot/images/meat.jpg",
                "price": 12.00,
                "delivery_text": "📍 Под старым дубом, в синем контейнере. Код: MEAT3.",
            },
        ],
    },
    "drinks": {
        "title": "🥤 Refresh — Напитки",
        "products": [
            {
                "name": "Энергетик 'Турбо'",
                "file": "bot/images/drinks/turbo.jpg",
                "price": 3.50,
                "delivery_text": "📍 Под лавочкой в парке, рядом с третьим деревом. Код: DRK1.",
            },
            {
                "name": "Кола (1.5 л)",
                "file": "bot/images/drinks/cola.jpg",
                "price": 2.00,
                "delivery_text": "📍 В мусорном баке возле почты, под картоном. Код: DRK2.",
            },
        ],
    },
}


def create_tables():
    """Создает таблицы stores, products и orders в БД."""
    print("--- Удаление старых таблиц (если существуют)...")
    execute_query("DROP TABLE IF EXISTS orders;")
    execute_query("DROP TABLE IF EXISTS products;")
    execute_query("DROP TABLE IF EXISTS stores;")

    print("--- Создание таблицы stores...")
    stores_table = """
    CREATE TABLE IF NOT EXISTS stores (
        store_id SERIAL PRIMARY KEY,
        shop_key TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL
    );
    """
    execute_query(stores_table)
    print("stores создана.")

    print("--- Создание таблицы products...")
    products_table = """
    CREATE TABLE IF NOT EXISTS products (
        product_id SERIAL PRIMARY KEY,
        store_id INTEGER REFERENCES stores(store_id), 
        name TEXT NOT NULL,
        price_usd NUMERIC(10, 2) NOT NULL,
        delivery_text TEXT NOT NULL,
        file_path TEXT NOT NULL
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
        pickup_address TEXT, 
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
    """Заполняет таблицы stores и products данными из каталога."""
    print("--- Заполнение каталога...")

    # Заполнение stores
    for key, data in CATALOG.items():
        print(f"Попытка вставить магазин: {data['title']}")
        insert_store = (
            "INSERT INTO stores (shop_key, title) VALUES (%s, %s) RETURNING store_id;"
        )
        result = execute_query(insert_store, (key, data["title"]), fetch=True)

        store_id = result[0][0] if result else None

        if not store_id:
            print(
                f"❌ ОШИБКА: Не удалось получить store_id для {data['title']}. Проверьте подключение/запрос!"
            )
            continue

        print(f"✅ Магазин '{data['title']}' добавлен с ID: {store_id}")

        # Заполнение products
        for product in data["products"]:
            insert_product = """
            INSERT INTO products (store_id, name, price_usd, delivery_text, file_path)
            VALUES (%s, %s, %s, %s, %s);
            """
            params = (
                store_id,
                product["name"],
                product["price"],
                product["delivery_text"],
                product["file"],
            )
            execute_query(insert_product, params)
            print(f"Добавлен товар: {product['name']}")


if __name__ == "__main__":
    from bot.db import execute_query

    create_tables()
    populate_products()
    print("База данных инициализирована.")
