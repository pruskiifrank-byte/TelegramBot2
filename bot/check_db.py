# check_db.py
from bot.db import check_store_count

if __name__ == "__main__":
    count = check_store_count()
    if count > 0:
        print(f"✅ УСПЕХ! Найдено {count} магазинов в базе данных.")
    else:
        print("❌ ПРОВАЛ! Таблица stores пуста или недоступна.")
