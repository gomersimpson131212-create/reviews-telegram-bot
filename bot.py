import logging
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import os, csv

API_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = [5705261098]
CHANNEL = "@CloudMafiaDP_OT3UBU"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# ---------- DATABASE ----------
conn = sqlite3.connect("reviews.db")
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    rating INTEGER,
    communication INTEGER,
    delivery INTEGER,
    name TEXT,
    text TEXT,
    photo TEXT,
    date TEXT,
    published INTEGER DEFAULT 0
)
""")
conn.commit()

# ---------- HELPERS ----------
def stars_kb(prefix):
    kb = InlineKeyboardMarkup(row_width=5)
    for i in range(1, 6):
        kb.insert(InlineKeyboardButton(f"{i} ⭐", callback_data=f"{prefix}_{i}"))
    return kb

def can_review(uid):
    cur.execute("SELECT date FROM reviews WHERE user_id=? ORDER BY date DESC LIMIT 1", (uid,))
    r = cur.fetchone()
    if not r:
        return True
    return datetime.now() - datetime.fromisoformat(r[0]) >= timedelta(hours=12)

async def update_rating():
    cur.execute("SELECT AVG(rating), COUNT(*) FROM reviews WHERE published=1")
    avg, cnt = cur.fetchone()
    if avg:
        text = f"⭐ Середня оцінка: {round(avg,2)} / 5 ({cnt} відгуків)"
        await bot.set_chat_description(CHANNEL, text)

# ---------- STATES ----------
class Review(StatesGroup):
    rating = State()
    communication = State()
    delivery = State()
    name = State()
    text = State()
    photo = State()

# ---------- START ----------
@dp.message_handler(commands="start")
async def start(msg: types.Message):
    if not can_review(msg.from_user.id):
        await msg.answer("⏳ Ви вже залишали відгук. Спробуйте через 12 годин.")
        return
    await Review.rating.set()
    await msg.answer("⭐ Оцініть магазин загалом:", reply_markup=stars_kb("rate"))

@dp.callback_query_handler(lambda c: c.data.startswith("rate_"), state=Review.rating)
async def rate(c: types.CallbackQuery, state: FSMContext):
    await state.update_data(rating=int(c.data.split("_")[1]))
    await Review.communication.set()
    await c.message.answer("💬 Як ви оцінюєте комунікацію?", reply_markup=stars_kb("comm"))
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("comm_"), state=Review.communication)
async def comm(c: types.CallbackQuery, state: FSMContext):
    await state.update_data(communication=int(c.data.split("_")[1]))
    await Review.delivery.set()
    await c.message.answer("🚚 Як ви оцінюєте швидкість доставки?", reply_markup=stars_kb("del"))
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("del_"), state=Review.delivery)
async def deliv(c: types.CallbackQuery, state: FSMContext):
    await state.update_data(delivery=int(c.data.split("_")[1]))
    await Review.name.set()
    await c.message.answer("👤 Як вас вказати у відгуку?")
    await c.answer()

@dp.message_handler(state=Review.name)
async def name(msg: types.Message, state: FSMContext):
    await state.update_data(name=msg.text)
    await Review.text.set()
    await msg.answer("✍️ Напишіть ваш відгук:")

@dp.message_handler(state=Review.text)
async def text(msg: types.Message, state: FSMContext):
    await state.update_data(text=msg.text)
    await Review.photo.set()
    await msg.answer("📸 Додайте фото або напишіть «без фото»")

@dp.message_handler(state=Review.photo, content_types=types.ContentTypes.ANY)
async def photo(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = msg.photo[-1].file_id if msg.photo else None

    cur.execute(
        """INSERT INTO reviews 
        (user_id,rating,communication,delivery,name,text,photo,date)
        VALUES (?,?,?,?,?,?,?,?)""",
        (
            msg.from_user.id,
            data['rating'],
            data['communication'],
            data['delivery'],
            data['name'],
            data['text'],
            photo_id,
            datetime.now().isoformat()
        )
    )
    conn.commit()
    review_id = cur.lastrowid

    caption = (
        f"⭐ {data['rating']} / 5\n"
        f"💬 {data['communication']} / 5\n"
        f"🚚 {data['delivery']} / 5\n\n"
        f"👤 {data['name']}\n\n"
        f"{data['text']}"
    )

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Опублікувати", callback_data=f"pub_{review_id}"),
        InlineKeyboardButton("❌ Відхилити", callback_data=f"rej_{review_id}")
    )

    if photo_id:
        await bot.send_photo(ADMIN_IDS[0], photo_id, caption=caption, reply_markup=kb)
    else:
        await bot.send_message(ADMIN_IDS[0], caption, reply_markup=kb)

    await msg.answer("✅ Дякуємо! Відгук відправлено на перевірку.")
    await state.finish()

# ---------- MODERATION ----------
@dp.callback_query_handler(lambda c: c.data.startswith(("pub_", "rej_")))
async def moderate(c: types.CallbackQuery):
    if c.from_user.id not in ADMIN_IDS:
        return

    action, rid = c.data.split("_")
    rid = int(rid)

    cur.execute("SELECT * FROM reviews WHERE id=?", (rid,))
    r = cur.fetchone()
    if not r:
        return

    _, _, rate, comm, deliv, name, text, photo, _, _ = r

    if action == "pub":
        cur.execute("UPDATE reviews SET published=1 WHERE id=?", (rid,))
        conn.commit()

        post = (
            f"⭐ {rate} / 5\n"
            f"💬 {comm} / 5\n"
            f"🚚 {deliv} / 5\n\n"
            f"👤 {name}\n\n"
            f"{text}"
        )

        if photo:
            await bot.send_photo(CHANNEL, photo, caption=post)
        else:
            await bot.send_message(CHANNEL, post)

        await update_rating()
        await c.answer("Опубліковано ✅")

    else:
        await c.answer("Відхилено ❌")

    await c.message.edit_reply_markup()

# ---------- EXPORT ----------
@dp.message_handler(commands="export")
async def export(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS:
        return

    cur.execute("SELECT * FROM reviews")
    rows = cur.fetchall()

    with open("reviews.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id","user_id","rating","communication","delivery",
            "name","text","photo","date","published"
        ])
        writer.writerows(rows)

    await msg.answer_document(types.InputFile("reviews.csv"))

# ---------- RUN ----------
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
