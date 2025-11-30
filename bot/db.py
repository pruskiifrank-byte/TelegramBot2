# bot/db.py
import os
import psycopg2
from psycopg2 import pool
from bot.config import DATABASE_URL

# Создаем пул соединений (минимум 1, максимум 20)
try:
    if DATABASE_URL:
        db_pool = psycopg2.pool.SimpleConnectionPool(
            1, 20, DATABASE_URL, sslmode="require"
        )
        print("✅ Пул соединений с БД создан успешно")
    else:
        print("❌ ОШИБКА: Не задан DATABASE_URL")
        db_pool = None
except Exception as e:
    print(f"🚨 Ошибка создания пула БД: {e}")
    db_pool = None


def execute_query(query, params=None, fetch=False):
    """
    Выполняет SQL-запрос, используя быстрое соединение из пула.
    """
    if not db_pool:
        print("⛔ Пул БД не инициализирован")
        return None

    conn = None
    result = None
    try:
        # Берем свободное соединение из пула (мгновенно)
        conn = db_pool.getconn()

        with conn.cursor() as cur:
            cur.execute(query, params)
            if fetch:
                result = cur.fetchall()
            conn.commit()

    except Exception as e:
        print(f"🚨 SQL ERROR: {e}\nQuery: {query}")
        if conn:
            conn.rollback()
    finally:
        # ОБЯЗАТЕЛЬНО возвращаем соединение обратно в пул
        if conn:
            db_pool.putconn(conn)

    return result
