import logging
from aiogram import types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot import bot, router
from config import CHANNEL_ID, ADMIN_IDS
from data import referral_data, users_data, stars_per_referral
# Исправляем импорты - добавляем get_invite_word
from utils import save_referral_data, save_users_data, get_stars_word, get_invite_word
from handlers.subscription import check_subscription, get_subscription_keyboard


async def register_user(user: types.User) -> bool:
    """
    Регистрирует пользователя, если его нет в файле.
    Если регистрация прошла успешно (новый пользователь), возвращает True,
    а также отправляет сообщение админам.
    """
    user_id = str(user.id)
    if user_id not in users_data:
        users_data[user_id] = {
            "username": user.username or user.full_name,
            "status": "active",
            "stars": 0  # Добавляем поле звёзд (внутренний баланс)
        }
        save_users_data(users_data)
        # Отправляем сообщение админам о регистрации нового пользователя
        message_text = (
            f"Зарегистрирован новый пользователь: "
            f"<a href='tg://user?id={user.id}'>{user.username or user.full_name}</a>"
        )
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, message_text)
            except Exception as e:
                logging.error(f"Ошибка при отправке сообщения админу {admin_id}: {e}")
        return True
    # Если пользователь уже есть, но статус "removed", меняем на "active"
    elif users_data[user_id].get("status") == "removed":
        users_data[user_id]["status"] = "active"
        save_users_data(users_data)
    return False


async def process_subscriber(chat: types.Chat, user: types.User) -> None:
    """
    Обрабатывает подписчика: создаёт или выдает реферальную ссылку на бота.
    """
    user_id = user.id

    # Проверяем, есть ли подписка на канал
    is_subscribed = await check_subscription(user_id)
    if not is_subscribed:
        await bot.send_message(
            chat.id,
            "❗ Для получения реферальной ссылки необходимо подписаться на наш канал.",
            reply_markup=get_subscription_keyboard()
        )
        return

    # Создаем или предоставляем существующую ссылку на бота
    bot_info = await bot.get_me()
    bot_username = bot_info.username

    if str(user_id) in referral_data and referral_data[str(user_id)].get("bot_link"):
        bot_link = referral_data[str(user_id)]["bot_link"]
    else:
        bot_link = f"https://t.me/{bot_username}?start={user_id}"
        referral_data[str(user_id)] = {
            "bot_link": bot_link,
            "count": 0,
            "username": user.username or user.full_name
        }
        save_referral_data(referral_data)

    # Получаем текущее количество звёзд
    user_stars = users_data.get(str(user_id), {}).get("stars", 0)

    await bot.send_message(
        chat.id,
        f"✅ <b>Ваша персональная реферальная ссылка:</b>\n\n"
        f"<code>{bot_link}</code>\n\n"
        f"Поделитесь ею с друзьями, чтобы получать звёзды за каждого приглашенного друга !\n\n"
        f"💫 Ваш текущий баланс: <b>{user_stars} {get_stars_word(user_stars)}</b>\n"
        f"💰 За каждого приглашенного вы получите <b>{stars_per_referral} {get_stars_word(stars_per_referral)}</b>"
    )


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    # Проверяем наличие реферального параметра
    args = message.text.split()
    if len(args) > 1:
        referrer_id = args[1]
        # Регистрируем пользователя
        new_user = await register_user(message.from_user)
        # Если пользователь новый и есть реферер - начисляем звезды
        if new_user and referrer_id.isdigit() and referrer_id in users_data:
            # Добавляем в список засчитанных рефералов
            from data import credited_referrals, save_credited_referrals
            new_user_id = str(message.from_user.id)
            # Проверяем, не был ли уже засчитан этот пользователь
            if new_user_id not in credited_referrals:
                credited_referrals.add(new_user_id)
                save_credited_referrals()

                # Обновляем статистику рефералов
                if referrer_id in referral_data:
                    referral_data[referrer_id]["count"] += 1
                else:
                    referral_data[referrer_id] = {
                        "bot_link": f"https://t.me/{(await bot.get_me()).username}?start={referrer_id}",
                        "count": 1,
                        "username": users_data[referrer_id]["username"]
                    }
                save_referral_data(referral_data)

                # Начисляем звезды рефереру
                users_data[referrer_id]["stars"] = users_data[referrer_id].get("stars", 0) + stars_per_referral
                save_users_data(users_data)

                # Оповещаем реферера
                try:
                    username = message.from_user.username or message.from_user.full_name
                    await bot.send_message(
                        int(referrer_id),
                        f"🎉 Поздравляем! По вашей ссылке зарегистрировался новый пользователь: {username}\n\n"
                        f"💫 Вам начислено {stars_per_referral} {get_stars_word(stars_per_referral)}\n"
                        f"💫 Ваш текущий баланс: {users_data[referrer_id]['stars']} {get_stars_word(users_data[referrer_id]['stars'])}"
                    )
                except Exception as e:
                    logging.error(f"Ошибка при отправке уведомления рефереру {referrer_id}: {e}")
    else:
        # Обычная регистрация пользователя
        await register_user(message.from_user)

    # Проверяем подписку на канал
    is_subscribed = await check_subscription(message.from_user.id)
    if not is_subscribed:
        text = (
            '<b>Добро пожаловать!</b>\n\n'
            'Для доступа к боту необходимо подписаться на наш канал.'
        )
        await message.answer(text, reply_markup=get_subscription_keyboard())
    else:
        text = (
            '<b>Добро пожаловать!</b>\n\n'
            "💫 <b>Зарабатывайте звезды:</b>\n"
            "- Приглашайте друзей и получайте звезды\n"
            "- Обменивайте звезды на ценные призы\n\n"
            "Нажмите кнопку ниже, чтобы получить вашу персональную реферальную ссылку."
        )
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Получить реферальную ссылку", callback_data="get_ref_link")],
            [InlineKeyboardButton(text="💫 Мои звезды", callback_data="my_stars")]
        ])
        await message.answer(text, reply_markup=inline_kb)


@router.message(Command("link"))
async def cmd_link(message: types.Message) -> None:
    # Проверяем подписку на канал
    is_subscribed = await check_subscription(message.from_user.id)
    if not is_subscribed:
        await message.answer(
            "❗ Для получения реферальной ссылки необходимо подписаться на наш канал.",
            reply_markup=get_subscription_keyboard()
        )
        return

    await process_subscriber(message.chat, message.from_user)


@router.message(Command("stars"))
async def cmd_stars(message: types.Message) -> None:
    # Проверяем подписку на канал
    is_subscribed = await check_subscription(message.from_user.id)
    if not is_subscribed:
        await message.answer(
            "❗ Для доступа к боту необходимо подписаться на наш канал.",
            reply_markup=get_subscription_keyboard()
        )
        return

    user_id = str(message.from_user.id)
    stars = users_data.get(user_id, {}).get("stars", 0)
    referrals_count = referral_data.get(user_id, {}).get("count", 0)

    await message.answer(
        f"💫 <b>Ваша статистика:</b>\n\n"
        f"Количество звезд: <b>{stars} {get_stars_word(stars)}</b>\n"
        f"Приглашено друзей: <b>{referrals_count} {get_invite_word(referrals_count)}</b>\n\n"
        f"За каждого нового приглашенного вы получаете <b>{stars_per_referral} {get_stars_word(stars_per_referral)}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Вывести звезды", callback_data="withdraw_stars")]
        ])
    )


@router.callback_query(F.data == "check_subscription")
async def callback_check_subscription(callback: types.CallbackQuery) -> None:
    is_subscribed = await check_subscription(callback.from_user.id)
    if is_subscribed:
        # Если пользователь подписался, показываем основное меню
        text = (
            '<b>Спасибо за подписку!</b>\n\n'
            "💫 <b>Зарабатывайте звезды:</b>\n"
            "- Приглашайте друзей и получайте звезды\n"
            "- Обменивайте звезды на ценные призы\n\n"
            "Нажмите кнопку ниже, чтобы получить вашу персональную реферальную ссылку."
        )
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Получить реферальную ссылку", callback_data="get_ref_link")],
            [InlineKeyboardButton(text="💫 Мои звезды", callback_data="my_stars")]
        ])
        await callback.message.edit_text(text, reply_markup=inline_kb)
    else:
        await callback.answer("Вы еще не подписались на канал. Подпишитесь, чтобы продолжить.", show_alert=True)


@router.callback_query(F.data == "get_ref_link")
async def callback_get_ref_link(callback: types.CallbackQuery) -> None:
    await process_subscriber(callback.message.chat, callback.from_user)
    await callback.answer()


@router.callback_query(F.data == "my_stars")
async def callback_my_stars(callback: types.CallbackQuery) -> None:
    user_id = str(callback.from_user.id)
    stars = users_data.get(user_id, {}).get("stars", 0)
    referrals_count = referral_data.get(user_id, {}).get("count", 0)

    await callback.message.edit_text(
        f"💫 <b>Ваша статистика:</b>\n\n"
        f"Количество звезд: <b>{stars} {get_stars_word(stars)}</b>\n"
        f"Приглашено друзей: <b>{referrals_count} {get_invite_word(referrals_count)}</b>\n\n"
        f"За каждого нового приглашенного вы получаете <b>{stars_per_referral} {get_stars_word(stars_per_referral)}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Вывести звезды", callback_data="withdraw_stars")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "withdraw_stars")
async def callback_withdraw_stars(callback: types.CallbackQuery) -> None:
    user_id = str(callback.from_user.id)
    stars = users_data.get(user_id, {}).get("stars", 0)

    if stars < 15:
        await callback.answer("У вас недостаточно звезд для вывода. Минимум 15 звезд.", show_alert=True)
        return

    # Создаем клавиатуру с доступными опциями вывода
    keyboard = []

    # Добавляем доступные кнопки в зависимости от баланса
    if stars >= 15:
        keyboard.append([InlineKeyboardButton(text="Вывести 15 звезд", callback_data="withdraw_15")])
    if stars >= 25:
        keyboard.append([InlineKeyboardButton(text="Вывести 25 звезд", callback_data="withdraw_25")])
    if stars >= 50:
        keyboard.append([InlineKeyboardButton(text="Вывести 50 звезд", callback_data="withdraw_50")])

    # Добавляем кнопку возврата
    keyboard.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="my_stars")])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(
        f"💰 <b>Вывод звезд</b>\n\n"
        f"У вас <b>{stars} {get_stars_word(stars)}</b>\n\n"
        f"Выберите количество звезд для вывода:",
        reply_markup=inline_kb
    )
    await callback.answer()


# Добавьте новые обработчики для каждого номинала
@router.callback_query(F.data == "withdraw_15")
async def callback_withdraw_15(callback: types.CallbackQuery) -> None:
    await process_withdraw(callback, 15)


@router.callback_query(F.data == "withdraw_25")
async def callback_withdraw_25(callback: types.CallbackQuery) -> None:
    await process_withdraw(callback, 25)


@router.callback_query(F.data == "withdraw_50")
async def callback_withdraw_50(callback: types.CallbackQuery) -> None:
    await process_withdraw(callback, 50)


# Общая функция для обработки вывода любого количества звезд
async def process_withdraw(callback: types.CallbackQuery, amount: int) -> None:
    user_id = str(callback.from_user.id)
    stars = users_data.get(user_id, {}).get("stars", 0)
    username = callback.from_user.username or callback.from_user.full_name

    if stars < amount:
        await callback.answer(f"У вас недостаточно звезд для вывода {amount} {get_stars_word(amount)}.",
                              show_alert=True)
        return

    # Отправляем заявку админам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💰 <b>Заявка на вывод звезд</b>\n\n"
                f"Пользователь: <a href='tg://user?id={callback.from_user.id}'>{username}</a>\n"
                f"ID: <code>{callback.from_user.id}</code>\n"
                f"Количество звезд: <b>{amount} {get_stars_word(amount)}</b>"
            )
        except Exception as e:
            logging.error(f"Ошибка при отправке заявки админу {admin_id}: {e}")

    # Списываем звезды у пользователя
    users_data[user_id]["stars"] = stars - amount
    save_users_data(users_data)

    await callback.message.edit_text(
        f"✅ <b>Заявка на вывод {amount} {get_stars_word(amount)} успешно отправлена!</b>\n\n"
        f"Администратор свяжется с вами для уточнения деталей.\n"
        f"Ваш текущий баланс: <b>{users_data[user_id]['stars']} {get_stars_word(users_data[user_id]['stars'])}</b>\n"
        f"Спасибо за использование нашего бота!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 На главную", callback_data="back_to_main")]
        ])
    )
    await callback.answer(f"Заявка отправлена! Списано {amount} {get_stars_word(amount)}.", show_alert=True)


@router.callback_query(F.data == "back_to_main")
async def callback_back_to_main(callback: types.CallbackQuery) -> None:
    text = (
        '<b>Главное меню</b>\n\n'
        "💫 <b>Зарабатывайте звезды:</b>\n"
        "- Приглашайте друзей и получайте звезды\n"
        "- Обменивайте звезды на ценные призы\n\n"
        "Выберите нужный раздел:"
    )
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Получить реферальную ссылку", callback_data="get_ref_link")],
        [InlineKeyboardButton(text="💫 Мои звезды", callback_data="my_stars")]
    ])
    await callback.message.edit_text(text, reply_markup=inline_kb)
    await callback.answer()
