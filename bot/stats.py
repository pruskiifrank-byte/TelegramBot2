# bot/stats.py
from bot.db import execute_query
from datetime import datetime


def get_statistics():
    """
    Собирает полную статистику по магазину.
    Возвращает текст отчета.
    """
    # 1. Пользователи
    res = execute_query("SELECT COUNT(*) FROM users;", fetch=True)
    total_users = res[0][0] if res else 0

    # 2. Заказы (Оплаченные)
    res = execute_query(
        "SELECT COUNT(*) FROM orders WHERE status = 'paid';", fetch=True
    )
    paid_orders = res[0][0] if res else 0

    # 3. Выручка (Сумма всех оплаченных заказов)
    res = execute_query(
        "SELECT SUM(price_usd) FROM orders WHERE status = 'paid';", fetch=True
    )
    total_revenue = float(res[0][0]) if res and res[0][0] else 0.0

    # 4. Топ-3 популярных товара
    query_top = """
    SELECT p.name, COUNT(o.order_id) as cnt 
    FROM orders o 
    JOIN products p ON o.product_id = p.product_id 
    WHERE o.status = 'paid' 
    GROUP BY p.name 
    ORDER BY cnt DESC 
    LIMIT 3;
    """
    top_products = execute_query(query_top, fetch=True)

    # Формируем красивый текст
    stats_text = (
        f"📊 <b>СТАТИСТИКА МАГАЗИНА</b>\n"
        f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        f"👥 <b>Пользователей:</b> {total_users}\n"
        f"✅ <b>Продаж:</b> {paid_orders}\n"
        f"💰 <b>Выручка:</b> {total_revenue} $\n\n"
        f"🏆 <b>Топ-3 товара:</b>\n"
    )

    if top_products:
        for i, (name, count) in enumerate(top_products, 1):
            stats_text += f"{i}. {name} — {count} шт.\n"
    else:
        stats_text += "Пока нет продаж.\n"

    return stats_text
