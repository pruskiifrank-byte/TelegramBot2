# rename_stores.py
from bot.db import execute_query


def rename_category(part_of_old_name, new_name):
    """
    Ищет магазин, в названии которого есть part_of_old_name,
    и меняет его название на new_name.
    """
    # 1. Проверяем, есть ли такой магазин
    search_query = "SELECT store_id, title FROM stores WHERE title ILIKE %s;"
    # ILIKE означает поиск без учета регистра (большие/маленькие буквы не важны)
    results = execute_query(search_query, (f"%{part_of_old_name}%",), fetch=True)

    if not results:
        print(f"❌ Магазин с названием, похожим на '{part_of_old_name}', не найден.")
        return

    # 2. Если нашли — обновляем
    for store in results:
        store_id, old_title = store
        print(f"🔄 Меняем: '{old_title}' -> '{new_name}'")

        update_query = "UPDATE stores SET title = %s WHERE store_id = %s;"
        execute_query(update_query, (new_name, store_id))

    print("✅ Успешно!")


if __name__ == "__main__":
    # --- НАСТРОЙКИ (МЕНЯТЬ ТУТ) ---

    # Пример: найти магазин где есть слово "Фрукты" и назвать его "Электроника"
    rename_category("", "MrGrinchShopZp")

    # Пример: найти магазин где есть слово "Овощи" и назвать его "Одежда"
    rename_category("", "ScoobyDoo")

    # Можете добавить свои строки:
    # rename_category("Старое название", "Новое название")
