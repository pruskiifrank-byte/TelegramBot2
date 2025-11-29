# bot/storage.py
import json
import threading
from pathlib import Path

_lock = threading.Lock()
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
        # ignore load errors, keep empty
        pass

def save_orders():
    try:
        with _lock:
            _orders_path.write_text(json.dumps(orders, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

# convenience helpers
def add_order(order_id: str, payload: dict):
    orders[order_id] = payload
    save_orders()

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

# load from disk on import
load_orders()
