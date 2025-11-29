# bot/products.py

# Каждая позиция: ID, Название, Цена (в USD), Описание, URL фотографии
FRUITS = {
    "banana": {
        "name": "Связка бананов",
        "price_usd": 3.00,
        "description": "Свежие, спелые бананы.",
        "photo_url": "https://i.imgur.com/example/banana.jpg",
        # НОВЫЕ ПОЛЯ ДЛЯ ТАЙНИКА
        "delivery_photo_url": "https://i.imgur.com/place/banana_spot.jpg", 
        "delivery_text": "📍 Тайник №123: Под третьей скамейкой у фонтана 'Три Грации'."
    },
    # ... другие товары
}

# Магазины: ID, Название, Товары
STORES = {
    "scooby_doo": {
        "name": "🍌 Scooby-Doo — Фрукты",
        "products": FRUITS
    },
    "hardware_co": {
        "name": "🔩 Tool Co. — Инструменты",
        "products": {} # Добавьте сюда другие товары
    }
}

def get_product_by_id(store_id: str, product_id: str):
    """Возвращает информацию о товаре по ID магазина и ID товара."""
    store = STORES.get(store_id)
    if store:
        return store["products"].get(product_id)
    return None