# bot/db.py

import os
import psycopg2
from decimal import Decimal

# !!! ВАЖНО !!! ЗАМЕНИТЕ ЭТУ СТРОКУ ВАШЕЙ РЕАЛЬНОЙ СТРОКОЙ ПОДКЛЮЧЕНИЯ RENDER
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://bdshop_kwoz_user:t4fpnmrBVddy8NPuYS9akZHhX2pYtsep@dpg-d4llumodl3ps7388r6ag-a.frankfurt-postgres.render.com/bdshop_kwoz?sslmode=require",
)


def get_connection():
    """Устанавливает и возвращает соединение с базой данных."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Ошибка подключения к БД: {e}")
        return None


def check_store_count():
    """Проверяет количество записей в таблице stores."""
    query = "SELECT COUNT(*) FROM stores;"
    result = execute_query(query, fetch=True)
    if result:
        return result[0][0]
    return 0


def execute_query(query, params=None, fetch=False):
    """Выполняет SQL-запрос."""
    conn = get_connection()
    if not conn:
        return None

    result = None

    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if fetch:
                result = cur.fetchall()  # Получаем результат RETURNING

            # Явный коммит для всех запросов на изменение данных
            conn.commit()

    except Exception as e:
        print(f"🚨 ОШИБКА SQL: {e}")
        # Откат транзакции на случай сбоя
        conn.rollback()
    finally:
        if conn:
            conn.close()

    return result
