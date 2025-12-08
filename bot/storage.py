from .db import execute_query


# --- ПОЛЬЗОВАТЕЛИ ---
def upsert_user(user_id, username, first_name):
    query = """
    INSERT INTO users (user_id, username, first_name)
    VALUES (%s, %s, %s)
    ON CONFLICT (user_id) DO UPDATE 
    SET username = EXCLUDED.username, first_name = EXCLUDED.first_name;
    """
    execute_query(query, (user_id, username, first_name))


def get_all_users():
    res = execute_query("SELECT user_id FROM users;", fetch=True)
    return [row[0] for row in res] if res else []


# --- МАГАЗИНЫ И ТОВАРЫ ---
def get_all_stores():
    query = "SELECT store_id, title FROM stores ORDER BY store_id;"
    results = execute_query(query, fetch=True)
    stores_list = []
    if results:
        for row in results:
            stores_list.append({"store_id": row[0], "title": row[1]})
    return stores_list


def get_products_by_store(store_id):
    """
    Возвращает товары для Админки.
    ИСПРАВЛЕНО: Убрали admin_note, оставили address.
    """
    query = """
    SELECT product_id, name, price_usd, address
    FROM products 
    WHERE store_id = %s AND is_sold = FALSE 
    ORDER BY product_id DESC;
    """
    results = execute_query(query, (store_id,), fetch=True)
    products_list = []
    if results:
        for row in results:
            products_list.append(
                {
                    "product_id": row[0],
                    "name": row[1],
                    "price_usd": float(row[2]),
                    "address": (row[3] if row[3] else ""),
                }
            )
    return products_list


def get_product_details_by_id(product_id):
    """
    ИСПРАВЛЕНО: Убрана лишняя запятая перед FROM и удален admin_note.
    """
    query = """
    SELECT p.price_usd, p.file_path, p.delivery_text, p.name, s.title, p.address
    FROM products p 
    JOIN stores s ON p.store_id = s.store_id 
    WHERE p.product_id = %s;
    """
    result = execute_query(query, (product_id,), fetch=True)
    if result:
        row = result[0]
        return {
            "price_usd": float(row[0]),
            "file_path": row[1],
            "delivery_text": row[2],
            "product_name": row[3],
            "shop_title": row[4],
            "address": row[5] if len(row) > 5 else "Не указан",
            # admin_note удален
        }
    return None


def update_product_field(product_id, field, value):
    # ИСПРАВЛЕНО: Удален 'admin_note' из разрешенных полей
    allowed_fields = [
        "name",
        "price_usd",
        "delivery_text",
        "file_path",
        "address",
    ]
    if field not in allowed_fields:
        return

    query = f"UPDATE products SET {field} = %s WHERE product_id = %s;"
    execute_query(query, (value, product_id))


def get_unique_products_by_store(store_id):
    """
    Для меню категорий: возвращает уникальные имена товаров.
    """
    query = """
    SELECT DISTINCT ON (name) product_id, name, price_usd 
    FROM products 
    WHERE store_id = %s AND is_sold = FALSE 
    ORDER BY name, product_id;
    """
    results = execute_query(query, (store_id,), fetch=True)
    products_list = []
    if results:
        for row in results:
            products_list.append(
                {"ref_id": row[0], "name": row[1], "price_usd": float(row[2])}
            )
    return products_list


def get_districts_for_product(product_name):
    """
    Группирует товары по районам.
    """
    query = """
    SELECT address, COUNT(*), MIN(price_usd), MIN(product_id)
    FROM products
    WHERE name = %s AND is_sold = FALSE
    GROUP BY address;
    """
    results = execute_query(query, (product_name,), fetch=True)
    districts = []
    if results:
        for row in results:
            districts.append(
                {
                    "address": row[0],
                    "count": row[1],
                    "price": float(row[2]),
                    "target_id": row[3],
                }
            )
    return districts


def get_fresh_product_id(name, address):
    """
    Ищет свободный товар.
    Условие: Товар не продан И на него нет заказа, созданного менее 40 минут назад.
    """
    query = """
    SELECT p.product_id 
    FROM products p
    LEFT JOIN orders o ON p.product_id = o.product_id 
        AND o.status = 'waiting_payment' 
        AND o.created_at > NOW() - INTERVAL '40 minutes'
    WHERE p.name = %s 
      AND p.address = %s 
      AND p.is_sold = FALSE 
      AND o.order_id IS NULL -- Это гарантирует, что активной брони нет
    LIMIT 1;
    """
    res = execute_query(query, (name, address), fetch=True)
    return res[0][0] if res else None


def mark_product_as_sold(product_id):
    query = "UPDATE products SET is_sold = TRUE WHERE product_id = %s;"
    execute_query(query, (product_id,))


# --- АДМИНКА ---
def insert_product(store_id, name, price, delivery_text, file_path, address):
    query = """
    INSERT INTO products (store_id, name, price_usd, delivery_text, file_path, address, is_sold)
    VALUES (%s, %s, %s, %s, %s, %s, FALSE);
    """
    execute_query(query, (store_id, name, price, delivery_text, file_path, address))


def delete_product(product_id):
    execute_query(
        "UPDATE orders SET product_id = NULL WHERE product_id = %s;", (product_id,)
    )
    execute_query("DELETE FROM products WHERE product_id = %s;", (product_id,))


# --- ЗАКАЗЫ ---
def add_order(
    user_id,
    product_id,
    price_usd,
    pickup_address,
    order_id,
    oxapay_track_id,
    payment_url,
):
    query = """
    INSERT INTO orders (
        order_id, user_id, product_id, price_usd, 
        pickup_address, oxapay_track_id, payment_url, status, delivery_status
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, 'waiting_payment', 'pending');
    """
    execute_query(
        query,
        (
            order_id,
            user_id,
            product_id,
            price_usd,
            pickup_address,
            oxapay_track_id,
            payment_url,
        ),
    )
    return order_id


def update_order(order_id, **kwargs):
    if not kwargs:
        return
    set_clauses = []
    params = []
    for key, value in kwargs.items():
        set_clauses.append(f"{key} = %s")
        params.append(value)
    params.append(order_id)
    query = f"UPDATE orders SET {', '.join(set_clauses)} WHERE order_id = %s;"
    execute_query(query, tuple(params))


def cancel_order_db(order_id):
    query = "UPDATE orders SET status = 'cancelled' WHERE order_id = %s;"
    execute_query(query, (order_id,))


def get_order(order_id):
    query = "SELECT * FROM orders WHERE order_id = %s;"
    result = execute_query(query, (order_id,), fetch=True)
    if result:
        return {
            "order_id": result[0][0],
            "user_id": result[0][1],
            "product_id": result[0][2],
            "delivery_status": result[0][6],
            "status": result[0][5],
            "oxapay_track_id": result[0][7],
        }
    return None


def find_orders_by_user(user_id):
    query = """
    SELECT o.order_id, o.status, o.price_usd, p.name, o.delivery_status, o.payment_url, o.created_at
    FROM orders o
    LEFT JOIN products p ON o.product_id = p.product_id
    WHERE o.user_id = %s 
    ORDER BY o.created_at DESC;
    """
    results = execute_query(query, (user_id,), fetch=True)
    orders_dict = {}
    if results:
        for row in results:
            oid, status, price, p_name, d_status, pay_url, created_at = row
            if not p_name:
                p_name = "Удаленный товар"
            orders_dict[oid] = {
                "status": status,
                "price": float(price),
                "product_name": p_name,
                "delivery_status": d_status,
                "payment_url": pay_url,
                "created_at_ts": created_at.timestamp() if created_at else 0,
            }
    return orders_dict


def get_table_data(table_name):
    """
    Возвращает заголовки и все строки таблицы для экспорта.
    """
    allowed_tables = ["users", "products", "orders", "stores"]

    if table_name not in allowed_tables:
        return [], []

    query_cols = f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}';"
    cols_res = execute_query(query_cols, fetch=True)
    headers = [row[0] for row in cols_res] if cols_res else []

    query_data = f"SELECT * FROM {table_name};"
    rows = execute_query(query_data, fetch=True)

    return headers, rows


def get_store_id_by_title(title):
    query = "SELECT store_id FROM stores WHERE title ILIKE %s;"
    res = execute_query(query, (title.strip(),), fetch=True)
    if res:
        return res[0][0]
    return None
