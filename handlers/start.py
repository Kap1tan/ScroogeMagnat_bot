# В файле start.py
# Изменим приоритеты обработчиков, чтобы команды обрабатывались раньше

import logging
from aiogram import types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from bot import bot, router
from config import ADMIN_IDS
from data import referral_data, users_data, stars_per_referral, required_channels
from utils import save_referral_data, save_users_data, get_stars_word, get_invite_word
from handlers.subscription import check_subscription, get_subscription_keyboard, get_not_subscribed_channels, \
    get_channels_text
from handlers.captcha_handler import CaptchaStates, generate_captcha


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
            "stars": 0,  # Добавляем поле звёзд (внутренний баланс)
            "stars_for_subscription_received": False  # Добавляем флаг для отслеживания получения звезд за подписку
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

    # Проверяем наличие флага stars_for_subscription_received и добавляем, если его нет
    if "stars_for_subscription_received" not in users_data[user_id]:
        users_data[user_id]["stars_for_subscription_received"] = False
        save_users_data(users_data)

    return False


async def process_subscriber(chat: types.Chat, user: types.User) -> None:
    """
    Обрабатывает подписчика: создаёт или выдает реферальную ссылку на бота.
    """
    user_id = str(user.id)

    logging.info(f"=== ГЕНЕРАЦИЯ РЕФЕРАЛЬНОЙ ССЫЛКИ ДЛЯ {user_id} ===")

    # Проверяем, есть ли подписка на все обязательные каналы
    is_subscribed = await check_subscription(int(user_id))
    if not is_subscribed:
        not_subscribed_channels = await get_not_subscribed_channels(int(user_id))
        channels_text = get_channels_text(not_subscribed_channels)

        await bot.send_message(
            chat.id,
            f"❗ Для получения реферальной ссылки необходимо подписаться на все обязательные каналы.\n\n{channels_text}",
            reply_markup=get_subscription_keyboard()
        )
        return

    # Создаем или предоставляем существующую ссылку на бота
    bot_info = await bot.get_me()
    bot_username = bot_info.username

    logging.info(f"Проверка существования реферальной ссылки для {user_id}")

    # Проверяем существование записи о рефералах
    if str(user_id) not in referral_data:
        logging.info(f"Создание новой записи реферала для {user_id}")
        referral_data[str(user_id)] = {
            "bot_link": f"https://t.me/{bot_username}?start={user_id}",
            "count": 0,
            "username": user.username or user.full_name,
            "referral_activations": []  # Добавляем пустой список для отслеживания активаций
        }
        save_referral_data(referral_data)

    bot_link = referral_data[str(user_id)].get("bot_link") or f"https://t.me/{bot_username}?start={user_id}"
    referral_data[str(user_id)]["bot_link"] = bot_link
    save_referral_data(referral_data)

    # Получаем текущее количество звёзд пользователя
    user_stars = users_data.get(str(user_id), {}).get("stars", 0)

    # Получаем актуальное количество звезд за реферала из конфигурационного файла
    from utils import load_json_data
    stars_config = load_json_data("data/config.json")
    current_stars_per_referral = stars_config.get("stars_per_referral", 2)  # Используем 2 как значение по умолчанию

    logging.info(f"Отправка реферальной ссылки для {user_id} с {current_stars_per_referral} звездами за реферала")
    await bot.send_message(
        chat.id,
        f"✅ <b>Ваша персональная реферальная ссылка:</b>\n\n"
        f"<code>{bot_link}</code>\n\n"
        f"Поделитесь ею с друзьями! Когда они перейдут по ссылке и подпишутся на все обязательные каналы, "
        f"вы получите <b>{current_stars_per_referral} {get_stars_word(current_stars_per_referral)}</b> и +1 к счетчику приглашенных.\n\n"
        f"💫 Ваш текущий баланс: <b>{user_stars} {get_stars_word(user_stars)}</b>"
    )


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext) -> None:
    # Регистрируем пользователя
    await ensure_user_registered(message.from_user)

    # Проверяем наличие реферального параметра
    args = message.text.split()
    if len(args) > 1:
        referrer_id = args[1]
        # Если есть реферер, сохраняем это в данных рефералов
        if referrer_id.isdigit() and referrer_id in users_data:
            # Сохраняем ID реферера в состоянии для использования при обработке капчи
            await state.update_data(referrer_id=referrer_id)
            logging.info(f"Сохранен реферер {referrer_id} для пользователя {message.from_user.id} в состоянии")

            # Добавляем пользователя в список активированных по реферальной ссылке
            user_id = str(message.from_user.id)

            logging.info(f"Получен старт по реферальной ссылке: пользователь {user_id}, реферер {referrer_id}")

            if referrer_id in referral_data:
                # Создаем запись активаций, если ещё нет
                if "referral_activations" not in referral_data[referrer_id]:
                    referral_data[referrer_id]["referral_activations"] = []
                    logging.info(f"Создан новый список активаций для реферера {referrer_id}")

                # Сохраняем ID пользователя, активировавшего ссылку
                if user_id not in referral_data[referrer_id]["referral_activations"]:
                    referral_data[referrer_id]["referral_activations"].append(user_id)
                    logging.info(f"Пользователь {user_id} добавлен в список активаций реферера {referrer_id}")
                    save_referral_data(referral_data)
                    logging.info(f"Данные рефералов сохранены")
                else:
                    logging.info(f"Пользователь {user_id} уже в списке активаций реферера {referrer_id}")
            else:
                # Создаем запись для реферера, если её ещё нет
                referral_data[referrer_id] = {
                    "bot_link": f"https://t.me/{(await bot.get_me()).username}?start={referrer_id}",
                    "count": 0,
                    "username": users_data[referrer_id]["username"],
                    "referral_activations": [user_id]
                }
                logging.info(f"Создана новая запись для реферера {referrer_id} с активацией пользователя {user_id}")
                save_referral_data(referral_data)
                logging.info(f"Данные рефералов сохранены")

            # Сообщаем пользователю, что звезды будут начислены при подписке на каналы
            channels_count = len(required_channels)
            channels_info = ""
            if channels_count > 0:
                if channels_count == 1:
                    channels_info = f"\n\nНеобходимо подписаться на канал."
                elif 2 <= channels_count <= 4:
                    channels_info = f"\n\nНеобходимо подписаться на {channels_count} канала."
                else:
                    channels_info = f"\n\nНеобходимо подписаться на {channels_count} каналов."

            await message.answer(
                "👋 <b>Добро пожаловать!</b>\n\n"
                "Вы перешли по реферальной ссылке. Для получения доступа к боту "
                f"вам необходимо подписаться на все обязательные каналы.{channels_info}"
            )

    # Проверяем, прошел ли пользователь капчу
    data = await state.get_data()
    captcha_passed = data.get("captcha_passed", False)

    if not captcha_passed:
        # Пользователь не прошел капчу, отправляем её
        captcha_word, captcha_message = await generate_captcha()
        await state.update_data(captcha_word=captcha_word)
        await state.set_state(CaptchaStates.waiting_for_captcha)
        await message.answer(captcha_message)
        return

    # Проверяем подписку на каналы
    is_subscribed = await check_subscription(message.from_user.id)
    if not is_subscribed:
        not_subscribed_channels = await get_not_subscribed_channels(message.from_user.id)
        channels_text = get_channels_text(not_subscribed_channels)

        text = (
            '<b>Добро пожаловать!</b>\n\n'
            f'Для доступа к боту необходимо подписаться на все обязательные каналы.\n\n'
            f'{channels_text}'
        )
        await message.answer(text, reply_markup=get_subscription_keyboard())
    else:
        await show_main_menu(message)


@router.message(Command("link"))
async def cmd_link(message: types.Message, state: FSMContext) -> None:
    # Проверяем, прошел ли пользователь капчу
    data = await state.get_data()
    captcha_passed = data.get("captcha_passed", False)

    if not captcha_passed:
        # Пользователь не прошел капчу, отправляем её
        captcha_word, captcha_message = await generate_captcha()
        await state.update_data(captcha_word=captcha_word)
        await state.set_state(CaptchaStates.waiting_for_captcha)
        await message.answer(captcha_message)
        return

    # Проверяем подписку на каналы
    is_subscribed = await check_subscription(message.from_user.id)
    if not is_subscribed:
        not_subscribed_channels = await get_not_subscribed_channels(message.from_user.id)
        channels_text = get_channels_text(not_subscribed_channels)

        await message.answer(
            f"❗ Для получения реферальной ссылки необходимо подписаться на все обязательные каналы.\n\n{channels_text}",
            reply_markup=get_subscription_keyboard()
        )
        return

    await process_subscriber(message.chat, message.from_user)


async def show_main_menu(message: types.Message) -> None:
    """
    Показывает главное меню бота.
    """
    text = (
        '<b>Добро пожаловать!</b>\n\n'
        "💫 <b>Зарабатывайте звезды:</b>\n"
        "- Приглашайте друзей и увеличивайте статистику\n"
        "- Обменивайте звезды на ценные призы\n\n"
        "Используйте кнопки внизу для навигации."
    )

    # Добавляем только основную клавиатуру
    from handlers.keyboard_handler import get_main_keyboard
    await message.answer(text, reply_markup=get_main_keyboard())


@router.callback_query(F.data == "check_subscription")
async def callback_check_subscription(callback: types.CallbackQuery) -> None:
    # Регистрируем пользователя
    await ensure_user_registered(callback.from_user)

    user_id = str(callback.from_user.id)
    logging.info(f"Проверка подписки для колбэка: user_id={user_id}")

    is_subscribed = await check_subscription(callback.from_user.id)
    logging.info(f"Результат проверки подписки: {is_subscribed}")

    if is_subscribed:
        # Если пользователь подписался, проверяем получил ли он уже звезды
        stars_for_subscription_received = users_data.get(user_id, {}).get("stars_for_subscription_received", False)
        logging.info(f"Статус получения звезд за подписку: {stars_for_subscription_received}")

        # Если еще не получал, отмечаем, что он подписался
        if not stars_for_subscription_received and user_id in users_data:
            users_data[user_id]["stars_for_subscription_received"] = True
            save_users_data(users_data)
            logging.info(f"Отмечено, что пользователь {user_id} получил доступ по подписке")

            # Показываем основное меню с информацией о начислении звезд
            from handlers.keyboard_handler import get_main_keyboard

            text = (
                '<b>Спасибо за подписку!</b>\n\n'
                "💫 <b>Зарабатывайте звезды:</b>\n"
                "- Приглашайте друзей и увеличивайте статистику\n"
                "- Обменивайте звезды на ценные призы\n\n"
                "Используйте кнопки внизу для навигации."
            )
        else:
            # Если уже получал звезды, просто показываем основное меню
            from handlers.keyboard_handler import get_main_keyboard

            text = (
                '<b>Спасибо за подписку!</b>\n\n'
                "💫 <b>Зарабатывайте звезды:</b>\n"
                "- Приглашайте друзей и увеличивайте статистику\n"
                "- Обменивайте звезды на ценные призы\n\n"
                "Используйте кнопки внизу для навигации."
            )

        logging.info("Отправка основного меню после подписки")
        # Отправляем новое сообщение вместо редактирования текущего
        await callback.message.delete()  # Удаляем старое сообщение с кнопкой подписки
        await callback.message.answer(text, reply_markup=get_main_keyboard())
    else:
        not_subscribed_channels = await get_not_subscribed_channels(callback.from_user.id)
        channels_text = get_channels_text(not_subscribed_channels)

        await callback.answer(f"Вы еще не подписались на все обязательные каналы. Подпишитесь, чтобы продолжить.",
                              show_alert=True)


async def ensure_user_registered(user: types.User) -> None:
    """
    Проверяет наличие пользователя в базе данных и регистрирует его,
    если он не зарегистрирован. Применяется для всех обработчиков,
    чтобы гарантировать наличие пользователя в базе.
    """
    user_id = str(user.id)
    if user_id not in users_data:
        logging.info(f"Регистрация нового пользователя: {user_id}")
        users_data[user_id] = {
            "username": user.username or user.full_name,
            "status": "active",
            "stars": 0,
            "stars_for_subscription_received": False
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
    elif users_data[user_id].get("status") == "removed":
        users_data[user_id]["status"] = "active"
        save_users_data(users_data)

    # Добавляем флаг stars_for_subscription_received, если его нет
    if "stars_for_subscription_received" not in users_data[user_id]:
        users_data[user_id]["stars_for_subscription_received"] = False
        save_users_data(users_data)


# Делаем обработчик текстовых сообщений самым последним по приоритету
# Это важно, чтобы команды обрабатывались перед ним
@router.message(F.text, flags={"allow_in_processed": True})
async def process_unknown_message(message: types.Message, state: FSMContext) -> None:
    """
    Обрабатывает все текстовые сообщения, которые не попали под специальные обработчики.
    """
    # Регистрируем пользователя
    await ensure_user_registered(message.from_user)

    from handlers.keyboard_handler import show_profile, promo_code_request, show_ref_link, show_reviews, show_channel

    text = message.text.strip()

    # Проверяем, находится ли пользователь в состоянии ожидания ввода капчи
    current_state = await state.get_state()

    # Если пользователь находится в состоянии ввода промокода, обрабатываем сообщение как промокод
    if current_state == "PromoStates:waiting_for_promo":
        from handlers.keyboard_handler import process_promo_code
        await process_promo_code(message, state)
        return

    # Если пользователь находится в состоянии капчи, не перехватываем его сообщения
    if current_state == "CaptchaStates:waiting_for_captcha":
        # Передадим обработку соответствующему обработчику
        return

    # Проверяем подписку на все каналы
    is_subscribed = await check_subscription(message.from_user.id)
    if not is_subscribed:
        not_subscribed_channels = await get_not_subscribed_channels(message.from_user.id)
        channels_text = get_channels_text(not_subscribed_channels)

        await message.answer(
            f"❗ Для доступа к боту необходимо подписаться на все обязательные каналы.\n\n{channels_text}",
            reply_markup=get_subscription_keyboard()
        )
        return

    # Проверяем, совпадает ли сообщение с одной из кнопок
    if text == "👤 Профиль":
        await show_profile(message, state)
    elif text == "🎟 Промокод":
        await promo_code_request(message, state)
    elif text == "🔗 Реферальная ссылка":
        await show_ref_link(message, state)
    elif text == "⭐ Отзывы":
        await show_reviews(message, state)
    elif text == "📢 Канал":
        await show_channel(message, state)
    else:
        # Если сообщение не совпадает ни с одной кнопкой, отправляем подсказку
        await message.answer(
            "Используйте кнопки внизу для навигации или следующие команды:\n"
            "/start - перезапуск бота\n"
            "/link - получить реферальную ссылку"
        )