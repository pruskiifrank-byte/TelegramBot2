# add_note_col.py
from bot.db import execute_query

def add_note():
    print("🛠 Добавляем колонку для заметок админа...")
    try:
        execute_query("ALTER TABLE products ADD COLUMN admin_note TEXT DEFAULT '';")
        print("✅ Колонка 'admin_note' успешно добавлена.")
    except Exception as e:
        print(f"ℹ️ Ошибка (возможно, уже есть): {e}")

if __name__ == "__main__":
    add_note()