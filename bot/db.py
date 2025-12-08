import os
import psycopg2
from psycopg2 import pool

# Глобальная переменная для пула соединений
db_pool = None


def init_db_pool():
    """Инициализирует пул соединений при старте бота"""
    global db_pool

    # Получаем URL базы из настроек Render или .env
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        print("⛔️ ОШИБКА: Не найдена переменная DATABASE_URL!")
        return

    try:
        # Создаем пул: минимум 1 соединение, максимум 20
        # ThreadedConnectionPool нужен, если вы используете threaded=True в боте,
        # но даже с threaded=False это хороший и безопасный выбор.
        db_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=20, dsn=database_url
        )
        if db_pool:
            print("✅ Успешное подключение к базе данных (Pool created)")

    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")


def execute_query(query, params=None, fetch=False):
    """
    Усиленная функция выполнения запросов с авто-переподключением.
    Защищает от ошибок SSL error и EOF detected на Render.
    """
    global db_pool

    # Если пул не создан или закрыт, пробуем пересоздать
    if not db_pool:
        init_db_pool()
        if not db_pool:
            print("❌ CRITICAL: Не удалось создать пул БД")
            return None

    conn = None
    result = None

    # Попытка выполнить запрос (с 1 повтором при сбое сети)
    for attempt in range(2):
        try:
            # 1. Берем соединение из пула
            conn = db_pool.getconn()

            # 2. Создаем курсор и выполняем запрос
            with conn.cursor() as cur:
                cur.execute(query, params)

                if fetch:
                    result = cur.fetchall()
                else:
                    conn.commit()

            # Если дошли сюда без ошибок - успех, выходим из цикла
            break

        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            # Ловим ошибки сети (SSL EOF, decryption failed, server closed connection)
            # print(f"⚠️ SQL Connection Error (Attempt {attempt+1}): {e}")

            if conn:
                try:
                    # Сообщаем пулу, что это соединение мертвое, пусть закроет его
                    db_pool.putconn(conn, close=True)
                except:
                    pass
                conn = None  # Сбрасываем переменную, чтобы не вернуть её в finally

            # Идем на вторую попытку (цикл for сработает еще раз)
            continue

        except Exception as e:
            # Логические ошибки SQL (синтаксис и т.д.) - их не повторяем
            print(f"🚨 SQL ERROR: {e}\nQuery: {query}")
            if conn:
                conn.rollback()
            break

        finally:
            # 3. Возвращаем соединение в пул (только если оно живое)
            if conn:
                try:
                    db_pool.putconn(conn)
                except:
                    pass

    return result


# Инициализируем пул сразу при импорте файла
init_db_pool()
