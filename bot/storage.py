# bot/storage.py

from .db import execute_query
import time
from decimal import Decimal


def get_all_stores():
    """Получает все магазины для главного меню."""
    query = "SELECT store_id, title FROM stores ORDER BY store_id;"
    results = execute_query(query, fetch=True)
    stores_list = []
    if results:
        for row in results:
            # store_id, title
            stores_list.append({"store_id": row[0], "title": row[1]})
    return stores_list


def get_products_by_store(store_id):
    """Получает все товары для выбранного магазина."""
    query = "SELECT product_id, name, price_usd FROM products WHERE store_id = %s ORDER BY price_usd;"
    results = execute_query(query, (store_id,), fetch=True)
    products_list = []
    if results:
        for row in results:
            # product_id, name, price_usd
            products_list.append(
                {"product_id": row[0], "name": row[1], "price_usd": float(row[2])}
            )
    return products_list


def get_product_details_by_id(product_id):
    """Получает полные детали товара (для создания заказа) по его ID."""
    query = "SELECT p.price_usd, p.file_path, p.delivery_text, p.name, s.title FROM products p JOIN stores s ON p.store_id = s.store_id WHERE p.product_id = %s;"
    result = execute_query(query, (product_id,), fetch=True)
    if result:
        row = result[0]
        # price_usd, file_path, delivery_text, name, title (магазина)
        return {
            "price_usd": float(row[0]),
            "file_path": row[1],
            "delivery_text": row[2],
            "product_name": row[3],
            "shop_title": row[4],
        }
    return None


# --- ОБНОВЛЕННАЯ ФУНКЦИЯ ---
def add_order(
    user_id: int,
    product_id: int,
    price_usd: float,
    pickup_address: str,
    order_id: str,
    oxapay_track_id: str = None,
    payment_url: str = None,
):
    """
    Добавляет новый заказ в БД с полной информацией.
    Теперь принимает order_id извне, а также адрес и данные платежа.
    """

    query = """
    INSERT INTO orders (
        order_id, user_id, product_id, price_usd, 
        pickup_address, oxapay_track_id, payment_url, status
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, 'waiting_payment');
    """

    # Передаем параметры в порядке, указанном в VALUES
    params = (
        order_id,
        user_id,
        product_id,
        price_usd,
        pickup_address,
        oxapay_track_id,
        payment_url,
    )

    execute_query(query, params)
    return order_id


# ---------------------------


def update_order(order_id: str, **kwargs):
    """Обновляет статус или детали заказа в БД."""
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


def get_order(order_id: str):
    """Получает детали заказа по ID."""
    query = "SELECT * FROM orders WHERE order_id = %s;"
    result = execute_query(query, (order_id,), fetch=True)

    if result:
        cols = [
            "order_id",
            "user_id",
            "product_id",
            "pickup_address",
            "price_usd",
            "status",
            "delivery_status",
            "oxapay_track_id",
            "payment_url",
            "created_at",
            "paid_at",
        ]
        order_data = dict(zip(cols, result[0]))
        if "price_usd" in order_data:
            order_data["price_usd"] = float(order_data["price_usd"])

        return order_data
    return None


def find_orders_by_user(user_id: int):
    """Ищет все заказы пользователя."""
    query = """
    SELECT 
        o.order_id, 
        o.status, 
        o.price_usd, 
        p.name as product_name
    FROM orders o
    JOIN products p ON o.product_id = p.product_id
    WHERE o.user_id = %s 
    ORDER BY o.created_at DESC;
    """
    results = execute_query(query, (user_id,), fetch=True)

    orders_dict = {}
    if results:
        for row in results:
            oid, status, price, product_name = row
            orders_dict[oid] = {
                "status": status,
                "price": float(price),
                "product_name": product_name,
            }
    return orders_dict
