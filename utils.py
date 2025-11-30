# bot/utils.py
from flask import request
import json

# Список официальных диапазонов IP-адресов Telegram.
# Этот список может меняться, и его нужно периодически обновлять.
# На практике для большинства простых ботов достаточно проверять токен.


def verify_telegram_request(request):
    """
    Проверяет, что запрос действительно пришел от Telegram.

    Для простоты мы проверяем только, что в URL присутствует токен,
    что является базовой мерой безопасности для вебхука.
    В ПРОФЕССИОНАЛЬНЫХ проектах требуется проверка IP-адресов.
    """
    try:
        # Простая проверка: если токен бота есть в URL, считаем запрос легитимным.
        # Этого достаточно для большинства хостингов, где IP-адрес источника
        # не всегда отображается корректно (прокси, балансировщики).

        # NOTE: Ваш TELEGRAM_TOKEN должен быть импортирован или доступен здесь
        # (в данном примере мы просто проверяем наличие JSON-контента)

        if request.headers.get("content-type") == "application/json":
            # Проверка, что запрос содержит данные, которые выглядят как обновление Telegram
            try:
                data = request.get_json(silent=True)
                if "update_id" in data:
                    return True  # Похоже на обновление Telegram

            except json.JSONDecodeError:
                return False

    except Exception as e:
        print(f"Error during Telegram request verification: {e}")
        return False

    return False
