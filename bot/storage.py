# bot/storage.py
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
    # Показываем только НЕ проданные
    query = """
    SELECT product_id, name, price_usd 
    FROM products 
    WHERE store_id = %s AND is_sold = FALSE 
    ORDER BY price_usd;
    """
    results = execute_query(query, (store_id,), fetch=True)
    products_list = []
    if results:
        for row in results:
            products_list.append(
                {"product_id": row[0], "name": row[1], "price_usd": float(row[2])}
            )
    return products_list


def get_product_details_by_id(product_id):
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
            "address": row[5] if len(row) > 5 else "Не указан",  # <--- Достаем район
        }
    return None

# --- АДМИНКА ---
def insert_product(store_id, name, price, delivery_text, file_path, address):
    query = """
    INSERT INTO products (store_id, name, price_usd, delivery_text, file_path, address, is_sold)
    VALUES (%s, %s, %s, %s, %s, %s, FALSE);
    """
    execute_query(query, (store_id, name, price, delivery_text, file_path, address))


def mark_product_as_sold(product_id):
    query = "UPDATE products SET is_sold = TRUE WHERE product_id = %s;"
    execute_query(query, (product_id,))





def update_product_field(product_id, field, value):
    allowed_fields = ["name", "price_usd", "delivery_text", "file_path", "address"]
    if field not in allowed_fields:
        return
    query = f"UPDATE products SET {field} = %s WHERE product_id = %s;"
    execute_query(query, (value, product_id))


def delete_product(product_id):
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
        # Индексы зависят от порядка создания таблицы.
        # Обычно: 0-order_id, 1-user, 2-prod, 3-addr, 4-price, 5-status, 6-deliv, 7-track
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
            # Теперь распаковываем 7 значений (добавилось created_at)
            oid, status, price, p_name, d_status, pay_url, created_at = row

            if not p_name:
                p_name = "Удаленный товар"

            orders_dict[oid] = {
                "status": status,
                "price": float(price),
                "product_name": p_name,
                "delivery_status": d_status,
                "payment_url": pay_url,
                # Превращаем время в число (timestamp), чтобы удобно сравнивать
                "created_at_ts": created_at.timestamp() if created_at else 0,
            }
    return orders_dict
