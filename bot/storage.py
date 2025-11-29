import json
import threading
import time
from pathlib import Path

_lock = threading.Lock()
# Файл будет создан в корне проекта (рядом с server.py)
_orders_path = Path(__file__).parent.parent / "orders.json"

# in-memory orders dict: order_id -> {...}
orders = {}


def _ensure_file():
    if not _orders_path.exists():
        try:
            _orders_path.write_text("{}", encoding="utf-8")
        except Exception:
            pass


def load_orders():
    _ensure_file()
    try:
        with _lock:
            text = _orders_path.read_text(encoding="utf-8")
            data = json.loads(text or "{}")
            orders.clear()
            for k, v in data.items():
                orders[k] = v
    except Exception:
        pass


def save_orders():
    try:
        with _lock:
            _orders_path.write_text(
                json.dumps(orders, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    except Exception:
        pass


# Helpers
def add_order(user_id: int, price_usd: float, store_id: str, product_id: str):
    """Добавляет новый заказ в хранилище."""
    order_id = f"ORD-{int(time.time())}-{user_id}"

    # Расширяем структуру заказа
    orders[order_id] = {
        "user_id": user_id,
        "price_usd": price_usd,
        "status": "pending",  # 'pending', 'waiting_payment', 'paid'
        "store_id": store_id,  # НОВОЕ: ID магазина
        "product_id": product_id,  # НОВОЕ: ID товара
        "address": None,  # НОВОЕ: Адрес доставки
        "payment_url": None,
        "track_id": None,
    }

    # Сохранение в файл
    save_orders()
    return order_id


def update_order(order_id: str, **kwargs):
    o = orders.get(order_id)
    if not o:
        return
    o.update(kwargs)
    save_orders()


def get_order(order_id: str):
    return orders.get(order_id)


def find_orders_by_user(user_id: int):
    return {oid: d for oid, d in orders.items() if d.get("user_id") == user_id}


# Загружаем при старте
load_orders()
