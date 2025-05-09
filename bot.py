import asyncio
import secrets
import httpx
from datetime import datetime, timedelta

from pyrogram import Client, filters
from pyrogram.types import Message
from config import API_ID, API_HASH, BOT_TOKEN, URL_SHORTENER_API, URL_SHORTENER_KEY
from db import files_col, users_col, verifications_col

app = Client("file-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Generate file slug with "fs_" prefix
def generate_slug(length=6):
    core = secrets.token_urlsafe(length)[:length]
    return f"fs_{core}"

# Generate unique verification slug
def generate_verification_slug():
    slug = secrets.token_urlsafe(12)
    while verifications_col.find_one({"slug": slug}):
        slug = secrets.token_urlsafe(12)
    return slug

# URL shortener function
import requests

def get_short_link(link):
    from config import URL_SHORTENER_API, SHORTENER_DOMAIN

    try:
        api_url = f"https://{SHORTENER_DOMAIN}/api?api={URL_SHORTENER_API}&url={link}"
        response = requests.get(api_url)
        data = response.json()

        if data.get("status") == "success" and "shortenedUrl" in data:
            return data["shortenedUrl"]
    except Exception as e:
        print(f"Shortening failed: {e}")

    return link  # fallback to original if something fails

@app.on_message(filters.document | filters.video | filters.audio)
async def handle_file(client, message: Message):
    file_id = (
        message.document.file_id if message.document else
        message.video.file_id if message.video else
        message.audio.file_id
    )
    slug = generate_slug()

    # Ensure uniqueness
    while files_col.find_one({"slug": slug}):
        slug = generate_slug()

    files_col.insert_one({
        "slug": slug,
        "file_id": file_id,
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
        # File slug handling
        user = users_col.find_one({"user_id": user_id})
        if not user or user.get("expires_at", datetime.min) < datetime.utcnow():
            # Not verified
            verification_slug = generate_verification_slug()
            verifications_col.insert_one({
                "slug": verification_slug,
                "user_id": user_id,
                "created_at": datetime.utcnow()
            })
            verify_link = f"https://t.me/{(await app.get_me()).username}?start={verification_slug}"
            short_link = get_short_link(verify_link)
            return await message.reply(
                f"Please verify yourself first:\n\n"
                f"Original: {verify_link}\n"
                f"Shortened: {short_link}"
            )

        # Verified user — send file
        file_data = files_col.find_one({"slug": slug})
        if not file_data:
            return await message.reply("Invalid file link.")
        await client.send_document(chat_id=message.chat.id, document=file_data["file_id"])

    elif len(slug) >= 15:
        # Verification slug
        verification = verifications_col.find_one({"slug": slug})
        if not verification or verification["user_id"] != user_id:
            return await message.reply("Invalid or expired verification link.")

        # Mark user as verified and invalidate the slug
        expires_at = datetime.utcnow() + timedelta(hours=4)
        users_col.update_one(
            {"user_id": user_id},
            {"$set": {"verified_at": datetime.utcnow(), "expires_at": expires_at}},
            upsert=True
        )
        verifications_col.delete_one({"slug": slug})

        return await message.reply("You are now verified for 4 hours!")

    else:
        return await message.reply("Invalid or unrecognized link.")

app.run()