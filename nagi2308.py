import os
import datetime
from pymongo import MongoClient
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

# ====== LOAD ENV ======
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

SUDO_ID = int(os.getenv("OWNER_ID"))
LOGIN_CREDENTIALS = {
    "username": os.getenv("LOGIN_USERNAME"),
    "password": os.getenv("LOGIN_PASSWORD"),
}

# ====== DATABASE ======
mongo = MongoClient(MONGO_URI)
db = mongo["support_bot"]
users_col = db["users"]
messages_col = db["messages"]
sessions = {}  # temporary login sessions {user_id: {"logged_in": True, "login_time": datetime}}

# ====== BOT ======
app = Client("support-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


# --- START ---
@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    users_col.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "username": username}},
        upsert=True,
    )

    buttons = [
        [InlineKeyboardButton("💬 Support", url="https://t.me/KnightsXBotsupport")],
        [InlineKeyboardButton("📢 Updates", url="https://t.me/KnightsXbots")],
    ]
    await message.reply_text(
        "🚀 ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ **Nagi Support Bot**\n\n"
        "🤖 This bot helps you contact **Nagi** if he is not available on Telegram.\n"
        "📩 Use /send <message> to reach out.\n",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# --- SEND MESSAGE ---
@app.on_message(filters.command("send") & filters.private)
async def send_message(client, message):
    user = message.from_user
    if len(message.command) < 2:
        return await message.reply_text("⚠️ Usage: `/send your message`", quote=True)

    text = message.text.split(" ", 1)[1]
    msg_data = {
        "user_id": user.id,
        "username": user.username,
        "sudo_id": user.id,
        "message": text,
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    messages_col.insert_one(msg_data)

    await message.reply_text("✅ Your message has been sent to Nagi!")

    # notify sudo
    await client.send_message(
        SUDO_ID,
        f"📩 **New Message Received**\n\n👤 From: @{user.username or 'NoUsername'} (`{user.id}`)\n🕒 {msg_data['date']}\n💬 {text}",
    )


# --- LOGIN ---
@app.on_message(filters.command("login") & filters.private)
async def login(client, message):
    user_id = message.from_user.id

    if user_id != SUDO_ID:
        return await message.reply_text("❌ You are not allowed to login.")

    await message.reply_text("👤 Enter your username:")
    sessions[user_id] = {"step": "username"}


@app.on_message(filters.private)
async def handle_login(client, message):
    user_id = message.from_user.id

    if user_id in sessions:
        step = sessions[user_id].get("step")

        if step == "username":
            if message.text == LOGIN_CREDENTIALS["username"]:
                sessions[user_id]["username"] = message.text
                sessions[user_id]["step"] = "password"
                return await message.reply_text("🔑 Enter your password:")
            else:
                return await message.reply_text("❌ Invalid username. Try again.")

        elif step == "password":
            if message.text == LOGIN_CREDENTIALS["password"]:
                sessions[user_id] = {"logged_in": True, "login_time": datetime.datetime.now()}
                return await message.reply_text(
                    "✅ Successfully logged in!\n\nAvailable commands:\n"
                    "• /messages - View all messages\n"
                    "• /reply <username|id> <message> - Reply to user\n"
                    "• /broadcast <message> - Send broadcast\n"
                    "• /logout - Logout"
                )
            else:
                return await message.reply_text("❌ Wrong password.")


# --- AUTO LOGOUT CHECK ---
def is_logged_in(user_id):
    session = sessions.get(user_id)
    if not session or not session.get("logged_in"):
        return False
    login_time = session.get("login_time")
    if login_time and (datetime.datetime.now() - login_time).total_seconds() > 86400:  # 24 hours
        del sessions[user_id]
        return False
    return True


# --- LOGOUT ---
@app.on_message(filters.command("logout") & filters.private)
async def logout(client, message):
    user_id = message.from_user.id
    if user_id != SUDO_ID or not is_logged_in(user_id):
        return await message.reply_text("❌ You are not logged in.")

    if user_id in sessions:
        del sessions[user_id]
    await message.reply_text("✅ You have been logged out.")


# --- MESSAGES ---
@app.on_message(filters.command("messages") & filters.private)
async def get_messages(client, message):
    user_id = message.from_user.id
    if user_id != SUDO_ID or not is_logged_in(user_id):
        return await message.reply_text("❌ You must login first.")

    msgs = messages_col.find().sort("_id", -1)
    text = "📜 **User Messages:**\n\n"
    for m in msgs:
        text += f"👤 @{m.get('username')} (`{m['user_id']}`)\n🕒 {m['date']}\n💬 {m['message']}\n\n"
    await message.reply_text(text or "No messages yet.")


# --- REPLY ---
@app.on_message(filters.command("reply") & filters.private)
async def reply_user(client, message):
    user_id = message.from_user.id
    if user_id != SUDO_ID or not is_logged_in(user_id):
        return await message.reply_text("❌ You must login first.")

    try:
        target, reply_msg = message.text.split(" ", 2)[1:]
    except:
        return await message.reply_text("⚠️ Usage: /reply <username|id> <message>")

    if target.isdigit():
        target_id = int(target)
    else:
        user_doc = users_col.find_one({"username": target})
        if not user_doc:
            return await message.reply_text("❌ User not found.")
        target_id = user_doc["user_id"]

    await client.send_message(target_id, f"💬 Reply from Nagi:\n\n{reply_msg}")
    await message.reply_text("✅ Replied successfully!")


# --- BROADCAST ---
@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast(client, message):
    user_id = message.from_user.id
    if user_id != SUDO_ID or not is_logged_in(user_id):
        return await message.reply_text("❌ You must login first.")

    if len(message.command) < 2:
        return await message.reply_text("⚠️ Usage: /broadcast <message>")

    text = message.text.split(" ", 1)[1]
    users = users_col.find()
    sent = 0
    for u in users:
        try:
            await client.send_message(u["user_id"], f"📢 Broadcast:\n\n{text}")
            sent += 1
        except:
            pass

    await message.reply_text(f"✅ Broadcast sent to {sent} users.")


# ====== RUN ======
print("Bot is running...")
app.run()
