# handlers/keyboard_handler.py
import logging
from aiogram import types, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot import router, bot
from config import ADMIN_IDS
from data import users_data, referral_data, promocodes, save_promocodes, required_channels
from utils import get_stars_word, get_invite_word, save_users_data, save_referral_data
from handlers.subscription import check_subscription, get_subscription_keyboard, get_not_subscribed_channels, \
    get_channels_text


class PromoStates(StatesGroup):
    waiting_for_promo = State()


async def ensure_user_registered(user: types.User) -> None:
    """
    Проверяет наличие пользователя в базе данных и регистрирует его,
    если он не зарегистрирован. Гарантирует наличие пользователя в базе.
    """
    user_id = str(user.id)

    logging.info(f"=== РЕГИСТРАЦИЯ ПОЛЬЗОВАТЕЛЯ {user_id} ===")

    # Проверка данных перед регистрацией
    if user_id not in referral_data:
        logging.info(f"Создание данных реферала для {user_id}")
        bot_info = await bot.get_me()
        referral_data[user_id] = {
            "bot_link": f"https://t.me/{bot_info.username}?start={user_id}",
            "count": 0,
            "username": user.username or user.full_name,
            "referral_activations": []
        }
        save_referral_data(referral_data)

    if user_id not in users_data:
        logging.info(f"Регистрация нового пользователя через keyboard_handler: {user_id}")
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


# Создаем основную клавиатуру
def get_main_keyboard() -> types.ReplyKeyboardMarkup:
    """
    Возвращает основную клавиатуру бота с основными функциями.
    """
    keyboard = [
        [types.KeyboardButton(text="👤 Профиль"), types.KeyboardButton(text="⭐ Отзывы")],
        [types.KeyboardButton(text="🎟 Промокод"), types.KeyboardButton(text="🔗 Реферальная ссылка")],
        [types.KeyboardButton(text="📢 Канал")]  # Добавляем новую кнопку в третью строку
    ]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


@router.message(F.text == "👤 Профиль")
async def show_profile(message: types.Message, state: FSMContext) -> None:
    """
    Показывает профиль пользователя: имя, ID, количество звезд и рефералов.
    """
    # Регистрируем пользователя, если его нет в системе
    await ensure_user_registered(message.from_user)

    # Сначала проверяем, находится ли пользователь в каком-то состоянии
    current_state = await state.get_state()
    if current_state:
        # Если пользователь в каком-то состоянии, сначала очищаем его
        await state.clear()

    # Проверяем подписку на все обязательные каналы
    is_subscribed = await check_subscription(message.from_user.id)
    if not is_subscribed:
        not_subscribed_channels = await get_not_subscribed_channels(message.from_user.id)
        channels_text = get_channels_text(not_subscribed_channels)

        await message.answer(
            f"❗ Для доступа к профилю необходимо подписаться на все обязательные каналы.\n\n{channels_text}",
            reply_markup=get_subscription_keyboard()
        )
        return

    user_id = str(message.from_user.id)
    username = message.from_user.username or message.from_user.full_name

    # Получаем данные пользователя
    user_data = users_data.get(user_id, {})
    stars = user_data.get("stars", 0)

    # Получаем количество рефералов
    ref_count = referral_data.get(user_id, {}).get("count", 0)

    profile_text = (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"🙋‍♂️ Имя: {username}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"💫 Звезды: {stars} {get_stars_word(stars)}\n"
        f"👥 Приглашено: {ref_count} {get_invite_word(ref_count)}\n"
    )

    # Создаем инлайн-клавиатуру с кнопкой вывода звезд
    inline_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💰 Вывести звезды", callback_data="withdraw_stars")]
    ])

    await message.answer(profile_text, reply_markup=inline_kb)


# Остальные методы (show_reviews, promo_code_request, process_promo_code, show_ref_link, show_channel, callback_cancel_withdraw)
# остаются без изменений, но также рекомендуется добавить ensure_user_registered в начало каждого метода


@router.message(F.text == "⭐ Отзывы")
async def show_reviews(message: types.Message, state: FSMContext) -> None:
    """
    Отправляет ссылку на канал с отзывами.
    """
    # Регистрируем пользователя, если его нет в системе
    await ensure_user_registered(message.from_user)

    # Сначала проверяем, находится ли пользователь в каком-то состоянии
    current_state = await state.get_state()
    if current_state:
        # Если пользователь в каком-то состоянии, сначала очищаем его
        await state.clear()

    # Проверяем подписку на все обязательные каналы
    is_subscribed = await check_subscription(message.from_user.id)
    if not is_subscribed:
        not_subscribed_channels = await get_not_subscribed_channels(message.from_user.id)
        channels_text = get_channels_text(not_subscribed_channels)

        await message.answer(
            f"❗ Для доступа к отзывам необходимо подписаться на все обязательные каналы.\n\n{channels_text}",
            reply_markup=get_subscription_keyboard()
        )
        return

    await message.answer(
        "⭐ <b>Отзывы наших пользователей</b>\n\n"
        "Перейдите по ссылке ниже, чтобы прочитать отзывы о нашем сервисе и оставить свой:\n"
        "https://t.me/ScroogeMagnat_Otz"
    )


@router.message(F.text == "🎟 Промокод")
async def promo_code_request(message: types.Message, state: FSMContext) -> None:
    """
    Обрабатывает запрос на ввод промокода.
    """
    # Регистрируем пользователя, если его нет в системе
    await ensure_user_registered(message.from_user)

    # Сначала проверяем, находится ли пользователь в каком-то состоянии
    current_state = await state.get_state()
    if current_state:
        # Если пользователь уже в каком-то состоянии, сначала очищаем его
        await state.clear()

    # Проверяем подписку на все обязательные каналы
    is_subscribed = await check_subscription(message.from_user.id)
    if not is_subscribed:
        not_subscribed_channels = await get_not_subscribed_channels(message.from_user.id)
        channels_text = get_channels_text(not_subscribed_channels)

        await message.answer(
            f"❗ Для активации промокода необходимо подписаться на все обязательные каналы.\n\n{channels_text}",
            reply_markup=get_subscription_keyboard()
        )
        return

    await message.answer(
        "🎟 <b>Введите промокод</b>\n\n"
        "Для получения звезд введите действующий промокод."
    )
    await state.set_state(PromoStates.waiting_for_promo)


@router.message(PromoStates.waiting_for_promo)
async def process_promo_code(message: types.Message, state: FSMContext) -> None:
    """
    Обрабатывает введенный промокод.
    """
    # Регистрируем пользователя, если его нет в системе
    await ensure_user_registered(message.from_user)

    # Проверяем подписку на все обязательные каналы
    is_subscribed = await check_subscription(message.from_user.id)
    if not is_subscribed:
        not_subscribed_channels = await get_not_subscribed_channels(message.from_user.id)
        channels_text = get_channels_text(not_subscribed_channels)

        await message.answer(
            f"❗ Для активации промокода необходимо подписаться на все обязательные каналы.\n\n{channels_text}",
            reply_markup=get_subscription_keyboard()
        )
        await state.clear()
        return

    promo_code = message.text.strip().upper()
    user_id = str(message.from_user.id)

    # Используем промокоды из глобальных данных
    from data import promocodes, save_promocodes

    if promo_code in promocodes:
        promo_data = promocodes[promo_code]

        # Проверка на однократное использование
        if promo_data.get("is_single_use", False) and user_id in promo_data.get("used_by", []):
            await message.answer("❌ Вы уже использовали этот промокод.")
            await state.clear()
            return

        # Проверка на лимит активаций
        if "limit" in promo_data and promo_data.get("activations", 0) >= promo_data["limit"]:
            await message.answer("❌ Этот промокод достиг лимита активаций и больше не действителен.")
            await state.clear()
            return

        # Начисление звезд
        stars_amount = promo_data.get("stars", 0)
        if stars_amount > 0:
            if user_id in users_data:
                users_data[user_id]["stars"] = users_data[user_id].get("stars", 0) + stars_amount
                save_users_data(users_data)

                # Обновляем данные промокода
                if promo_data.get("is_single_use", False):
                    # Добавляем пользователя в список использовавших
                    if "used_by" not in promo_data:
                        promo_data["used_by"] = []
                    promo_data["used_by"].append(user_id)

                # Увеличиваем счетчик активаций
                promo_data["activations"] = promo_data.get("activations", 0) + 1

                # Сохраняем обновленные данные промокода
                save_promocodes()

                await message.answer(
                    f"✅ <b>Промокод активирован!</b>\n\n"
                    f"Вам начислено {stars_amount} {get_stars_word(stars_amount)}\n"
                    f"Ваш текущий баланс: {users_data[user_id]['stars']} {get_stars_word(users_data[user_id]['stars'])}"
                )
            else:
                await message.answer("❌ Произошла ошибка. Пожалуйста, перезапустите бота командой /start")
        else:
            await message.answer("❌ Недействительный промокод.")
    else:
        await message.answer("❌ Промокод не найден или истек срок его действия.")

    await state.clear()

@router.message(F.text == "📢 Канал")
async def show_channel(message: types.Message, state: FSMContext) -> None:
    """
    Отправляет ссылку на основной канал.
    """
    # Регистрируем пользователя, если его нет в системе
    await ensure_user_registered(message.from_user)

    # Сначала проверяем, находится ли пользователь в каком-то состоянии
    current_state = await state.get_state()
    if current_state:
        # Если пользователь в каком-то состоянии, сначала очищаем его
        await state.clear()

    # Проверяем подписку на все обязательные каналы
    is_subscribed = await check_subscription(message.from_user.id)
    if not is_subscribed:
        not_subscribed_channels = await get_not_subscribed_channels(message.from_user.id)
        channels_text = get_channels_text(not_subscribed_channels)

        await message.answer(
            f"❗ Для доступа к каналу необходимо подписаться на все обязательные каналы.\n\n{channels_text}",
            reply_markup=get_subscription_keyboard()
        )
        return

    await message.answer(
        "📢 <b>Наш официальный канал</b>\n\n"
        "Перейдите по ссылке, чтобы быть в курсе всех новостей и обновлений:\n"
        "https://t.me/ScroogeMagnat_Info"
    )

@router.message(F.text == "🔗 Реферальная ссылка")
async def show_ref_link(message: types.Message, state: FSMContext) -> None:
    """
    Показывает реферальную ссылку пользователя.
    """
    # Регистрируем пользователя, если его нет в системе
    await ensure_user_registered(message.from_user)

    # Сначала проверяем, находится ли пользователь в каком-то состоянии
    current_state = await state.get_state()
    if current_state:
        # Если пользователь в каком-то состоянии, сначала очищаем его
        await state.clear()

    # Проверяем подписку на все обязательные каналы
    is_subscribed = await check_subscription(message.from_user.id)
    if not is_subscribed:
        not_subscribed_channels = await get_not_subscribed_channels(message.from_user.id)
        channels_text = get_channels_text(not_subscribed_channels)

        await message.answer(
            f"❗ Для получения реферальной ссылки необходимо подписаться на все обязательные каналы.\n\n{channels_text}",
            reply_markup=get_subscription_keyboard()
        )
        return

    from handlers.start import process_subscriber
    await process_subscriber(message.chat, message.from_user)


@router.callback_query(F.data == "cancel_withdraw")
async def callback_cancel_withdraw(callback: types.CallbackQuery) -> None:
    """
    Обработчик отмены вывода звезд, возвращает к отображению профиля
    """
    # Регистрируем пользователя, если его нет в системе
    await ensure_user_registered(callback.from_user)

    # Проверяем подписку на все обязательные каналы
    is_subscribed = await check_subscription(callback.from_user.id)
    if not is_subscribed:
        await callback.answer("Для доступа к этой функции необходимо подписаться на все обязательные каналы.",
                              show_alert=True)
        return

    user_id = str(callback.from_user.id)
    username = callback.from_user.username or callback.from_user.full_name

    # Получаем данные пользователя
    user_data = users_data.get(user_id, {})
    stars = user_data.get("stars", 0)

    # Получаем количество рефералов
    ref_count = referral_data.get(user_id, {}).get("count", 0)

    profile_text = (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"🙋‍♂️ Имя: {username}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"💫 Звезды: {stars} {get_stars_word(stars)}\n"
        f"👥 Приглашено: {ref_count} {get_invite_word(ref_count)}\n"
    )

    # Создаем инлайн-клавиатуру с кнопкой вывода звезд
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Вывести звезды", callback_data="withdraw_stars")]
    ])

    await callback.message.edit_text(profile_text, reply_markup=inline_kb)
    await callback.answer()