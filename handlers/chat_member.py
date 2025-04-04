# handlers/chat_member.py
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
        
        # Проверяем, есть ли этот пользователь в данных бота
        if user_id in users_data:
            # Проверяем, не был ли этот пользователь уже засчитан как реферал
            is_new_referral = False
            
            # Проверяем, есть ли у пользователя реферер (пригласивший)
            referrer_id = None
            for potential_referrer_id, info in referral_data.items():
                # Ищем пользователя в активированных по реферальной ссылке
                referral_records = info.get("referral_activations", [])
                if user_id in referral_records:
                    referrer_id = potential_referrer_id
                    break
            
            # Если пользователь есть в списке активированных по реферальной ссылке,
            # но не в списке засчитанных за подписку
            if referrer_id and user_id not in credited_referrals:
                is_new_referral = True
                # Добавляем в список засчитанных рефералов
                credited_referrals.add(user_id)
                save_credited_referrals()
                
                # Обновляем статистику рефералов
                if referrer_id in referral_data:
                    referral_data[referrer_id]["count"] = referral_data[referrer_id].get("count", 0) + 1
                else:
                    referral_data[referrer_id] = {
                        "bot_link": f"https://t.me/{(await bot.get_me()).username}?start={referrer_id}",
                        "count": 1,
                        "username": users_data.get(referrer_id, {}).get("username", "Неизвестно"),
                        "referral_activations": []
                    }
                save_referral_data(referral_data)
                
                # Начисляем звезды рефереру
                if referrer_id in users_data:
                    users_data[referrer_id]["stars"] = users_data[referrer_id].get("stars", 0) + stars_per_referral
                    save_users_data(users_data)
                    
                    # Оповещаем реферера
                    try:
                        username = update.new_chat_member.user.username or update.new_chat_member.user.full_name
                        await bot.send_message(
                            int(referrer_id),
                            f"🎉 Поздравляем! Пользователь {username}, которого вы пригласили, подписался на канал!\n\n"
                            f"💫 Вам начислено {stars_per_referral} {get_stars_word(stars_per_referral)}\n"
                            f"💫 Ваш текущий баланс: {users_data[referrer_id]['stars']} {get_stars_word(users_data[referrer_id]['stars'])}"
                        )
                    except Exception as e:
                        logging.error(f"Ошибка при отправке уведомления рефереру {referrer_id}: {e}")
            
            # Отправляем уведомление пользователю о подписке и доступе к боту
            try:
                message_text = "✅ <b>Спасибо за подписку на канал!</b>\n\n"
                if is_new_referral:
                    message_text += "🎁 Ваш реферер получил вознаграждение за ваше приглашение.\n\n"
                
                message_text += "Теперь вы можете использовать все функции бота и получить свою реферальную ссылку.\n"
                message_text += "Отправьте /link чтобы получить вашу ссылку."
                
                await bot.send_message(int(user_id), message_text)
            except Exception as e:
                logging.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")
