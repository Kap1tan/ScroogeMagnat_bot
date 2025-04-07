# main.py
import asyncio
import logging
import os
from aiogram.fsm.storage.memory import MemoryStorage
from bot import bot
from data import referral_data, users_data
from utils import save_referral_data, save_users_data

# Проверка и восстановление поврежденных данных рефералов
def validate_referral_data():
    for user_id, data in list(referral_data.items()):
        if not isinstance(data, dict):
            referral_data[user_id] = {
                "bot_link": f"https://t.me/ScroogeMagnat_bot?start={user_id}",
                "count": 0,
                "username": users_data.get(user_id, {}).get("username", "Неизвестно"),
                "referral_activations": []
            }
    save_referral_data(referral_data)

def validate_users_data():
    for user_id, data in list(users_data.items()):
        if not isinstance(data, dict):
            users_data[user_id] = {
                "username": "Неизвестно",
                "status": "active",
                "stars": 0,
                "stars_for_subscription_received": False
            }
    save_users_data(users_data)

async def main() -> None:
    # Проверка и восстановление данных перед запуском бота
    validate_referral_data()
    validate_users_data()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("bot.log"),
            logging.StreamHandler()
        ]
    )

    # Создаем директории для данных, если они не существуют
    os.makedirs("data", exist_ok=True)

    # Создаем необходимые файлы, если они не существуют
    for file_path in [
        "data/referrals.json",
        "data/users.json",
        "data/credited_referrals.json",
        "data/config.json",
        "data/promocodes.json",
        "data/required_channels.json"  # Добавляем файл для обязательных каналов
    ]:
        if not os.path.exists(file_path):
            with open(file_path, "w", encoding="utf-8") as f:
                if file_path == "data/config.json":
                    f.write('{"stars_per_referral": 2}')
                elif file_path == "data/promocodes.json":
                    f.write('{"promocodes": {}}')
                elif file_path == "data/required_channels.json":
                    f.write('{"channels": []}')
                else:
                    f.write('{}')
            logging.info(f"Создан файл: {file_path}")

    # Инициализируем диспетчер с хранилищем состояний
    from aiogram import Dispatcher
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Регистрируем роутер из bot.py
    from bot import router
    dp.include_router(router)

    # Импорт административных обработчиков первым - это важно для приоритета
    from handlers import admin

    # Затем импортируем остальные обработчики
    from handlers import (
        subscription,
        chat_member,
        captcha_handler,
        keyboard_handler,
        start  # Импортируем start последним, так как в нем есть catch-all обработчик
    )

    logging.info("Бот запущен")
    while True:
        try:
            await dp.start_polling(bot)
        except Exception as e:
            logging.exception(f"Ошибка в polling: {e}. Перезапуск через 5 секунд...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен пользователем")