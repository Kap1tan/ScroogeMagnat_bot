# handlers/captcha_handler.py
import random
import logging
from aiogram import types, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from bot import bot, router
from config import ADMIN_IDS
from handlers.subscription import check_subscription, get_subscription_keyboard, get_not_subscribed_channels, \
    get_channels_text
from utils import save_users_data, get_stars_word, save_referral_data, load_json_data

# Список слов для капчи
CAPTCHA_WORDS = [
    "звезда", "планета", "космос", "галактика", "вселенная",
    "ракета", "спутник", "комета", "астероид", "метеорит",
    "солнце", "луна", "земля", "марс", "юпитер",
    "сатурн", "уран", "нептун", "плутон", "меркурий",
    "венера", "орбита", "созвездие", "телескоп", "астронавт",
    "инвестиция", "доход", "прибыль", "финансы", "экономика"
]


class CaptchaStates(StatesGroup):
    waiting_for_captcha = State()


def get_referrer_for_user(user_id: str, referral_data: dict) -> str | None:
    """
    Находит реферера для указанного пользователя.

    :param user_id: ID пользователя
    :param referral_data: Словарь с данными рефералов
    :return: ID реферера или None
    """
    for potential_referrer_id, info in referral_data.items():
        referral_activations = info.get("referral_activations", [])
        if user_id in referral_activations:
            return potential_referrer_id
    return None


async def generate_captcha() -> tuple[str, str]:
    """
    Генерирует случайное слово для капчи.

    Returns:
        tuple: (captcha_word, captcha_message)
    """
    captcha_word = random.choice(CAPTCHA_WORDS)
    captcha_message = (
        "🔐 <b>Капча-проверка</b>\n\n"
        f"Пожалуйста, введите следующее слово: <b>{captcha_word}</b>\n\n"
        "Это необходимо для защиты от ботов."
    )
    return captcha_word, captcha_message


@router.message(CaptchaStates.waiting_for_captcha)
async def process_captcha(message: types.Message, state: FSMContext) -> None:
    """
    Обрабатывает ответ пользователя на капчу.
    """
    # Импортируем здесь, чтобы избежать циклического импорта
    from data import (
        referral_data, users_data,
        captcha_passed_referrals,
        save_captcha_passed_referrals, credited_referrals,
        save_credited_referrals
    )

    # Если это команда /admin и пользователь в списке админов, сразу пропускаем обработку капчи
    if message.text == "/admin" and message.from_user.id in ADMIN_IDS:
        # Очищаем состояние и устанавливаем флаг
        await state.clear()
        await state.update_data(captcha_passed=True)
        # Перенаправляем запрос, но НЕ вызываем напрямую функцию
        # Только освобождаем пользователя от состояния капчи
        return

    # Проверка на другие команды, которые нужно обработать независимо от капчи
    if message.text and message.text.startswith('/'):
        # Для команд очищаем состояние капчи и даем другим обработчикам возможность обработать команду
        await state.clear()
        # Устанавливаем флаг, что капча пройдена (для простоты)
        await state.update_data(captcha_passed=True)
        return

    # Проверка на специальные кнопки, которые должны работать всегда
    special_buttons = ["👤 Профиль", "⭐ Отзывы", "🎟 Промокод", "🔗 Реферальная ссылка", "📢 Канал"]
    if message.text in special_buttons:
        # Для специальных кнопок очищаем состояние капчи и даем другим обработчикам возможность обработать нажатие
        await state.clear()
        # Устанавливаем флаг, что капча пройдена (для простоты)
        await state.update_data(captcha_passed=True)
        return

    user_text = message.text.strip().lower()
    data = await state.get_data()
    captcha_word = data.get("captcha_word", "").lower()

    if user_text == captcha_word:
        # Капча пройдена
        user_id = str(message.from_user.id)
        logging.info(f"Пользователь {user_id} успешно прошел капчу")

        # Получаем данные о реферальной ссылке из состояния
        ref_data = await state.get_data()
        referrer_id = ref_data.get("referrer_id")
        logging.info(f"Найден реферер из состояния для пользователя {user_id}: {referrer_id}")

        # Если не нашли в состоянии, пробуем найти через стандартную функцию
        if not referrer_id:
            referrer_id = get_referrer_for_user(user_id, referral_data)
            logging.info(f"Найден реферер через поиск в данных для пользователя {user_id}: {referrer_id}")

        # Если реферер найден и пользователь еще не был засчитан как реферал
        if referrer_id and referrer_id in users_data and user_id not in captcha_passed_referrals and user_id not in credited_referrals:
            logging.info(f"Засчитываем пользователя {user_id} как реферала для {referrer_id} после капчи")

            # Отмечаем, что этот пользователь прошел капчу и засчитан как реферал
            captcha_passed_referrals.add(user_id)
            save_captcha_passed_referrals()
            logging.info(f"Пользователь {user_id} добавлен в список прошедших капчу")

            # Добавляем в список засчитанных рефералов
            credited_referrals.add(user_id)
            save_credited_referrals()
            logging.info(f"Пользователь {user_id} добавлен в список засчитанных рефералов")

            # Обновляем счетчик рефералов
            if referrer_id in referral_data:
                referral_data[referrer_id]["count"] = referral_data[referrer_id].get("count", 0) + 1
                logging.info(
                    f"Увеличен счетчик рефералов для {referrer_id} после прохождения капчи: {referral_data[referrer_id]['count']}")

                # Добавляем в список активаций, если его нет
                if "referral_activations" not in referral_data[referrer_id]:
                    referral_data[referrer_id]["referral_activations"] = []

                if user_id not in referral_data[referrer_id]["referral_activations"]:
                    referral_data[referrer_id]["referral_activations"].append(user_id)
            else:
                referral_data[referrer_id] = {
                    "bot_link": f"https://t.me/{(await bot.get_me()).username}?start={referrer_id}",
                    "count": 1,
                    "username": users_data.get(referrer_id, {}).get("username", "Неизвестно"),
                    "referral_activations": [user_id]
                }
                logging.info(f"Создана новая запись реферала для {referrer_id}")

            save_referral_data(referral_data)
            logging.info(f"Данные рефералов сохранены")

            # Начисляем звезды рефереру
            if referrer_id in users_data:
                # Прямое чтение актуального значения звезд за реферала из файла
                stars_config = load_json_data("data/config.json")
                current_stars_per_referral = stars_config.get("stars_per_referral",
                                                              2)  # Используем 2 как значение по умолчанию
                logging.info(f"Текущее значение звезд за реферала (прочитано из файла): {current_stars_per_referral}")

                current_stars = users_data[referrer_id].get("stars", 0)
                users_data[referrer_id]["stars"] = current_stars + current_stars_per_referral
                save_users_data(users_data)
                logging.info(
                    f"Начислены звезды рефереру {referrer_id}: {current_stars_per_referral}, всего: {users_data[referrer_id]['stars']}")

                try:
                    # Отправляем уведомление рефереру
                    await bot.send_message(
                        int(referrer_id),
                        f"🎉 Поздравляем! Пользователь {message.from_user.username or message.from_user.full_name} прошел капчу по вашей реферальной ссылке!\n\n"
                        f"💫 Вам начислено {current_stars_per_referral} {get_stars_word(current_stars_per_referral)}\n"
                        f"💫 Ваш текущий баланс: {users_data[referrer_id]['stars']} {get_stars_word(users_data[referrer_id]['stars'])}"
                    )
                    logging.info(f"Отправлено уведомление рефереру {referrer_id}")
                except Exception as e:
                    logging.error(f"Ошибка при отправке уведомления рефереру {referrer_id}: {e}")

        # Очищаем состояние
        await state.clear()
        # Устанавливаем флаг, что капча пройдена
        await state.update_data(captcha_passed=True)

        # Проверяем подписку на обязательные каналы
        is_subscribed = await check_subscription(message.from_user.id)

        if not is_subscribed:
            not_subscribed_channels = await get_not_subscribed_channels(message.from_user.id)
            channels_text = get_channels_text(not_subscribed_channels)

            text = (
                '✅ <b>Капча пройдена!</b>\n\n'
                f'Для доступа к боту необходимо подписаться на все обязательные каналы.\n\n'
                f'{channels_text}'
            )
            await message.answer(text, reply_markup=get_subscription_keyboard())
        else:
            # Если уже подписан, продолжаем работу бота
            from handlers.start import show_main_menu
            await show_main_menu(message)
    else:
        # Капча не пройдена, генерируем новую
        captcha_word, captcha_message = await generate_captcha()
        await state.update_data(captcha_word=captcha_word)
        await message.answer(
            f"❌ Неверное слово. Попробуйте еще раз.\n\n{captcha_message}"
        )