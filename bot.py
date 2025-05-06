import asyncio
import secrets
from datetime import datetime, timedelta

from pyrogram import Client, filters
from pyrogram.types import Message
from config import API_ID, API_HASH, BOT_TOKEN
from db import files_col, users_col, verifications_col

app = Client("file-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def generate_slug(length=6):
    return secrets.token_urlsafe(length)[:length]

def generate_verification_slug():
    return secrets.token_urlsafe(12)

async def check_subscription(client, user_id, slug):
    from config import CHANNEL_1_ID, CHANNEL_2_ID

    # Generate invite links
    ch1_invite = await client.create_chat_invite_link(CHANNEL_1_ID, creates_join_request=False)
    ch2_invite = await client.create_chat_invite_link(CHANNEL_2_ID, creates_join_request=True)

    # Check Channel 1 membership
    try:
        ch1_member = await client.get_chat_member(CHANNEL_1_ID, user_id)
        if ch1_member.status not in ("member", "administrator", "creator"):
            raise Exception()
    except:
        return ch1_invite.invite_link, ch2_invite.invite_link

    # Check Channel 2 join/request status
    try:
        ch2_member = await client.get_chat_member(CHANNEL_2_ID, user_id)
        if ch2_member.status in ("left", "kicked"):
            raise Exception()
    except:
        return ch1_invite.invite_link, ch2_invite.invite_link

    return None, None  # means user passed

@app.on_message(filters.document | filters.video | filters.audio)
async def handle_file(client, message: Message):
    file_id = message.document.file_id if message.document else (
              message.video.file_id if message.video else message.audio.file_id)
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

    if len(slug) >= 15:
        # Verification slug
        verification = verifications_col.find_one({"slug": slug})
        if not verification or verification["user_id"] != user_id:
            return await message.reply("Invalid or expired verification link.")

        # Mark user as verified
        expires_at = datetime.utcnow() + timedelta(hours=4)
        users_col.update_one(
            {"user_id": user_id},
            {"$set": {"verified_at": datetime.utcnow(), "expires_at": expires_at}},
            upsert=True
        )
        return await message.reply("You are now verified for 4 hours!")
    
    else:
        # File slug
            # Force subscription check
    ch1_link, ch2_link = await check_subscription(client, message.from_user.id, slug)
    if ch1_link or ch2_link:
        try_again_url = f"https://t.me/{(await client.get_me()).username}?start={slug}"
        buttons = [
            [InlineKeyboardButton("Join Channel 1", url=ch1_link)],
            [InlineKeyboardButton("Request to Join Channel 2", url=ch2_link)],
            [InlineKeyboardButton("✅ Try Again", url=try_again_url)]
        ]
        await message.reply_text(
            "You must join both channels to access this bot.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return
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
            return await message.reply(f"Please verify yourself first:\n{verify_link}")

        # Verified user — send file
        file_data = files_col.find_one({"slug": slug})
        if not file_data:
            return await message.reply("Invalid file link.")

        await client.send_document(chat_id=message.chat.id, document=file_data["file_id"])

app.run()