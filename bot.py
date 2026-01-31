import logging
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import os
import csv

API_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = [5705261098]
CHANNEL_USERNAME = "@CloudMafiaDP_OT3UBU"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# ---------- DATABASE ----------
conn = sqlite3.connect("reviews.db")
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS reviews (
    user_id INTEGER,
    rating INTEGER,
    communication INTEGER,
    delivery INTEGER,
    name TEXT,
    text TEXT,
    date TEXT
)
""")
conn.commit()

# ---------- HELPERS ----------
def stars_kb(prefix):
    kb = InlineKeyboardMarkup(row_width=5)
    for i in range(1, 6):
        kb.insert(InlineKeyboardButton(f"{i} ⭐", callback_data=f"{prefix}_{i}"))
    return kb

def can_leave_review(user_id):
    cur.execute(
        "SELECT date FROM reviews WHERE user_id=? ORDER BY date DESC LIMIT 1",
        (user_id,)
    )
    row = cur.fetchone()
    if not row:
        return True
    last = datetime.fromisoformat(row[0])
    return datetime.now() - last >= timedelta(hours=12)

def update_channel_rating():
    cur.execute("SELECT AVG(rating), COUNT(*) FROM reviews")
    avg, count = cur.fetchone()
    if not avg:
        return
    text = f"⭐ Середня оцінка: {round(avg,2)} / 5 ({count} відгуків)"
    bot.loop.create_task(
        bot.set_chat_description(CHANNEL_USERNAME, text)
    )

# ---------- STATES ----------
class Review(StatesGroup):
    rating = State()
    communication = State()
    delivery = State()
    name = State()
    text = State()

# ---------- HANDLERS ----------
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    if not can_leave_review(message.from_user.id):
        await message.answer("⏳ Ви вже залишали відгук. Спробуйте пізніше (через 12 годин).")
        return
    await Review.rating.set()
    await message.answer("⭐ Оцініть магазин загалом:", reply_markup=stars_kb("rate"))

@dp.callback_query_handler(lambda c: c.data.startswith("rate_"), state=Review.rating)
async def rate(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(rating=int(callback.data.split("_")[1]))
    await Review.communication.set()
    await callback.message.answer("💬 Як ви оцінюєте комунікацію?", reply_markup=stars_kb("comm"))
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("comm_"), state=Review.communication)
async def comm(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(communication=int(callback.data.split("_")[1]))
    await Review.delivery.set()
    await callback.message.answer("🚚 Як ви оцінюєте швидкість доставки?", reply_markup=stars_kb("del"))
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("del_"), state=Review.delivery)
async def delivery(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(delivery=int(callback.data.split("_")[1]))
    await Review.name.set()
    await callback.message.answer("👤 Як вас вказати у відгуку?")
    await callback.answer()

@dp.message_handler(state=Review.name)
async def name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await Review.text.set()
    await message.answer("✍️ Напишіть ваш відгук:")

@dp.message_handler(state=Review.text)
async def text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cur.execute(
        "INSERT INTO reviews VALUES (?,?,?,?,?,?,?)",
        (
            message.from_user.id,
            data['rating'],
            data['communication'],
            data['delivery'],
            data['name'],
            message.text,
            datetime.now().isoformat()
        )
    )
    conn.commit()

    caption = (
        f"⭐ {data['rating']} / 5\n"
        f"💬 {data['communication']} / 5\n"
        f"🚚 {data['delivery']} / 5\n\n"
        f"👤 {data['name']}\n\n"
        f"{message.text}"
    )

    await bot.send_message(ADMIN_IDS[0], caption)
    update_channel_rating()

    await message.answer("✅ Дякуємо! Відгук прийнято.")
    await state.finish()

# ---------- EXPORT ----------
@dp.message_handler(commands=['export'])
async def export(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    cur.execute("SELECT * FROM reviews")
    rows = cur.fetchall()

    with open("reviews.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id", "rating", "communication", "delivery", "name", "text", "date"])
        writer.writerows(rows)

    await message.answer_document(types.InputFile("reviews.csv"))

# ---------- START ----------
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
