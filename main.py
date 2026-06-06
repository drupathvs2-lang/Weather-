import logging
import os
import requests
import json
from flask import Flask
from threading import Thread
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ["BOT_TOKEN"]
WEATHER_API_KEY = os.environ["WEATHER_API_KEY"]
ADMIN_ID = 8661663559
DEVELOPER_LINK = "https://t.me/telgram_boy"

# ---------------- LOGGING ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------- KEEP ALIVE ----------------
app_web = Flask('')

@app_web.route('/')
def home():
    return "Bot is running!"

def run():
    app_web.run(host='0.0.0.0', port=5000)

def keep_alive():
    Thread(target=run, daemon=True).start()

# ---------------- DATABASE ----------------
users = {}
start_message = "Hi, I'm {name}. I can help you by weather alerting maintained by developer"
start_photo = None

def load_users():
    global users
    try:
        with open("users.json", "r") as f:
            users = json.load(f)
    except Exception:
        users = {}

def save_users():
    with open("users.json", "w") as f:
        json.dump(users, f)

# ---------------- WEATHER ----------------
def get_weather(lat, lon):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
        res = requests.get(url, timeout=10).json()

        if res.get("cod") != 200:
            msg = res.get("message", "Unknown error")
            logger.error(f"Weather API error: {res.get('cod')} - {msg}")
            if res.get("cod") == 401:
                return "❌ Weather API key is invalid or not yet activated. New keys can take up to 2 hours to activate."
            return f"❌ Weather error: {msg}"

        temp = res["main"]["temp"]
        desc = res["weather"][0]["description"]
        city = res["name"]

        return f"📍 {city}\n🌡 Temperature: {temp}°C\n☁️ Condition: {desc}"
    except Exception as e:
        logger.error(f"Weather fetch failed: {e}")
        return "❌ Failed to fetch weather. Please try again later."

# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if user_id not in users:
        users[user_id] = {"alert": False}
        save_users()

    keyboard = [
        [InlineKeyboardButton("🌦 Weather", callback_data="weather")],
        [InlineKeyboardButton("🔔 Alert", callback_data="alert")],
        [InlineKeyboardButton("👨‍💻 Developer", url=DEVELOPER_LINK)]
    ]

    if int(user_id) == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    bot_name = context.bot.first_name or "WeatherBot"
    personalized_message = start_message.replace("{name}", bot_name)

    if start_photo:
        await update.message.reply_photo(start_photo, caption=personalized_message, reply_markup=reply_markup)
    else:
        await update.message.reply_text(personalized_message, reply_markup=reply_markup)

# ---------------- BUTTON ----------------
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)

    if query.data == "weather":
        await query.message.reply_text(
            "📍 Send your location",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("Send Location 📍", request_location=True)]],
                resize_keyboard=True
            )
        )

    elif query.data == "alert":
        context.user_data["set_alert"] = True
        await query.message.reply_text("📍 Send location to enable daily alerts")

    elif query.data == "admin" and int(user_id) == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")],
            [InlineKeyboardButton("📊 Stats", callback_data="stats")],
            [InlineKeyboardButton("✏️ Change Msg", callback_data="change_msg")],
            [InlineKeyboardButton("🖼 Change Photo", callback_data="change_photo")]
        ]
        await query.message.reply_text("⚙️ Admin Panel", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "stats":
        await query.message.reply_text(f"👥 Total Users: {len(users)}")

    elif query.data == "broadcast":
        context.user_data["broadcast"] = True
        await query.message.reply_text("Send message to broadcast")

    elif query.data == "change_msg":
        context.user_data["change_msg"] = True
        await query.message.reply_text("Send new start message")

    elif query.data == "change_photo":
        context.user_data["change_photo"] = True
        await query.message.reply_text("Send new photo")

# ---------------- LOCATION ----------------
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    lat = update.message.location.latitude
    lon = update.message.location.longitude

    if user_id not in users:
        users[user_id] = {"alert": False}

    users[user_id]["lat"] = lat
    users[user_id]["lon"] = lon

    weather = get_weather(lat, lon)

    if context.user_data.get("set_alert"):
        users[user_id]["alert"] = True
        await update.message.reply_text("✅ Daily alert set for 7 AM")
        context.user_data["set_alert"] = False

    save_users()
    await update.message.reply_text(weather)

# ---------------- TEXT ----------------
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text

    global start_message

    if context.user_data.get("broadcast") and int(user_id) == ADMIN_ID:
        for uid in users:
            try:
                await context.bot.send_message(uid, text)
            except Exception:
                pass
        context.user_data["broadcast"] = False
        await update.message.reply_text("✅ Broadcast sent")

    elif context.user_data.get("change_msg") and int(user_id) == ADMIN_ID:
        start_message = text
        context.user_data["change_msg"] = False
        await update.message.reply_text("✅ Start message updated")

# ---------------- PHOTO ----------------
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global start_photo
    user_id = str(update.effective_user.id)

    if context.user_data.get("change_photo") and int(user_id) == ADMIN_ID:
        start_photo = update.message.photo[-1].file_id
        context.user_data["change_photo"] = False
        await update.message.reply_text("✅ Photo updated")

# ---------------- DAILY ALERT ----------------
async def send_daily_alert(app):
    for uid, data in users.items():
        if data.get("alert") and "lat" in data:
            weather = get_weather(data["lat"], data["lon"])
            try:
                await app.bot.send_message(uid, f"🌅 Good Morning!\n\n{weather}")
            except Exception:
                pass

# ---------------- MAIN ----------------
async def post_init(app):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_daily_alert, "cron", hour=1, minute=30, args=[app])  # 7 AM IST
    scheduler.start()
    logger.info("Scheduler started")

def main():
    load_users()
    keep_alive()

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.LOCATION, location_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    print("✅ Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
