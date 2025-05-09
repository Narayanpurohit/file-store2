import asyncio
import secrets
import requests
from datetime import datetime, timedelta

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import API_ID, API_HASH, BOT_TOKEN, URL_SHORTENER_API, SHORTENER_DOMAIN, ADMINS
from db import files_col, users_col, verifications_col

app = Client("file-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Generate slug with fs_ prefix
def generate_slug(length=6):
    core = secrets.token_urlsafe(length)[:length]
    return f"fs_{core}"

# Unique verification slug
def generate_verification_slug():
    slug = secrets.token_urlsafe(12)
    while verifications_col.find_one({"slug": slug}):
        slug = secrets.token_urlsafe(12)
    return slug

# Shortener function
def get_short_link(link):
    try:
        api_url = f"https://{SHORTENER_DOMAIN}/api?api={URL_SHORTENER_API}&url={link}"
        response = requests.get(api_url)
        data = response.json()
        if data.get("status") == "success" and "shortenedUrl" in data:
            return data["shortenedUrl"]
    except Exception as e:
        print(f"Shortening failed: {e}")
    return link  # fallback

@app.on_message(filters.document | filters.video | filters.audio)
async def handle_file(client, message: Message):
    if message.from_user.id not in ADMINS:
        return await message.reply_text("Only admins can upload and generate file links.")

    file_id = (
        message.document.file_id if message.document else
        message.video.file_id if message.video else
        message.audio.file_id
    )

    slug = generate_slug()
    while files_col.find_one({"slug": slug}):
        slug = generate_slug()

    files_col.insert_one({
        "slug": slug,
        "file_id": file_id,
        "file_type": (
            "document" if message.document else
            "video" if message.video else
            "audio"
        ),
        "uploaded_by": message.from_user.id,
        "created_at": datetime.utcnow()
    })

    link = f"https://t.me/{(await app.get_me()).username}?start={slug}"
    await message.reply_text(f"Here's your download link:\n{link}")

@app.on_message(filters.command("start"))
async def handle_start(client, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) == 1:
        return await message.reply("Welcome to the File Bot!")

    slug = args[1].strip()
    user_id = message.from_user.id

    if slug.startswith("fs_"):
        user = users_col.find_one({"user_id": user_id})
        if not user or user.get("expires_at", datetime.min) < datetime.utcnow():
            verification_slug = generate_verification_slug()
            verifications_col.insert_one({
                "slug": verification_slug,
                "user_id": user_id,
                "created_at": datetime.utcnow()
            })

            verify_link = f"https://t.me/{(await app.get_me()).username}?start={verification_slug}"
            short_link = get_short_link(verify_link)

            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Verify", url=short_link)],
                [InlineKeyboardButton("How to verify?", url="https://t.me/DriveOO1bot?start=fs_taDm6O")]
            ])
            return await message.reply(
                "You are not verified. Please verify yourself to continue.",
                reply_markup=buttons
            )

        file_data = files_col.find_one({"slug": slug})
        if not file_data:
            return await message.reply("Invalid file link.")

        file_type = file_data.get("file_type", "document")
        file_id = file_data["file_id"]
        caption = "This message will be deleted in 30 minutes."

        if file_type == "document":
            sent = await client.send_document(message.chat.id, file_id, caption=caption)
        elif file_type == "video":
            sent = await client.send_video(message.chat.id, file_id, caption=caption)
        elif file_type == "audio":
            sent = await client.send_audio(message.chat.id, file_id, caption=caption)
        else:
            return await message.reply("Unsupported file type.")

        await asyncio.sleep(1800)  # 30 minutes
        try:
            await client.delete_messages(message.chat.id, sent.id)
        except:
            pass

    elif len(slug) >= 15:
        verification = verifications_col.find_one({"slug": slug})
        if not verification or verification["user_id"] != user_id:
            return await message.reply("Invalid or expired verification link.")

        expires_at = datetime.utcnow() + timedelta(hours=12)
        users_col.update_one(
            {"user_id": user_id},
            {"$set": {"verified_at": datetime.utcnow(), "expires_at": expires_at}},
            upsert=True
        )
        verifications_col.delete_one({"slug": slug})

        return await message.reply("You are now verified for 12 hours!")

    else:
        return await message.reply("Invalid or unrecognized link.")

app.run()