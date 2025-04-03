from aiogram import types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot import bot, router
from config import CHANNEL_ID, CHANNEL_LINK

async def check_subscription(user_id: int) -> bool:
    """Проверяет, подписан ли пользователь на канал."""
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        # Если произошла ошибка, считаем что пользователь не подписан
        return False

def get_subscription_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру с кнопкой для подписки и проверки."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")]
    ])