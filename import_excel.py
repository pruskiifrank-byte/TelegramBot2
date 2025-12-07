import pandas as pd
import sys
import os

# --- НАСТРОЙКА ПУТЕЙ ---
sys.path.append(os.getcwd())

try:
    from bot.storage import upsert_user

    print("✅ Успешно подключились к базе данных бота.")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Убедитесь, что запускаете скрипт из папки, где лежит папка 'bot'.")
    sys.exit()


def import_users_from_excel(file_path):
    # Убираем кавычки, если Windows добавил их при копировании пути
    file_path = file_path.strip().replace('"', "").replace("'", "")

    print(f"📂 Открываю файл: {file_path}...")

    try:
        df = pd.read_excel(file_path, engine="openpyxl")
    except FileNotFoundError:
        print("❌ Ошибка: Файл не найден по указанному пути.")
        return
    except Exception as e:
        print(f"❌ Не удалось открыть Excel: {e}")
        return

    total_rows = len(df)
    print(f"📄 Найдено строк: {total_rows}")
    print("🚀 Начинаю импорт...")

    success_count = 0
    error_count = 0

    for index, row in df.iterrows():
        try:
            raw_uid = row["user_id"]
            if pd.isna(raw_uid):
                continue

            user_id = int(raw_uid)

            raw_username = row["joined_at"]
            username = str(raw_username).strip() if pd.notna(raw_username) else None

            raw_firstname = row["username"]
            first_name = str(raw_firstname).strip() if pd.notna(raw_firstname) else None

            upsert_user(user_id, username, first_name)
            success_count += 1

            if success_count % 50 == 0:
                print(f"⏳ Обработано {success_count}...")

        except Exception as e:
            error_count += 1
            print(f"⚠️ Ошибка в строке {index + 2}: {e}")

    print("-" * 30)
    print(f"🏁 Готово! Успешно: {success_count} | Ошибок: {error_count}")


if __name__ == "__main__":
    print("\n💡 СОВЕТ: Найдите файл users.xlsx и перетащите его мышкой в это окно.")
    user_input = input("Или вставьте путь к файлу сюда и нажмите Enter: ")

    if user_input:
        import_users_from_excel(user_input)
    else:
        print("Вы ничего не ввели.")
