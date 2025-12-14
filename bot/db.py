# bot/db.py
import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

load_dotenv()

# Глобальная переменная для пула
db_pool = None


def init_db_pool():
    global db_pool
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        print("⛔️ ОШИБКА: Не найдена переменная DATABASE_URL!")
        return

    try:
        db_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=20, dsn=database_url
        )
        if db_pool:
            print("✅ Успешное подключение к базе данных (Pool created)")
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")


def execute_query(query, params=None, fetch=False):
    """
    Универсальная функция.
    ТЕПЕРЬ ДЕЛАЕТ COMMIT ВСЕГДА.
    """
    global db_pool

    if not db_pool:
        init_db_pool()
        if not db_pool:
            return None

    conn = None
    result = None

    for attempt in range(2):
        try:
            conn = db_pool.getconn()

            with conn.cursor() as cur:
                cur.execute(query, params)

                if fetch:
                    result = cur.fetchall()

                # 🔥 ВАЖНОЕ ИЗМЕНЕНИЕ: 🔥
                # Делаем коммит ВСЕГДА, чтобы INSERT ... RETURNING сохранялся
                conn.commit()

            break  # Успех

        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            if conn:
                try:
                    db_pool.putconn(conn, close=True)
                except:
                    pass
                conn = None
            continue  # Пробуем еще раз

        except Exception as e:
            print(f"🚨 SQL ERROR: {e}\nQuery: {query}")
            if conn:
                conn.rollback()
            break

        finally:
            if conn:
                try:
                    db_pool.putconn(conn)
                except:
                    pass

    return result


# Инициализация при старте
init_db_pool()
