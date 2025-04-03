import os
import tempfile
import asyncio
import logging
from aiogram import types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from bot import bot, router
from config import ADMIN_IDS
from data import referral_data, users_data, stars_per_referral, save_stars_config
from utils import get_invite_word, save_referral_data, get_stars_word


class AdminStates(StatesGroup):
    waiting_for_stars_value = State()
    waiting_for_broadcast = State()


@router.message(Command("referrals"))
async def cmd_referrals(message: types.Message) -> None:
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет прав для использования этой команды.")
        return

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


@router.message(Command("admin"))
async def cmd_admin(message: types.Message) -> None:
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к этой команде.")
        return

    total_users = len(users_data)
    active_users = sum(1 for u in users_data.values() if u.get("status") == "active")
    removed_users = sum(1 for u in users_data.values() if u.get("status") == "removed")
    total_stars = sum(u.get("stars", 0) for u in users_data.values())

    admin_text = (
        "📊 <b>Админ панель</b>:\n\n"
        f"Всего пользователей: <b>{total_users}</b>\n"
        f"Активных пользователей: <b>{active_users}</b>\n"
        f"Удалили бота: <b>{removed_users}</b>\n"
        f"Всего звезд в обороте: <b>{total_stars}</b>\n"
        f"Звезд за реферала: <b>{stars_per_referral}</b>\n\n"
        "Выберите действие:"
    )
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скачать всех рефералов", callback_data="download_referrals")],
        [InlineKeyboardButton(text="📋 Скачать всех юзеров", callback_data="download_users")],
        [InlineKeyboardButton(text="⭐ Изменить кол-во звезд за реферала", callback_data="change_stars_value")],
        [InlineKeyboardButton(text="💬 Создать рассылку", callback_data="create_broadcast")]
    ])
    await message.answer(admin_text, reply_markup=inline_kb)


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

    await callback.message.answer(
        f"Текущее количество звезд за одного реферала: <b>{stars_per_referral}</b>\n\n"
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

        # Обновляем значение
        global stars_per_referral
        stars_per_referral = new_value
        save_stars_config()

        await message.answer(f"✅ Количество звезд за реферала изменено на: <b>{new_value}</b>")
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
        await message.answer(f"💬 Сообщение получено:\n\n{message.text}\n\nПодтвердите отправку:", reply_markup=inline_kb)
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

