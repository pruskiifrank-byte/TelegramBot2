from bot.db import execute_query


def clear_history():
    print("🧹 Очистка истории заказов...")
    # Удаляем все строки из orders
    execute_query("TRUNCATE TABLE orders;")

    # Если хотите удалить и пользователей (чтобы они снова жали /start)
    # execute_query("TRUNCATE TABLE users CASCADE;")

    print("✅ История заказов очищена. Товары остались на месте.")


if __name__ == "__main__":
    clear_history()
