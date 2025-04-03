# bot.py
from aiogram import Bot, Router
from aiogram.client.default import DefaultBotProperties
from config import BOT_TOKEN

# Включаем HTML-парсинг по умолчанию
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
router = Router()