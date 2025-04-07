from aiogram import types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot import bot, router
from config import ADMIN_IDS
from data import required_channels
import logging


async def check_subscription(user_id: int) -> bool:
    """Проверяет, подписан ли пользователь на все обязательные каналы."""
    if not required_channels:
        # Если нет обязательных каналов, считаем, что пользователь подписан
        logging.info(f"Проверка подписки для пользователя {user_id}: нет обязательных каналов")
        return True

    is_subscribed_to_all = True

    for channel in required_channels:
        channel_id = channel.get('id')
        try:
            if not channel_id:
                continue

            member = await bot.get_chat_member(int(channel_id), user_id)
            is_member = member.status in ["member", "administrator", "creator"]

            logging.info(f"Проверка подписки для пользователя {user_id} на канал {channel_id}: "
                         f"статус {member.status}, результат {is_member}")

            if not is_member:
                is_subscribed_to_all = False
                break

        except Exception as e:
            logging.error(f"Ошибка при проверке подписки пользователя {user_id} на канал {channel_id}: {e}")
            # Если произошла ошибка, считаем что пользователь не подписан на данный канал
            is_subscribed_to_all = False
            break

    return is_subscribed_to_all


def get_subscription_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру с кнопками для подписки на обязательные каналы и проверки."""
    keyboard = []

    # Добавляем кнопки для всех обязательных каналов
    for channel in required_channels:
        channel_name = channel.get('name', 'Канал')
        channel_link = channel.get('link', '')

        if channel_link:
            keyboard.append([InlineKeyboardButton(
                text=f"Подписаться на {channel_name}",
                url=channel_link
            )])

    # Добавляем кнопку проверки подписки
    keyboard.append([InlineKeyboardButton(
        text="🔄 Проверить подписку",
        callback_data="check_subscription"
    )])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def get_not_subscribed_channels(user_id: int) -> list:
    """Возвращает список каналов, на которые пользователь не подписан."""
    if not required_channels:
        return []

    not_subscribed = []

    for channel in required_channels:
        channel_id = channel.get('id')
        try:
            if not channel_id:
                continue

            member = await bot.get_chat_member(int(channel_id), user_id)
            is_member = member.status in ["member", "administrator", "creator"]

            if not is_member:
                not_subscribed.append(channel)

        except Exception as e:
            logging.error(f"Ошибка при проверке подписки пользователя {user_id} на канал {channel_id}: {e}")
            # Если произошла ошибка, добавляем канал в список не подписанных
            not_subscribed.append(channel)

    return not_subscribed


def get_channels_text(channels_list: list) -> str:
    """Возвращает текст с информацией о необходимости подписки на каналы."""
    count = len(channels_list)

    if count == 0:
        return ""

    if count == 1:
        return "Требуется подписка на канал"
    elif 2 <= count <= 4:
        return f"Требуется подписка на {count} канала"
    else:
        return f"Требуется подписка на {count} каналов"