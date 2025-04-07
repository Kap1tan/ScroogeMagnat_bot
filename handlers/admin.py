# handlers/admin.py
import os
import tempfile
import asyncio
import logging
from aiogram import types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, ChatAdministratorRights
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from bot import bot, router
from config import ADMIN_IDS
from data import (
    referral_data, users_data, stars_per_referral, save_stars_config,
    promocodes, save_promocodes, required_channels, save_required_channels
)
from utils import get_invite_word, save_referral_data, get_stars_word, save_users_data


class AdminStates(StatesGroup):
    waiting_for_stars_value = State()
    waiting_for_broadcast = State()
    waiting_for_promo_code = State()
    waiting_for_promo_stars = State()
    waiting_for_promo_limit = State()
    waiting_for_channel_id = State()
    waiting_for_channel_link = State()
    waiting_for_channel_name = State()
    waiting_for_edit_channel_id = State()


# Изменяем приоритет команды admin, чтобы она обрабатывалась в первую очередь
@router.message(Command("admin"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_admin(message: types.Message) -> None:
    total_users = len(users_data)
    active_users = sum(1 for u in users_data.values() if u.get("status") == "active")
    removed_users = sum(1 for u in users_data.values() if u.get("status") == "removed")
    total_stars = sum(u.get("stars", 0) for u in users_data.values())
    total_channels = len(required_channels)

    admin_text = (
        "📊 <b>Админ панель</b>:\n\n"
        f"Всего пользователей: <b>{total_users}</b>\n"
        f"Активных пользователей: <b>{active_users}</b>\n"
        f"Удалили бота: <b>{removed_users}</b>\n"
        f"Всего звезд в обороте: <b>{total_stars}</b>\n"
        f"Звезд за подписку: <b>{stars_per_referral}</b>\n"
        f"Обязательных каналов: <b>{total_channels}</b>\n\n"
        "Выберите действие:"
    )
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скачать всех рефералов", callback_data="download_referrals")],
        [InlineKeyboardButton(text="📋 Скачать всех юзеров", callback_data="download_users")],
        [InlineKeyboardButton(text="⭐ Изменить кол-во звезд за подписку", callback_data="change_stars_value")],
        [InlineKeyboardButton(text="🎟 Создать промокод", callback_data="create_promo")],
        [InlineKeyboardButton(text="📢 Управление каналами", callback_data="manage_channels")],
        [InlineKeyboardButton(text="💬 Создать рассылку", callback_data="create_broadcast")]
    ])
    await message.answer(admin_text, reply_markup=inline_kb)


@router.message(Command("referrals"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_referrals(message: types.Message) -> None:
    sorted_refs = sorted(referral_data.items(), key=lambda item: item[1].get("count", 0), reverse=True)
    top10 = sorted_refs[:10]
    if not top10:
        text = "Топ рефералов отсутствует."
    else:
        text = "🏆 <b>Топ рефералов</b>:\n\n"
        rank = 1
        for user_id, info in top10:
            username = info.get("username", "Неизвестно")
            count = info.get("count", 0)
            stars = users_data.get(user_id, {}).get("stars", 0)
            text += f"{rank}. <a href='tg://user?id={user_id}'>{username}</a> — {count} {get_invite_word(count)}, {stars} {get_stars_word(stars)}\n"
            rank += 1
    await message.answer(text)


@router.callback_query(F.data == "download_referrals")
async def callback_download_referrals(callback: types.CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    lines = []
    for user_id, info in referral_data.items():
        username = info.get("username", "Неизвестно")
        count = info.get("count", 0)
        bot_link = info.get("bot_link", "")
        stars = users_data.get(user_id, {}).get("stars", 0)
        line = f"Имя: {username}, ID: {user_id}, Приглашено: {count} {get_invite_word(count)}, Звезд: {stars}, Ссылка: {bot_link}"
        lines.append(line)

    text_content = "\n".join(lines) if lines else "Статистика пуста."

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp.write(text_content)
        tmp_path = tmp.name

    document = FSInputFile(tmp_path)
    await bot.send_document(
        chat_id=callback.from_user.id,
        document=document,
        caption="Статистика по рефералам"
    )

    os.remove(tmp_path)
    await callback.answer()


@router.callback_query(F.data == "download_users")
async def callback_download_users(callback: types.CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    lines = []
    for user_id, info in users_data.items():
        username = info.get("username", "Неизвестно")
        status = info.get("status", "Неизвестно")
        stars = info.get("stars", 0)
        user_link = f"tg://user?id={user_id}"
        line = f"Имя: {username}, Статус: {status}, Звезд: {stars}, Ссылка: {user_link}"
        lines.append(line)

    text_content = "\n".join(lines) if lines else "Список пользователей пуст."

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        tmp.write(text_content)
        tmp_path = tmp.name

    document = FSInputFile(tmp_path)
    await bot.send_document(
        chat_id=callback.from_user.id,
        document=document,
        caption="Список всех пользователей"
    )

    os.remove(tmp_path)
    await callback.answer()


@router.callback_query(F.data == "change_stars_value")
async def callback_change_stars(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    # Загружаем текущее значение прямо из файла
    from utils import load_json_data
    stars_config = load_json_data("data/config.json")
    current_value = stars_config.get("stars_per_referral", 2)

    await callback.message.answer(
        f"Текущее количество звезд за подписку на канал: <b>{current_value}</b>\n\n"
        "Введите новое значение (целое число):"
    )
    await state.set_state(AdminStates.waiting_for_stars_value)
    await callback.answer()


@router.message(AdminStates.waiting_for_stars_value)
async def process_stars_value(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return

    try:
        new_value = int(message.text.strip())
        if new_value <= 0:
            await message.answer("Значение должно быть положительным числом. Попробуйте снова:")
            return

        # Обновляем значение напрямую в файле
        from utils import save_json_data
        save_json_data("data/config.json", {"stars_per_referral": new_value})

        # Для совместимости также обновляем глобальную переменную
        global stars_per_referral
        stars_per_referral = new_value

        # Проверяем, что значение сохранилось
        from utils import load_json_data
        stars_config = load_json_data("data/config.json")
        saved_value = stars_config.get("stars_per_referral", 0)

        # Выводим сообщение об успешном изменении
        await message.answer(f"✅ Количество звезд за подписку изменено на: <b>{saved_value}</b>")
        await state.clear()

    except ValueError:
        await message.answer("Введите корректное целое число:")
    except Exception as e:
        # Добавим подробный вывод ошибки для диагностики
        import traceback
        error_details = traceback.format_exc()
        await message.answer(f"❌ Произошла ошибка при сохранении значения: {str(e)}\n\nПопробуйте снова.")
        logging.error(f"Ошибка при изменении звезд за подписку: {error_details}")


@router.message(AdminStates.waiting_for_stars_value)
async def process_stars_value(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return

    try:
        new_value = int(message.text.strip())
        if new_value <= 0:
            await message.answer("Значение должно быть положительным числом. Попробуйте снова:")
            return

        # Обновляем значение в глобальной переменной (для совместимости)
        global stars_per_referral
        stars_per_referral = new_value

        # Сохраняем новое значение в файл конфигурации
        save_stars_config()

        # Проверяем, что значение сохранилось корректно
        from utils import load_json_data
        stars_config = load_json_data("data/config.json")
        saved_value = stars_config.get("stars_per_referral", 0)

        await message.answer(f"✅ Количество звезд за подписку изменено на: <b>{saved_value}</b>")
        await state.clear()

    except ValueError:
        await message.answer("Введите корректное целое число:")


@router.message(AdminStates.waiting_for_stars_value)
async def process_stars_value(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return

    try:
        new_value = int(message.text.strip())
        if new_value <= 0:
            await message.answer("Значение должно быть положительным числом. Попробуйте снова:")
            return

        # Обновляем значение
        global stars_per_referral
        stars_per_referral = new_value
        save_stars_config()

        # Вызываем функцию обновления в data.py
        from data import update_stars_per_referral
        updated_value = update_stars_per_referral()

        await message.answer(f"✅ Количество звезд за подписку изменено на: <b>{updated_value}</b>")
        await state.clear()

    except ValueError:
        await message.answer("Введите корректное целое число:")


@router.callback_query(F.data == "create_promo")
async def callback_create_promo(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    # Создаем клавиатуру для выбора типа промокода
    promo_type_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Одноразовый (для каждого пользователя)", callback_data="promo_type_single")],
        [InlineKeyboardButton(text="Многоразовый (неограниченно)", callback_data="promo_type_unlimited")],
        [InlineKeyboardButton(text="С ограничением активаций", callback_data="promo_type_limited")]
    ])

    await callback.message.answer(
        "🎟 <b>Создание промокода</b>\n\n"
        "Выберите тип промокода:",
        reply_markup=promo_type_kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("promo_type_"))
async def callback_promo_type(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    promo_type = callback.data.split("_")[2]

    # Сохраняем тип промокода
    await state.update_data(promo_type=promo_type)

    await callback.message.answer(
        "🎟 <b>Создание промокода</b>\n\n"
        "Введите название промокода (только буквы и цифры):"
    )
    await state.set_state(AdminStates.waiting_for_promo_code)
    await callback.answer()


@router.message(AdminStates.waiting_for_promo_code)
async def process_promo_code(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return

    promo_code = message.text.strip().upper()

    # Проверка формата промокода
    if not promo_code.isalnum():
        await message.answer("Промокод должен содержать только буквы и цифры. Попробуйте снова:")
        return

    # Проверка на уникальность
    if promo_code in promocodes:
        await message.answer("Такой промокод уже существует. Введите другой:")
        return

    # Сохраняем код и запрашиваем количество звезд
    await state.update_data(promo_code=promo_code)
    await message.answer(
        f"Промокод <b>{promo_code}</b> будет создан.\n"
        "Введите количество звезд, которое будет начисляться по этому промокоду:"
    )
    await state.set_state(AdminStates.waiting_for_promo_stars)


@router.message(AdminStates.waiting_for_promo_stars)
async def process_promo_stars(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return

    try:
        stars = int(message.text.strip())
        if stars <= 0:
            await message.answer("Количество звезд должно быть положительным числом. Попробуйте снова:")
            return

        # Получаем данные из состояния
        data = await state.get_data()
        promo_code = data.get("promo_code")
        promo_type = data.get("promo_type", "single")

        # Если тип промокода с ограничением активаций, запрашиваем лимит
        if promo_type == "limited":
            await state.update_data(promo_stars=stars)
            await message.answer(
                f"Укажите максимальное количество активаций для промокода <b>{promo_code}</b>:"
            )
            await state.set_state(AdminStates.waiting_for_promo_limit)
            return

        # Создаем промокод в зависимости от типа
        if promo_type == "single":
            promocodes[promo_code] = {
                "stars": stars,
                "is_single_use": True,
                "used_by": []
            }
        elif promo_type == "unlimited":
            promocodes[promo_code] = {
                "stars": stars,
                "is_single_use": False,
                "unlimited": True,
                "activations": 0,
                "used_by": []
            }

        save_promocodes()

        promo_type_text = {
            "single": "одноразовый (для каждого пользователя)",
            "unlimited": "многоразовый (неограниченно)",
            "limited": "с ограничением активаций"
        }

        await message.answer(
            f"✅ Промокод <b>{promo_code}</b> успешно создан!\n"
            f"Тип: {promo_type_text.get(promo_type, 'стандартный')}\n"
            f"При активации пользователь получит {stars} {get_stars_word(stars)}."
        )
        await state.clear()

    except ValueError:
        await message.answer("Введите корректное целое число:")


@router.message(AdminStates.waiting_for_promo_limit)
async def process_promo_limit(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return

    try:
        limit = int(message.text.strip())
        if limit <= 0:
            await message.answer("Лимит активаций должен быть положительным числом. Попробуйте снова:")
            return

        # Получаем данные из состояния
        data = await state.get_data()
        promo_code = data.get("promo_code")
        stars = data.get("promo_stars")

        # Создаем промокод с ограничением активаций
        promocodes[promo_code] = {
            "stars": stars,
            "is_single_use": False,
            "limit": limit,
            "activations": 0,
            "used_by": []
        }
        save_promocodes()

        await message.answer(
            f"✅ Промокод <b>{promo_code}</b> успешно создан!\n"
            f"Тип: с ограничением в {limit} активаций\n"
            f"При активации пользователь получит {stars} {get_stars_word(stars)}."
        )
        await state.clear()

    except ValueError:
        await message.answer("Введите корректное целое число:")


@router.callback_query(F.data == "create_broadcast")
async def callback_create_broadcast(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    await callback.message.answer(
        "Отправьте сообщение, которое нужно разослать всем активным пользователям.\n\n"
        "<b>Поддерживаются:</b> \n"
        "- <b>Текст</b> (без форматирования)\n"
        "- <b>Фото</b> (С описанием, без форматирования)\n"
        "- <b>Видео</b> (С описанием, без форматирования)\n"
        "- <b>Документ</b> (С описанием, без форматирования)\n"
        "- <b>Аудио</b> (С описанием, без форматирования)\n"
        "- <b>Голосовое сообщение</b> (С описанием, без форматирования)\n"
        "- <b>Видеосообщение</b>"
    )
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.answer()


@router.message(AdminStates.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return

    # Подтверждение перед рассылкой
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить отправку", callback_data="confirm_broadcast")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_broadcast")]
    ])

    # Сохраняем сообщение для рассылки в FSM
    if message.photo:
        await state.update_data(type="photo", file_id=message.photo[-1].file_id, caption=message.caption or "")
        await message.answer("📸 Фото получено. Подтвердите отправку:", reply_markup=inline_kb)
    elif message.video:
        await state.update_data(type="video", file_id=message.video.file_id, caption=message.caption or "")
        await message.answer("🎬 Видео получено. Подтвердите отправку:", reply_markup=inline_kb)
    elif message.document:
        await state.update_data(type="document", file_id=message.document.file_id, caption=message.caption or "")
        await message.answer("📄 Документ получен. Подтвердите отправку:", reply_markup=inline_kb)
    elif message.audio:
        await state.update_data(type="audio", file_id=message.audio.file_id, caption=message.caption or "")
        await message.answer("🎵 Аудио получено. Подтвердите отправку:", reply_markup=inline_kb)
    elif message.voice:
        await state.update_data(type="voice", file_id=message.voice.file_id, caption=message.caption or "")
        await message.answer("🎤 Голосовое сообщение получено. Подтвердите отправку:", reply_markup=inline_kb)
    elif message.video_note:
        await state.update_data(type="video_note", file_id=message.video_note.file_id)
        await message.answer("📹 Видеосообщение получено. Подтвердите отправку:", reply_markup=inline_kb)
    elif message.text:
        await state.update_data(type="text", text=message.text)
        await message.answer(f"💬 Сообщение получено:\n\n{message.text}\n\nПодтвердите отправку:",
                             reply_markup=inline_kb)
    else:
        await message.answer("❌ Неподдерживаемый тип сообщения. Попробуйте снова.")
        return


@router.callback_query(F.data == "confirm_broadcast")
async def callback_confirm_broadcast(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    data = await state.get_data()
    message_type = data.get("type")

    # Счетчики для статистики
    sent_count = 0
    error_count = 0

    # Обновляем сообщение о процессе
    progress_message = await callback.message.edit_text("⏳ Рассылка началась. Пожалуйста, подождите...")

    total_users = sum(1 for user_id, info in users_data.items() if info.get("status") == "active")
    processed = 0

    # Отправляем сообщения всем активным пользователям
    for user_id, info in users_data.items():
        if info.get("status") == "active":
            try:
                if message_type == "photo":
                    await bot.send_photo(
                        chat_id=int(user_id),
                        photo=data["file_id"],
                        caption=data.get("caption", "")
                    )
                elif message_type == "video":
                    await bot.send_video(
                        chat_id=int(user_id),
                        video=data["file_id"],
                        caption=data.get("caption", "")
                    )
                elif message_type == "document":
                    await bot.send_document(
                        chat_id=int(user_id),
                        document=data["file_id"],
                        caption=data.get("caption", "")
                    )
                elif message_type == "audio":
                    await bot.send_audio(
                        chat_id=int(user_id),
                        audio=data["file_id"],
                        caption=data.get("caption", "")
                    )
                elif message_type == "voice":
                    await bot.send_voice(
                        chat_id=int(user_id),
                        voice=data["file_id"],
                        caption=data.get("caption", "")
                    )
                elif message_type == "video_note":
                    await bot.send_video_note(
                        chat_id=int(user_id),
                        video_note=data["file_id"]
                    )
                elif message_type == "text":
                    await bot.send_message(
                        chat_id=int(user_id),
                        text=data["text"]
                    )
                sent_count += 1
            except Exception as e:
                logging.error(f"Ошибка при отправке сообщения пользователю {user_id}: {e}")
                error_count += 1

            processed += 1
            # Обновляем прогресс каждые 10 пользователей
            if processed % 10 == 0:
                await progress_message.edit_text(
                    f"⏳ Отправлено {processed}/{total_users} сообщений...\n"
                    f"✅ Успешно: {sent_count}\n"
                    f"❌ Ошибок: {error_count}"
                )

            # Делаем небольшую задержку, чтобы избежать ограничений API
            await asyncio.sleep(0.05)

    # Финальное сообщение с результатами
    await progress_message.edit_text(
        f"✅ Рассылка завершена!\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"- Всего пользователей: {total_users}\n"
        f"- Успешно отправлено: {sent_count}\n"
        f"- Ошибок: {error_count}"
    )

    await state.clear()


@router.callback_query(F.data == "cancel_broadcast")
async def callback_cancel_broadcast(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    await callback.message.edit_text("❌ Рассылка отменена.")
    await state.clear()
    await callback.answer()


@router.message(Command("debug_referrals"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_debug_referrals(message: types.Message) -> None:
    """
    Отладочная команда для просмотра всех данных о рефералах
    """
    # Получаем данные из кредитованных рефералов
    from data import credited_referrals

    debug_text = "<b>Отладочная информация о рефералах:</b>\n\n"

    # Информация по всем рефералам
    debug_text += "<b>Все записи рефералов:</b>\n"
    for user_id, info in referral_data.items():
        username = info.get("username", "Неизвестно")
        count = info.get("count", 0)
        activations = info.get("referral_activations", [])

        debug_text += f"Реферер: {username} ({user_id})\n"
        debug_text += f"Счетчик: {count}\n"
        debug_text += f"Активации: {', '.join(activations) if activations else 'нет'}\n\n"

    # Информация о кредитованных рефералах
    debug_text += "<b>Кредитованные рефералы:</b>\n"
    debug_text += ", ".join(credited_referrals) if credited_referrals else "нет"

    # Разделяем длинное сообщение на части, если нужно
    max_length = 4000
    if len(debug_text) > max_length:
        parts = [debug_text[i:i + max_length] for i in range(0, len(debug_text), max_length)]
        for part in parts:
            await message.answer(part)
    else:
        await message.answer(debug_text)


@router.message(Command("reset_credited"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_reset_credited(message: types.Message) -> None:
    """
    Сбрасывает список кредитованных рефералов
    """
    from data import credited_referrals, save_credited_referrals

    # Сохраняем старые данные для отчета
    old_count = len(credited_referrals)

    # Очищаем список
    credited_referrals.clear()
    save_credited_referrals()

    await message.answer(f"✅ Список кредитованных рефералов очищен. Было удалено {old_count} записей.")


@router.message(Command("fix_user"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_fix_user(message: types.Message) -> None:
    """
    Фиксирует пользователей, которым не начислены звезды
    """
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /fix_user [user_id] [referrer_id]")
        return

    try:
        user_id = args[1]
        referrer_id = args[2] if len(args) > 2 else None

        # Проверяем существование пользователя
        if user_id not in users_data:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            return

        # Отмечаем, что пользователь получил звезды за подписку
        if not users_data[user_id].get("stars_for_subscription_received", False):
            users_data[user_id]["stars_for_subscription_received"] = True
            users_data[user_id]["stars"] = users_data[user_id].get("stars", 0) + stars_per_referral
            save_users_data(users_data)
            await message.answer(f"✅ Пользователю {user_id} начислены звезды за подписку")

        # Если указан реферер, проверяем и фиксируем реферальную связь
        if referrer_id and referrer_id in users_data:
            # Проверяем, есть ли пользователь в списке засчитанных рефералов
            from data import credited_referrals, save_credited_referrals

            if user_id not in credited_referrals:
                credited_referrals.add(user_id)
                save_credited_referrals()

                # Обновляем счетчик рефералов
                if referrer_id in referral_data:
                    referral_data[referrer_id]["count"] = referral_data[referrer_id].get("count", 0) + 1

                    # Добавляем в список активаций, если его нет
                    if "referral_activations" not in referral_data[referrer_id]:
                        referral_data[referrer_id]["referral_activations"] = []

                    if user_id not in referral_data[referrer_id]["referral_activations"]:
                        referral_data[referrer_id]["referral_activations"].append(user_id)

                    save_referral_data(referral_data)
                else:
                    # Создаем новую запись для реферера
                    referral_data[referrer_id] = {
                        "bot_link": f"https://t.me/{(await bot.get_me()).username}?start={referrer_id}",
                        "count": 1,
                        "username": users_data[referrer_id]["username"],
                        "referral_activations": [user_id]
                    }
                    save_referral_data(referral_data)

                # Начисляем звезды рефереру
                users_data[referrer_id]["stars"] = users_data[referrer_id].get("stars", 0) + stars_per_referral
                save_users_data(users_data)

                await message.answer(
                    f"✅ Пользователь {user_id} добавлен как реферал для {referrer_id}, начислены звезды")
            else:
                await message.answer(f"❌ Пользователь {user_id} уже засчитан как реферал")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# Управление обязательными каналами
@router.callback_query(F.data == "manage_channels")
async def callback_manage_channels(callback: types.CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    # Показываем список обязательных каналов
    channels_text = "📢 <b>Управление обязательными каналами</b>\n\n"

    if not required_channels:
        channels_text += "На данный момент нет обязательных каналов для подписки.\n\n"
    else:
        channels_text += "<b>Текущие обязательные каналы:</b>\n"
        for i, channel in enumerate(required_channels, 1):
            channels_text += f"{i}. {channel.get('name', 'Без названия')} - {channel.get('link', 'Без ссылки')}\n"
        channels_text += "\n"

    # Создаем клавиатуру с действиями
    keyboard = [
        [InlineKeyboardButton(text="➕ Добавить канал", callback_data="add_channel")],
    ]

    # Добавляем кнопки редактирования и удаления, если есть каналы
    if required_channels:
        keyboard.append([InlineKeyboardButton(text="✏️ Редактировать канал", callback_data="edit_channel")])
        keyboard.append([InlineKeyboardButton(text="❌ Удалить канал", callback_data="delete_channel")])

    # Добавляем кнопку проверки прав бота
    keyboard.append([InlineKeyboardButton(text="🔍 Проверить права бота", callback_data="check_bot_rights")])

    # Добавляем кнопку возврата
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(channels_text, reply_markup=inline_kb)
    await callback.answer()


@router.callback_query(F.data == "back_to_admin")
async def callback_back_to_admin(callback: types.CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    # Вызываем основную админ-панель
    await cmd_admin(callback.message)
    await callback.answer()


@router.callback_query(F.data == "add_channel")
async def callback_add_channel(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    await callback.message.answer(
        "🔸 <b>Добавление нового канала</b>\n\n"
        "Есть два способа добавить канал:\n\n"
        "1️⃣ <b>Переслать сообщение из канала боту</b>\n"
        "Просто перешлите любое сообщение из нужного канала прямо сюда.\n\n"
        "2️⃣ <b>Указать ID канала вручную</b>\n"
        "Введите ID канала в формате: -100xxxxxxxxxx\n\n"
        "Чтобы получить ID канала:\n"
        "- Добавьте @username_to_id_bot в свой канал\n"
        "- Отправьте любое сообщение в канал\n"
        "- Бот вернет ID канала"
    )
    await state.set_state(AdminStates.waiting_for_channel_id)
    await callback.answer()


@router.message(AdminStates.waiting_for_channel_id)
async def process_channel_id(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return

    # Проверяем, является ли сообщение пересланным из канала
    if message.forward_from_chat and message.forward_from_chat.type == "channel":
        channel_id = str(message.forward_from_chat.id)
        channel_title = message.forward_from_chat.title

        logging.info(f"Получено пересланное сообщение из канала: {channel_title} (ID: {channel_id})")

        # Проверяем права бота в канале
        try:
            bot_member = await bot.get_chat_member(int(channel_id), (await bot.get_me()).id)

            if bot_member.status not in ["administrator", "creator"]:
                await message.answer(
                    "❌ Бот не является администратором указанного канала.\n\n"
                    "Добавьте бота в администраторы канала с правами:\n"
                    "- Просмотр сообщений (обязательно)\n"
                    "- Приглашение пользователей по ссылке (желательно)\n\n"
                    "После этого попробуйте снова."
                )
                return

            # Сохраняем ID канала и имя
            await state.update_data(channel_id=channel_id, chat_title=channel_title)

            # Пытаемся получить ссылку на канал
            try:
                chat = await bot.get_chat(int(channel_id))
                if chat.username:
                    channel_link = f"https://t.me/{chat.username}"
                    await state.update_data(channel_link=channel_link)

                    # Запрашиваем название для отображения
                    await message.answer(
                        f"✅ Канал <b>{channel_title}</b> найден и бот имеет необходимые права.\n\n"
                        f"Предлагаемая ссылка на канал: {channel_link}\n\n"
                        "Если вы хотите использовать другую ссылку, введите её сейчас.\n"
                        "Или нажмите кнопку ниже, чтобы использовать предложенную ссылку.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="✅ Использовать эту ссылку", callback_data="use_suggested_link")]
                        ])
                    )
                    await state.set_state(AdminStates.waiting_for_channel_link)
                    return
                else:
                    # Если у канала нет username, запрашиваем ссылку вручную
                    await message.answer(
                        f"✅ Канал <b>{channel_title}</b> найден и бот имеет необходимые права.\n\n"
                        "Введите ссылку на канал (начинается с https://t.me/):"
                    )
                    await state.set_state(AdminStates.waiting_for_channel_link)
                    return
            except Exception as e:
                logging.error(f"Ошибка при получении информации о канале {channel_id}: {e}")
                await message.answer(
                    f"✅ Канал <b>{channel_title}</b> найден и бот имеет необходимые права.\n\n"
                    "Введите ссылку на канал (начинается с https://t.me/):"
                )
                await state.set_state(AdminStates.waiting_for_channel_link)
                return

        except Exception as e:
            logging.error(f"Ошибка при проверке прав бота в канале {channel_id}: {e}")
            await message.answer(
                "❌ Не удалось проверить права бота в канале. Убедитесь, что бот добавлен в канал как администратор.\n\n"
                "Попробуйте снова или введите ID канала вручную:"
            )
            return

    # Если это не пересланное сообщение, обрабатываем как ввод ID вручную
    channel_id = message.text.strip()

    # Проверяем формат ID канала
    if not (channel_id.startswith("-100") and channel_id[4:].isdigit()):
        await message.answer(
            "❌ Неверный формат ID канала. ID должен начинаться с -100 и содержать только цифры.\n"
            "Попробуйте снова или перешлите сообщение из канала:"
        )
        return

    # Проверяем существование канала и права бота
    try:
        chat = await bot.get_chat(int(channel_id))

        # Проверяем, является ли бот администратором канала
        bot_member = await bot.get_chat_member(int(channel_id), (await bot.get_me()).id)

        if bot_member.status not in ["administrator", "creator"]:
            await message.answer(
                "❌ Бот не является администратором указанного канала.\n\n"
                "Добавьте бота в администраторы канала с правами:\n"
                "- Просмотр сообщений (обязательно)\n"
                "- Приглашение пользователей по ссылке (желательно)\n\n"
                "После этого попробуйте снова."
            )
            return

        # Сохраняем ID канала
        await state.update_data(channel_id=channel_id, chat_title=chat.title)

        # Пытаемся получить ссылку на канал
        if chat.username:
            channel_link = f"https://t.me/{chat.username}"
            await state.update_data(channel_link=channel_link)

            # Запрашиваем название для отображения
            await message.answer(
                f"✅ Канал <b>{chat.title}</b> найден и бот имеет необходимые права.\n\n"
                f"Предлагаемая ссылка на канал: {channel_link}\n\n"
                "Если вы хотите использовать другую ссылку, введите её сейчас.\n"
                "Или нажмите кнопку ниже, чтобы использовать предложенную ссылку.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Использовать эту ссылку", callback_data="use_suggested_link")]
                ])
            )
            await state.set_state(AdminStates.waiting_for_channel_link)
            return
        else:
            # Запрашиваем ссылку на канал
            await message.answer(
                f"✅ Канал <b>{chat.title}</b> найден и бот имеет необходимые права.\n\n"
                "Введите ссылку на канал (начинается с https://t.me/):"
            )
            await state.set_state(AdminStates.waiting_for_channel_link)

    except Exception as e:
        logging.error(f"Ошибка при проверке канала {channel_id}: {e}")
        await message.answer(
            "❌ Не удалось получить информацию о канале. Проверьте ID канала и убедитесь, что бот добавлен в канал как администратор.\n\n"
            "Попробуйте снова:"
        )


@router.callback_query(F.data == "use_suggested_link")
async def callback_use_suggested_link(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    data = await state.get_data()
    channel_link = data.get("channel_link")
    chat_title = data.get("chat_title")

    if not channel_link:
        await callback.message.answer("❌ Произошла ошибка. Ссылка на канал не найдена.")
        await state.clear()
        return

    # Запрашиваем отображаемое имя канала
    await callback.message.answer(
        f"✅ Ссылка на канал принята: {channel_link}\n\n"
        f"Введите название канала для отображения пользователям (по умолчанию будет использовано: {chat_title}):"
    )
    await state.set_state(AdminStates.waiting_for_channel_name)
    await callback.answer()


@router.message(AdminStates.waiting_for_channel_link)
async def process_channel_link(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return

    channel_link = message.text.strip()

    # Проверяем формат ссылки
    if not (channel_link.startswith("https://t.me/") or channel_link.startswith("http://t.me/")):
        await message.answer(
            "❌ Неверный формат ссылки. Ссылка должна начинаться с https://t.me/\n"
            "Попробуйте снова:"
        )
        return

    # Сохраняем ссылку на канал
    await state.update_data(channel_link=channel_link)

    # Запрашиваем отображаемое имя канала
    data = await state.get_data()
    await message.answer(
        f"✅ Ссылка на канал принята.\n\n"
        f"Введите название канала для отображения пользователям (по умолчанию будет использовано: {data.get('chat_title', 'Канал')}):"
    )
    await state.set_state(AdminStates.waiting_for_channel_name)


@router.message(AdminStates.waiting_for_channel_name)
async def process_channel_name(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return

    channel_name = message.text.strip()
    data = await state.get_data()

    # Если пользователь не ввел имя, используем имя канала из Telegram
    if not channel_name:
        channel_name = data.get('chat_title', 'Канал')

    # Добавляем канал в список обязательных
    new_channel = {
        "id": data.get("channel_id"),
        "link": data.get("channel_link"),
        "name": channel_name
    }

    required_channels.append(new_channel)
    save_required_channels()

    await message.answer(
        f"✅ Канал <b>{channel_name}</b> успешно добавлен в список обязательных каналов!"
    )

    # Отправляем обновленное меню управления каналами
    channels_text = "📢 <b>Управление обязательными каналами</b>\n\n"
    channels_text += "<b>Текущие обязательные каналы:</b>\n"

    for i, channel in enumerate(required_channels, 1):
        channels_text += f"{i}. {channel.get('name', 'Без названия')} - {channel.get('link', 'Без ссылки')}\n"

    keyboard = [
        [InlineKeyboardButton(text="➕ Добавить канал", callback_data="add_channel")],
        [InlineKeyboardButton(text="✏️ Редактировать канал", callback_data="edit_channel")],
        [InlineKeyboardButton(text="❌ Удалить канал", callback_data="delete_channel")],
        [InlineKeyboardButton(text="🔍 Проверить права бота", callback_data="check_bot_rights")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")]
    ]

    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await message.answer(channels_text, reply_markup=inline_kb)
    await state.clear()


@router.callback_query(F.data == "edit_channel")
async def callback_edit_channel(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    if not required_channels:
        await callback.answer("Нет каналов для редактирования.", show_alert=True)
        return

    # Создаем клавиатуру с выбором канала для редактирования
    keyboard = []
    for i, channel in enumerate(required_channels, 1):
        keyboard.append([InlineKeyboardButton(
            text=f"{i}. {channel.get('name', 'Без названия')}",
            callback_data=f"edit_channel_{i - 1}"
        )])

    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="manage_channels")])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(
        "✏️ <b>Редактирование канала</b>\n\n"
        "Выберите канал для редактирования:",
        reply_markup=inline_kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_channel_"))
async def callback_select_channel_to_edit(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    # Получаем индекс выбранного канала
    index = int(callback.data.split("_")[-1])

    if index >= len(required_channels):
        await callback.answer("Канал не найден.", show_alert=True)
        return

    channel = required_channels[index]

    # Сохраняем индекс канала в состоянии
    await state.update_data(edit_channel_index=index)

    # Создаем клавиатуру с выбором поля для редактирования
    keyboard = [
        [InlineKeyboardButton(text="ID канала", callback_data="edit_field_id")],
        [InlineKeyboardButton(text="Ссылка на канал", callback_data="edit_field_link")],
        [InlineKeyboardButton(text="Название канала", callback_data="edit_field_name")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="edit_channel")]
    ]

    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(
        f"✏️ <b>Редактирование канала</b>\n\n"
        f"Канал: <b>{channel.get('name', 'Без названия')}</b>\n"
        f"ID: <code>{channel.get('id', 'Не указан')}</code>\n"
        f"Ссылка: {channel.get('link', 'Не указана')}\n\n"
        "Выберите поле для редактирования:",
        reply_markup=inline_kb
    )
    await callback.answer()


@router.callback_query(F.data == "edit_field_id")
async def callback_edit_field_id(callback: types.CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    await callback.message.answer(
        "🔸 <b>Редактирование ID канала</b>\n\n"
        "Введите новый ID канала в формате: -100xxxxxxxxxx\n\n"
        "Чтобы получить ID канала:\n"
        "1. Добавьте @username_to_id_bot в свой канал\n"
        "2. Отправьте любое сообщение в канал\n"
        "3. Бот вернет ID канала"
    )
    await state.set_state(AdminStates.waiting_for_edit_channel_id)
    await callback.answer()


@router.message(AdminStates.waiting_for_edit_channel_id)
async def process_edit_channel_id(message: types.Message, state: FSMContext) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return

    channel_id = message.text.strip()

    # Проверяем формат ID канала
    if not (channel_id.startswith("-100") and channel_id[4:].isdigit()):
        await message.answer(
            "❌ Неверный формат ID канала. ID должен начинаться с -100 и содержать только цифры.\n"
            "Попробуйте снова:"
        )
        return

    # Проверяем существование канала и права бота
    try:
        chat = await bot.get_chat(int(channel_id))

        # Проверяем, является ли бот администратором канала
        bot_member = await bot.get_chat_member(int(channel_id), (await bot.get_me()).id)

        if bot_member.status not in ["administrator", "creator"]:
            await message.answer(
                "❌ Бот не является администратором указанного канала.\n\n"
                "Добавьте бота в администраторы канала с правами:\n"
                "- Просмотр сообщений (обязательно)\n"
                "- Приглашение пользователей по ссылке (желательно)\n\n"
                "После этого попробуйте снова."
            )
            return

        # Получаем индекс редактируемого канала
        data = await state.get_data()
        index = data.get("edit_channel_index")

        if index is not None and index < len(required_channels):
            # Обновляем ID канала
            required_channels[index]["id"] = channel_id
            save_required_channels()

            await message.answer(
                f"✅ ID канала успешно обновлен на: <code>{channel_id}</code> ({chat.title})"
            )

            # Возвращаемся к меню управления каналами
            channels_text = "📢 <b>Управление обязательными каналами</b>\n\n"
            channels_text += "<b>Текущие обязательные каналы:</b>\n"

            for i, channel in enumerate(required_channels, 1):
                channels_text += f"{i}. {channel.get('name', 'Без названия')} - {channel.get('link', 'Без ссылки')}\n"

            keyboard = [
                [InlineKeyboardButton(text="➕ Добавить канал", callback_data="add_channel")],
                [InlineKeyboardButton(text="✏️ Редактировать канал", callback_data="edit_channel")],
                [InlineKeyboardButton(text="❌ Удалить канал", callback_data="delete_channel")],
                [InlineKeyboardButton(text="🔍 Проверить права бота", callback_data="check_bot_rights")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")]
            ]

            inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

            await message.answer(channels_text, reply_markup=inline_kb)
            await state.clear()
        else:
            await message.answer("❌ Произошла ошибка при обновлении канала.")
            await state.clear()

    except Exception as e:
        logging.error(f"Ошибка при проверке канала {channel_id}: {e}")
        await message.answer(
            "❌ Не удалось получить информацию о канале. Проверьте ID канала и убедитесь, что бот добавлен в канал как администратор.\n\n"
            "Попробуйте снова:"
        )


@router.callback_query(F.data == "delete_channel")
async def callback_delete_channel(callback: types.CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    if not required_channels:
        await callback.answer("Нет каналов для удаления.", show_alert=True)
        return

    # Создаем клавиатуру с выбором канала для удаления
    keyboard = []
    for i, channel in enumerate(required_channels, 1):
        keyboard.append([InlineKeyboardButton(
            text=f"{i}. {channel.get('name', 'Без названия')}",
            callback_data=f"delete_channel_{i - 1}"
        )])

    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="manage_channels")])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(
        "❌ <b>Удаление канала</b>\n\n"
        "Выберите канал для удаления:",
        reply_markup=inline_kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_channel_"))
async def callback_confirm_delete_channel(callback: types.CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    # Получаем индекс выбранного канала
    index = int(callback.data.split("_")[-1])

    if index >= len(required_channels):
        await callback.answer("Канал не найден.", show_alert=True)
        return

    channel = required_channels[index]

    # Создаем клавиатуру для подтверждения удаления
    keyboard = [
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{index}")],
        [InlineKeyboardButton(text="❌ Нет, отменить", callback_data="delete_channel")]
    ]

    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(
        f"❓ <b>Подтверждение удаления</b>\n\n"
        f"Вы действительно хотите удалить канал <b>{channel.get('name', 'Без названия')}</b> из списка обязательных?",
        reply_markup=inline_kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete_"))
async def callback_perform_delete_channel(callback: types.CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    # Получаем индекс выбранного канала
    index = int(callback.data.split("_")[-1])

    if index >= len(required_channels):
        await callback.answer("Канал не найден.", show_alert=True)
        return

    # Сохраняем имя удаляемого канала
    channel_name = required_channels[index].get('name', 'Без названия')

    # Удаляем канал из списка
    del required_channels[index]
    save_required_channels()

    await callback.answer(f"Канал {channel_name} успешно удален!", show_alert=True)

    # Возвращаемся к меню управления каналами
    await callback_manage_channels(callback)


@router.callback_query(F.data == "check_bot_rights")
async def callback_check_bot_rights(callback: types.CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа.", show_alert=True)
        return

    if not required_channels:
        await callback.answer("Нет каналов для проверки.", show_alert=True)
        return

    # Обновляем сообщение о начале проверки
    process_message = await callback.message.edit_text(
        "🔍 <b>Проверка прав бота в каналах</b>\n\n"
        "Идет проверка, пожалуйста, подождите..."
    )

    bot_id = (await bot.get_me()).id
    results = []

    for channel in required_channels:
        channel_id = channel.get('id')
        channel_name = channel.get('name', 'Без названия')

        try:
            # Проверяем, существует ли канал и является ли бот администратором
            chat = await bot.get_chat(int(channel_id))
            bot_member = await bot.get_chat_member(int(channel_id), bot_id)

            if bot_member.status == "administrator":
                results.append(f"✅ {channel_name} - бот является администратором")
            elif bot_member.status == "creator":
                results.append(f"✅ {channel_name} - бот является создателем")
            else:
                results.append(f"❌ {channel_name} - бот не является администратором (статус: {bot_member.status})")
        except Exception as e:
            logging.error(f"Ошибка при проверке канала {channel_id}: {e}")
            results.append(f"❌ {channel_name} - ошибка проверки: {str(e)}")

    # Формируем отчет
    report = "🔍 <b>Результаты проверки прав бота</b>\n\n"
    for result in results:
        report += f"{result}\n"

    report += "\n<b>Рекомендации:</b>\n"
    report += "- Бот должен быть администратором во всех каналах\n"
    report += "- Необходимо право на просмотр сообщений\n"
    report += "- Желательно право на приглашение пользователей"

    # Создаем клавиатуру для возврата
    keyboard = [[InlineKeyboardButton(text="🔙 Назад", callback_data="manage_channels")]]
    inline_kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await process_message.edit_text(report, reply_markup=inline_kb)
    await callback.answer()