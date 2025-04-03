import logging
from aiogram import types
from bot import bot, router
from data import users_data, referral_data, credited_referrals, save_credited_referrals, stars_per_referral
from utils import save_users_data, save_referral_data, get_stars_word
from config import CHANNEL_ID


@router.my_chat_member()
async def on_my_chat_member(update: types.ChatMemberUpdated) -> None:
    if update.chat.type != "private":
        return
    user_id = str(update.chat.id)
    if update.new_chat_member.status in ["kicked", "left"]:
        if user_id in users_data:
            users_data[user_id]["status"] = "removed"
            save_users_data(users_data)
            logging.info(f"Пользователь {user_id} удалил бота.")


@router.chat_member()
async def on_chat_member_update(update: types.ChatMemberUpdated) -> None:
    if update.chat.id != CHANNEL_ID:
        return

    # Пользователь подписался на канал
    if update.new_chat_member.status == "member" and update.old_chat_member.status != "member":
        user_id = str(update.new_chat_member.user.id)

        # Если пользователь есть в данных, обновляем его статус
        if user_id in users_data:
            # Отправляем уведомление пользователю о возможности получить реферальную ссылку
            try:
                await bot.send_message(
                    int(user_id),
                    "✅ <b>Спасибо за подписку на канал!</b>\n\n"
                    "Теперь вы можете использовать все функции бота и получить свою реферальную ссылку.\n"
                )
            except Exception as e:
                logging.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")
