import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackQueryHandler
)
from dotenv import load_dotenv
import os

# Загрузка переменных окружения
load_dotenv()

# === Настройки ===
TOKEN = os.getenv("TOKEN")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID"))

# === Логгирование ===
logging.basicConfig(level=logging.INFO)
user_sessions = {}  # user_id: {name, phone, verified}
admin_reply_targets = {}
location_requests = {}  # user_id: admin_id

# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id == SUPER_ADMIN_ID:
        await update.message.reply_text("👑 Вы супер админ. Ждите сообщений от пользователей.")
    else:
        if user_id not in user_sessions or not user_sessions[user_id].get("verified"):
            button = KeyboardButton("✅ Подтвердить, что я не бот", request_contact=True)
            markup = ReplyKeyboardMarkup([[button]], resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text(
                "👋 Привет! Подтвердите, что вы не бот, отправив свой номер телефона.",
                reply_markup=markup
            )
        else:
            await update.message.reply_text("📨 Отправьте сообщение, и я передам его администратору.")

# === Получение номера пользователя ===
async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user_id = update.message.from_user.id
    user_name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or "Без имени"
    phone = contact.phone_number

    user_sessions[user_id] = {
        "name": user_name,
        "phone": phone,
        "verified": True
    }

    await update.message.reply_text(
        "✅ Спасибо! Теперь вы можете отправить сообщение администратору.",
        reply_markup=ReplyKeyboardRemove()
    )

# === Прием сообщений от обычных пользователей ===
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = user.id

    if user_id not in user_sessions or not user_sessions[user_id].get("verified"):
        await update.message.reply_text("❗Сначала подтвердите, что вы не бот, командой /start.")
        return

    msg = update.message.text
    user_info = user_sessions[user_id]
    user_name = user_info["name"]
    phone = user_info["phone"]

    user_tag = f'{user_name} | 📱 {phone}'

    user_sessions[user_id]["last_message"] = msg

    keyboard = [
        [InlineKeyboardButton(f"✉️ Ответить {user_name}", callback_data=f"reply_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=SUPER_ADMIN_ID,
        text=(
            f"📩 Новое сообщение:\n"
            f"👤 Имя: {user_name}\n"
            f"🆔 ID: {user_id}\n"
            f"📱 Телефон: {phone}\n\n"
            f"💬 {msg}"
        ),
        reply_markup=reply_markup
    )

    await update.message.reply_text("✅ Ваше сообщение отправлено администратору.")

# === Обработка кнопки "Ответить" от админа ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("reply_"):
        target_user_id = int(query.data.split("_")[1])
        admin_reply_targets[SUPER_ADMIN_ID] = target_user_id

        user_info = user_sessions.get(target_user_id, {})
        user_name = user_info.get("nametel", f"User#{target_user_id}")

        await query.message.reply_text(
            f"✏️ Напишите сообщение для {user_name}, и я отправлю его."
        )

# === Обработка ответа от админа ===
async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != SUPER_ADMIN_ID:
        return

    target_user_id = admin_reply_targets.get(SUPER_ADMIN_ID)
    if not target_user_id:
        await update.message.reply_text("❗Вы не выбрали, кому отвечать. Нажмите кнопку 'Ответить'.")
        return

    msg = update.message.text
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"👑 Сообщение от администратора:\n\n{msg}"
        )
        await update.message.reply_text("✅ Сообщение отправлено.")
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось отправить сообщение: {e}")

# === Команда /get <user_id> — Запрос локации ===
async def request_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != SUPER_ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("❗Используй: /get <user_id>")
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❗Неверный ID пользователя.")
        return

    if target_user_id not in user_sessions:
        await update.message.reply_text("❌ Пользователь не найден или не зарегистрирован.")
        return

    location_requests[target_user_id] = SUPER_ADMIN_ID

    button = KeyboardButton("📍 Отправить местоположение", request_location=True)
    markup = ReplyKeyboardMarkup([[button]], resize_keyboard=True, one_time_keyboard=True)

    await context.bot.send_message(
        chat_id=target_user_id,
        text="📍 Администратор запрашивает вашу локацию. Нажмите кнопку ниже, чтобы отправить.",
        reply_markup=markup
    )

    await update.message.reply_text("📨 Запрос локации отправлен.")

# === Обработка локации пользователя ===
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id not in location_requests:
        await update.message.reply_text("ℹ️ Локация получена, но не была запрошена.")
        return

    admin_id = location_requests.pop(user_id)
    location = update.message.location

    await context.bot.send_message(
        chat_id=admin_id,
        text=f"📍 Локация от {user_sessions[user_id]['name']}:\n"
             f"🌐 Широта: {location.latitude}\n🌐 Долгота: {location.longitude}"
    )

    await context.bot.send_location(
        chat_id=admin_id,
        latitude=location.latitude,
        longitude=location.longitude
    )

    await update.message.reply_text("✅ Спасибо! Локация отправлена администратору.", reply_markup=ReplyKeyboardRemove())

# === Основной запуск ===
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("get", request_location))
    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    app.add_handler(MessageHandler(filters.LOCATION, location_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.Chat(SUPER_ADMIN_ID),
        handle_user_message,
        block=False
    ))
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Chat(SUPER_ADMIN_ID),
        handle_admin_reply,
        block=False
    ))

    app.run_polling()

if __name__ == '__main__':
    main()
