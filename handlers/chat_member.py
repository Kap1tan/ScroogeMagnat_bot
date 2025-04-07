# handlers/chat_member.py
import logging
from aiogram import types
from bot import bot, router
from data import users_data, referral_data, credited_referrals, save_credited_referrals, stars_per_referral, \
    required_channels, captcha_passed_referrals
from utils import save_users_data, save_referral_data, get_stars_word
from handlers.keyboard_handler import get_main_keyboard
from handlers.subscription import check_subscription, get_not_subscribed_channels, get_channels_text


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
    logging.info(f"=== НАЧАЛО ОБРАБОТКИ ОБНОВЛЕНИЯ ПОДПИСКИ ===")
    logging.info(f"Обновление статуса участника: chat_id={update.chat.id}")
    logging.info(f"Пользователь: {update.new_chat_member.user.id} ({update.new_chat_member.user.username})")
    logging.info(f"Старый статус: {update.old_chat_member.status}, новый статус: {update.new_chat_member.status}")

    # Проверяем, относится ли обновление к одному из обязательных каналов
    channel_id = str(update.chat.id)
    is_required_channel = any(channel.get('id') == channel_id for channel in required_channels)

    logging.info(f"Канал {channel_id} является обязательным: {is_required_channel}")

    if not is_required_channel:
        logging.info(f"Пропуск: chat_id не соответствует обязательным каналам")
        return

    # Пользователь подписался на канал
    if update.new_chat_member.status in ["member", "administrator", "creator"] and \
            update.old_chat_member.status not in ["member", "administrator", "creator"]:

        user_id = str(update.new_chat_member.user.id)
        logging.info(f"=== ПОДПИСКА ПОЛЬЗОВАТЕЛЯ {user_id} ===")

        # Проверяем, есть ли этот пользователь в данных бота
        if user_id in users_data:
            logging.info(f"Пользователь {user_id} найден в данных бота")

            # Проверяем все подписки пользователя на обязательные каналы
            is_subscribed_to_all = await check_subscription(int(user_id))
            logging.info(f"Проверка всех подписок для {user_id}: {is_subscribed_to_all}")

            # Логируем данные о рефералах перед обработкой
            logging.info("=== ДАННЫЕ О РЕФЕРАЛАХ ===")
            for ref_id, ref_data in referral_data.items():
                logging.info(f"Реферер {ref_id}: {ref_data}")

            # Если подписан на все обязательные каналы
            if is_subscribed_to_all:
                # Проверяем, получал ли пользователь уже звезды за подписку
                stars_for_subscription_received = users_data[user_id].get("stars_for_subscription_received", False)
                logging.info(f"Статус получения звезд за подписку: {stars_for_subscription_received}")

                # Если еще не получал, начисляем звезды только за подписку (не за реферала)
                if not stars_for_subscription_received:
                    users_data[user_id]["stars_for_subscription_received"] = True
                    save_users_data(users_data)
                    logging.info(f"Отмечено, что пользователь {user_id} получил звезды за подписку")

                    # Ищем пользователя в активированных по реферальной ссылке
                    logging.info(f"Начинаем поиск реферрера для пользователя {user_id}")
                    referrer_id = None

                    # Проверяем, не был ли этот пользователь уже засчитан как реферал при прохождении капчи
                    # Если да, то пропускаем повторное начисление
                    if user_id not in credited_referrals and user_id not in captcha_passed_referrals:
                        logging.info(
                            f"Пользователь {user_id} не засчитан как реферал ранее, проверка в дополнение к капче")

                        for potential_referrer_id, info in referral_data.items():
                            referral_activations = info.get("referral_activations", [])
                            logging.info(
                                f"Проверяем реферрера {potential_referrer_id}, активации: {referral_activations}")

                            if user_id in referral_activations:
                                referrer_id = potential_referrer_id
                                logging.info(f"Найден реферер {referrer_id} для пользователя {user_id}")
                                break

                        if referrer_id:
                            logging.info(
                                f"Реферер найден: {referrer_id}. Отмечаем пользователя как реферала при подписке")

                            # Добавляем в список засчитанных рефералов
                            credited_referrals.add(user_id)
                            save_credited_referrals()
                            logging.info(f"Пользователь {user_id} добавлен в список засчитанных рефералов (подписка)")

                            # Обновляем статистику рефералов
                            if referrer_id in referral_data:
                                referral_data[referrer_id]["count"] = referral_data[referrer_id].get("count", 0) + 1
                                logging.info(
                                    f"Увеличен счетчик рефералов для {referrer_id}: {referral_data[referrer_id]['count']}")
                            else:
                                referral_data[referrer_id] = {
                                    "bot_link": f"https://t.me/{(await bot.get_me()).username}?start={referrer_id}",
                                    "count": 1,
                                    "username": users_data.get(referrer_id, {}).get("username", "Неизвестно"),
                                    "referral_activations": []
                                }
                                logging.info(f"Создана новая запись реферала для {referrer_id}")

                            save_referral_data(referral_data)
                            logging.info(f"Данные рефералов сохранены")

                            # Обновляем количество звезд за реферала из config.json
                            from data import update_stars_per_referral
                            current_stars_per_referral = update_stars_per_referral()
                            logging.info(
                                f"Текущее значение звезд за реферала в chat_member: {current_stars_per_referral}")

                            # Начисляем звезды рефереру
                            if referrer_id in users_data:
                                current_stars = users_data[referrer_id].get("stars", 0)
                                users_data[referrer_id]["stars"] = current_stars + current_stars_per_referral
                                save_users_data(users_data)
                                logging.info(
                                    f"Начислены звезды рефереру {referrer_id}: {current_stars_per_referral}, всего: {users_data[referrer_id]['stars']}")

                                # Оповещаем реферера
                                try:
                                    username = update.new_chat_member.user.username or update.new_chat_member.user.full_name
                                    await bot.send_message(
                                        int(referrer_id),
                                        f"🎉 Поздравляем! Пользователь {username}, которого вы пригласили, подписался на все обязательные каналы!\n\n"
                                        f"💫 Вам начислено {current_stars_per_referral} {get_stars_word(current_stars_per_referral)}\n"
                                        f"💫 Ваш текущий баланс: {users_data[referrer_id]['stars']} {get_stars_word(users_data[referrer_id]['stars'])}"
                                    )
                                    logging.info(f"Отправлено уведомление рефереру {referrer_id}")
                                except Exception as e:
                                    logging.error(f"Ошибка при отправке уведомления рефереру {referrer_id}: {e}")
                        else:
                            logging.info(f"Реферер для пользователя {user_id} не найден")
                    else:
                        logging.info(
                            f"Пользователь {user_id} уже засчитан как реферал ранее (при капче), пропускаем обработку")

                    # Оповещаем пользователя о подписке на все каналы
                    try:
                        await bot.send_message(
                            int(user_id),
                            f"🌟 <b>Поздравляем с подпиской на все обязательные каналы!</b>\n\n"
                            f"Теперь вы можете пользоваться всеми функциями бота!",
                            reply_markup=get_main_keyboard()
                        )
                        logging.info(f"Отправлено уведомление о завершении подписки пользователю {user_id}")
                    except Exception as e:
                        logging.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")
                else:
                    logging.info(f"Пользователь {user_id} уже получал звезды за подписку")
            else:
                # Если не подписан на все каналы, сообщаем о необходимости подписаться на остальные
                not_subscribed_channels = await get_not_subscribed_channels(int(user_id))

                if not_subscribed_channels:
                    channels_text = get_channels_text(not_subscribed_channels)

                    try:
                        await bot.send_message(
                            int(user_id),
                            f"👍 <b>Спасибо за подписку!</b>\n\n"
                            f"Для полного доступа к боту необходимо подписаться на все обязательные каналы.\n\n"
                            f"{channels_text}"
                        )
                        logging.info(
                            f"Отправлено сообщение о необходимости подписки на другие каналы пользователю {user_id}")
                    except Exception as e:
                        logging.error(f"Ошибка при отправке сообщения пользователю {user_id}: {e}")
        else:
            logging.info(f"Пользователь {user_id} не найден в данных бота")