# reset_db.py
from bot.db import execute_query
from init_db import create_tables, populate_stores, update_table_structure


def wipe_database():
    print("🔥 НАЧИНАЕМ ПОЛНУЮ ОЧИСТКУ БАЗЫ...")

    # Удаляем таблицы в правильном порядке (CASCADE удаляет связи)
    execute_query("DROP TABLE IF EXISTS orders CASCADE;")
    execute_query("DROP TABLE IF EXISTS products CASCADE;")
#    execute_query("DROP TABLE IF EXISTS stores CASCADE;")
    execute_query("DROP TABLE IF EXISTS users CASCADE;")

    print("🗑 Все таблицы удалены.")


if __name__ == "__main__":
    confirm = input("Вы точно хотите удалить ВСЮ базу? (y/n): ")
    if confirm.lower() == "y":
        wipe_database()
        print("🛠 Создаем таблицы заново...")
        create_tables()
        populate_stores()
        update_table_structure()
        print("✅ База данных чиста и готова к работе!")
    else:
        print("Отмена.")
