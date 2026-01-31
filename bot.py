import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import os

API_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_ID = 5705261098
CHANNEL_USERNAME = "@CloudMafiaDP_OT3UBU"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

class Review(StatesGroup):
    rating = State()
    text = State()
    photo = State()

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    kb = InlineKeyboardMarkup(row_width=5)
    for i in range(1, 6):
        kb.insert(InlineKeyboardButton(f"{i} ⭐", callback_data=f"rate_{i}"))
    await message.answer(
        "👋 Спасибо за покупку!\n\nПожалуйста, выберите оценку:",
        reply_markup=kb
    )

@dp.callback_query_handler(lambda c: c.data.startswith("rate_"))
async def set_rating(callback: types.CallbackQuery, state: FSMContext):
    rating = int(callback.data.split("_")[1])
    await state.update_data(rating=rating)
    await Review.text.set()
    await callback.message.answer("✍️ Напишите текст отзыва:")
    await callback.answer()

@dp.message_handler(state=Review.text, content_types=types.ContentTypes.TEXT)
async def set_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    await Review.photo.set()
    await message.answer("📸 Можете отправить фото или напишите «без фото»")

@dp.message_handler(state=Review.photo, content_types=types.ContentTypes.ANY)
async def set_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    rating = data["rating"]
    text = data["text"]

    stars = "⭐" * rating
    caption = f"{stars}\n\n{text}"

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Опубликовать", callback_data="approve"),
        InlineKeyboardButton("❌ Отклонить", callback_data="reject")
    )

    if message.photo:
        await bot.send_photo(
            ADMIN_ID,
            message.photo[-1].file_id,
            caption=caption,
            reply_markup=kb
        )
    else:
        await bot.send_message(
            ADMIN_ID,
            caption,
            reply_markup=kb
        )

    await message.answer("✅ Спасибо! Ваш отзыв отправлен на проверку.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data in ["approve", "reject"])
async def moderation(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    if callback.data == "approve":
        if callback.message.photo:
            await bot.send_photo(
                CHANNEL_USERNAME,
                callback.message.photo[-1].file_id,
                caption=callback.message.caption
            )
        else:
            await bot.send_message(
                CHANNEL_USERNAME,
                callback.message.text
            )
        await callback.message.edit_reply_markup()
        await callback.answer("Опубликовано ✅")

    else:
        await callback.message.edit_reply_markup()
        await callback.answer("Отклонено ❌")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)