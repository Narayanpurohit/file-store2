from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import random, string, time
from config import API_ID, API_HASH, BOT_TOKEN, CHANNEL_1_ID, CHANNEL_2_ID
from db import users_col, files_col, verifications_col

app = Client("FileShareBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def generate_short_slug():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(3, 5)))

def generate_verification_slug():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(15, 18)))

async def check_channel_2_subscription(client, user_id):
    try:
        member = await client.get_chat_member(CHANNEL_2_ID, user_id)
        if member.status in ("member", "administrator", "creator"):
            return True
    except:
        pass
    return False

@app.on_message(filters.private & filters.command("start"))
async def start_handler(client, message):
    user_id = message.from_user.id
    slug = message.text.split(" ", 1)[1] if len(message.command) > 1 else None

    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({"user_id": user_id})

    if slug:
        # Generate invite links
        ch1_link = (await client.create_chat_invite_link(CHANNEL_1_ID, creates_join_request=True)).invite_link
        ch2_link = (await client.create_chat_invite_link(CHANNEL_2_ID, creates_join_request=False)).invite_link

        is_member = await check_channel_2_subscription(client, user_id)
        if not is_member:
            try_again_url = f"https://t.me/{(await client.get_me()).username}?start={slug}"
            buttons = [
                [InlineKeyboardButton("Request to Join Channel 1", url=ch1_link)],
                [InlineKeyboardButton("Join Channel 2", url=ch2_link)],
                [InlineKeyboardButton("✅ Try Again", url=try_again_url)]
            ]
            await message.reply_text(
                "You must join the required channels to access this file.",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

        if len(slug) >= 15:
            data = verifications_col.find_one({"slug": slug})
            if data:
                verifications_col.update_one(
                    {"slug": slug},
                    {"$set": {"user_id": user_id, "verified_at": int(time.time())}}
                )
                await message.reply_text("You are now verified for 4 hours. Please use the file link again.")
            else:
                await message.reply_text("Invalid or expired verification link.")
        else:
            verified = verifications_col.find_one({"user_id": user_id})
            if verified and time.time() - verified["verified_at"] <= 4 * 3600:
                file_data = files_col.find_one({"slug": slug})
                if file_data:
                    await client.send_cached_media(message.chat.id, file_data["file_id"])
                else:
                    await message.reply_text("File not found.")
            else:
                verify_slug = generate_verification_slug()
                verifications_col.insert_one({
                    "user_id": user_id,
                    "slug": verify_slug,
                    "verified_at": 0
                })
                verify_link = f"https://t.me/{(await client.get_me()).username}?start={verify_slug}"
                await message.reply_text(
                    "You are not verified. Click the button below to verify (valid for 4 hours):",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("✅ Verify Me", url=verify_link)]]
                    )
                )
    else:
        await message.reply_text("Send me a file and I’ll give you a shareable link!")

@app.on_message(filters.private & filters.document)
async def handle_file(client, message):
    slug = generate_short_slug()
    file_id = message.document.file_id
    files_col.insert_one({"slug": slug, "file_id": file_id})
    link = f"https://t.me/{(await client.get_me()).username}?start={slug}"
    await message.reply_text(f"Here is your link:\n`{link}`", quote=True)

app.run()