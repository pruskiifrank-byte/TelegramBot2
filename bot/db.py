# bot/db.py
import os
import psycopg2
from bot.config import DATABASE_URL


def get_connection():
    """Устанавливает и возвращает соединение с базой данных."""
    if not DATABASE_URL:
        print("❌ ОШИБКА: Не задан DATABASE_URL")
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"🚨 Ошибка подключения к БД: {e}")
        return None


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
                result = cur.fetchall()
            conn.commit()
    except Exception as e:
        print(f"🚨 SQL ERROR: {e}\nQuery: {query}")
        conn.rollback()
    finally:
        if conn:
            conn.close()

    return result
