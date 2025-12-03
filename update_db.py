# update_db.py
from bot.db import execute_query

def add_admin_note():
    print("🛠 Добавляем колонку 'admin_note'...")
    try:
        execute_query("ALTER TABLE products ADD COLUMN admin_note TEXT DEFAULT '';")
        print("✅ УСПЕХ! Колонка добавлена.")
    except Exception as e:
        print(f"ℹ️ Уже есть или ошибка: {e}")

if __name__ == "__main__":
    add_admin_note()