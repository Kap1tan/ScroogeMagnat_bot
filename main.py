# main.py
import asyncio
import logging
import os
from aiogram.fsm.storage.memory import MemoryStorage
from bot import bot


async def main() -> None:
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

    # Инициализируем диспетчер с хранилищем состояний
    from aiogram import Dispatcher
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Регистрируем роутер из bot.py
    from bot import router
    dp.include_router(router)

    # Импортируем все обработчики для регистрации в роутере
    from handlers import subscription, start, admin, chat_member

    logging.info("Бот запущен")
    while True:
        try:
            await dp.start_polling(bot)
        except Exception as e:
            logging.exception(f"Ошибка в polling: {e}. Перезапуск через 5 секунд...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())