import os
import random
import string
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from config import API_ID, API_HASH, BOT_TOKEN, MONGO_URL, CHANNEL_1_ID, CHANNEL_2_ID, STORAGE_DIR
from pymongo import MongoClient

bot = Client("file_share_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
client = MongoClient(MONGO_URL)
db = client["file_share_bot"]
files_col = db["files"]
verify_col = db["verify"]
verified_users = {}

# Force subscription check (only channel 2)
async def check_force_sub(bot, message):
    user_id = message.from_user.id

    try:
        await bot.get_chat_member(CHANNEL_2_ID, user_id)
        return True
    except UserNotParticipant:
        channel_1_invite = await bot.create_chat_invite_link(CHANNEL_1_ID, creates_join_request=True)
        channel_2_invite = await bot.create_chat_invite_link(CHANNEL_2_ID)

        bot_username = (await bot.get_me()).username
        start_param = message.command[1] if len(message.command) > 1 else ""
        start_link = f"https://t.me/{bot_username}?start={start_param}"

        buttons = [
            [InlineKeyboardButton("Join Channel 1", url=channel_1_invite.invite_link)],
            [InlineKeyboardButton("Join Channel 2", url=channel_2_invite.invite_link)],
            [InlineKeyboardButton("✅ Try Again", url=start_link)]
        ]

        await message.reply_photo(
            photo="https://telegra.ph/file/5f5e22bd75730316fba60.jpg",
            caption="**To use this bot, please join both channels first.**",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return False

# Slug generator
def generate_slug(length=5):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# /start handler
@bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    if not await check_force_sub(client, message):
        return

    args = message.text.split(maxsplit=1)
    if len(args) == 2:
        slug = args[1]

        if len(slug) > 5:
            data = verify_col.find_one({"slug": slug})
            if data:
                verified_users[message.from_user.id] = asyncio.get_event_loop().time()
                await message.reply("You have been verified for 4 hours.")
            else:
                await message.reply("Invalid or expired verification link.")
        else:
            now = asyncio.get_event_loop().time()
            last_verified = verified_users.get(message.from_user.id, 0)
            if now - last_verified > 14400:  # 4 hours
                verif_slug = generate_slug(16)
                verify_col.insert_one({"slug": verif_slug, "user_id": message.from_user.id})
                bot_username = (await client.get_me()).username
                verify_link = f"https://t.me/{bot_username}?start={verif_slug}"
                await message.reply(f"You need to verify first. Click [here]({verify_link}) to verify.", disable_web_page_preview=True)
            else:
                file = files_col.find_one({"slug": slug})
                if file:
                    await message.reply_document(document=file["file_path"])
                else:
                    await message.reply("File not found.")
    else:
        await message.reply("Send me a file to generate a shareable link.")

# Save file and generate link
@bot.on_message(filters.document & filters.private)
async def save_file(client: Client, message: Message):
    media = message.document
    filename = media.file_name
    base, ext = os.path.splitext(filename)
    safe_filename = filename
    counter = 1

    while os.path.exists(os.path.join(STORAGE_DIR, safe_filename)):
        safe_filename = f"{base}_{counter}{ext}"
        counter += 1

    file_path = os.path.join(STORAGE_DIR, safe_filename)
    await message.download(file_path)

    slug = generate_slug()
    while files_col.find_one({"slug": slug}):
        slug = generate_slug()

    files_col.insert_one({
        "slug": slug,
        "file_path": file_path,
        "user_id": message.from_user.id
    })

    bot_username = (await client.get_me()).username
    share_link = f"https://t.me/{bot_username}?start={slug}"
    await message.reply(f"Here is your shareable link:\n`{share_link}`", quote=True)

bot.run()