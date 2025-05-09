import asyncio
import secrets
import httpx
from datetime import datetime, timedelta

from pyrogram import Client, filters
from pyrogram.types import Message
from config import API_ID, API_HASH, BOT_TOKEN, URL_SHORTENER_API, SHORTENER_DOMAIN
from db import files_col, users_col, verifications_col

app = Client("file-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Bypass verification slugs
BYPASS_VERIFICATION_SLUGS = ["fs_MVbzAH", "fs_MVbzAH"]  # Add your allowed slugs here

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
async def shorten_url(original_url):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{URL_SHORTENER_API}?url={original_url}")
            data = response.json()
            return data.get("shortenedUrl") or original_url
    except Exception as e:
        print(f"Shortening failed: {e}")
        return original_url

@app.on_message(filters.video)
async def handle_file(client, message: Message):
    file_id = message.video.file_id
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
    await message.reply_text(f"Here's your video link:\n{link}")

@app.on_message(filters.command("start"))
async def handle_start(client, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) == 1:
        return await message.reply("Welcome to the Video Bot!")

    slug = args[1].strip()
    user_id = message.from_user.id

    if slug in BYPASS_VERIFICATION_SLUGS:
        # Bypass verification and send video directly
        file_data = files_col.find_one({"slug": slug})
        if not file_data:
            return await message.reply("Invalid file link.")
        await client.send_video(
            chat_id=message.chat.id,
            video=file_data["file_id"],
            caption="This message will be deleted in 30 minutes."
        )
        await asyncio.sleep(1800)
        await client.delete_messages(chat_id=message.chat.id, message_ids=[message.id + 1])
        return

    # Verification process for non-bypass slugs
    user = users_col.find_one({"user_id": user_id})
    if not user or user.get("expires_at", datetime.min) < datetime.utcnow():
        verification_slug = generate_verification_slug()
        verifications_col.insert_one({
            "slug": verification_slug,
            "user_id": user_id,
            "created_at": datetime.utcnow()
        })
        verify_link = f"https://t.me/{(await app.get_me()).username}?start={verification_slug}"
        short_link = await shorten_url(verify_link)
        return await message.reply(
            f"You are not verified. Please verify yourself to continue.\n\n"
            f"Click here to verify: {short_link}"
        )

    # Verified user — send file
    file_data = files_col.find_one({"slug": slug})
    if not file_data:
        return await message.reply("Invalid file link.")
    await client.send_video(
        chat_id=message.chat.id,
        video=file_data["file_id"],
        caption="This message will be deleted in 30 minutes."
    )
    await asyncio.sleep(1800)
    await client.delete_messages(chat_id=message.chat.id, message_ids=[message.id + 1])

@app.on_message(filters.command("verify"))
async def handle_verify(client, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) == 1:
        return await message.reply("Please provide a verification link to proceed.")

    slug = args[1].strip()
    user_id = message.from_user.id

    verification = verifications_col.find_one({"slug": slug})
    if not verification or verification["user_id"] != user_id:
        return await message.reply("Invalid or expired verification link.")

    # Mark user as verified and invalidate the slug
    expires_at = datetime.utcnow() + timedelta(hours=12)  # 12 hours verification time
    users_col.update_one(
        {"user_id": user_id},
        {"$set": {"verified_at": datetime.utcnow(), "expires_at": expires_at}},
        upsert=True
    )
    verifications_col.delete_one({"slug": slug})

    return await message.reply("You are now verified for 12 hours!")

app.run()