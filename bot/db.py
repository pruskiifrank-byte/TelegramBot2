# bot/db.py

import os
import psycopg2

# !!! ВАЖНО !!! ЗАМЕНИТЕ ЭТУ СТРОКУ ВАШЕЙ РЕАЛЬНОЙ СТРОКОЙ ПОДКЛЮЧЕНИЯ RENDER
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bdshop_kwoz_user:t4fpnmrBVddy8NPuYS9akZHhX2pYtsep@dpg-d4llumodl3ps7388r6ag-a/bdshop_kwoz?sslmode=require")

def get_connection():
    """Устанавливает и возвращает соединение с базой данных."""
    try:
        # Для работы на Render необходимо использовать sslmode='require'
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        # print(f"Ошибка подключения к БД: {e}") # Закомментируйте на проде, чтобы не засорять логи
        return None

def execute_query(query, params=None, fetch=False):
    """Выполняет SQL-запрос."""
    conn = get_connection()
    if not conn:
        return None
        
    result = None
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                if fetch:
                    result = cur.fetchall()
    except Exception as e:
        print(f"Ошибка при выполнении запроса: {e}")
    finally:
        if conn:
            conn.close()
    return result