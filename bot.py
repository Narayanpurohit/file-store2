import asyncio
import secrets
import logging
from datetime import datetime, timedelta
import requests

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    InputMediaPhoto
)
from config import API_ID, API_HASH, BOT_TOKEN, URL_SHORTENER_API, SHORTENER_DOMAIN, ADMINS
from db import files_col, users_col, verifications_col

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = Client("file-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


def generate_slug(length=6):
    core = secrets.token_urlsafe(length)[:length]
    return f"fs_{core}"


def generate_verification_slug():
    slug = secrets.token_urlsafe(12)
    while verifications_col.find_one({"slug": slug}):
        slug = secrets.token_urlsafe(12)
    return slug


def get_short_link(link):
    try:
        if not link.startswith("http://") and not link.startswith("https://"):
            link = "https://" + link

        api_url = f"https://{SHORTENER_DOMAIN}/api?api={URL_SHORTENER_API}&url={link}"
        response = requests.get(api_url)
        data = response.json()

        if data.get("status") == "success" and "shortenedUrl" in data:
            return data["shortenedUrl"]
    except Exception as e:
        logger.error(f"Shortening failed: {e}")
    return link


@app.on_message(filters.video)
async def handle_file(client, message: Message):
    user_id = message.from_user.id
    if user_id not in ADMINS:
        return await message.reply("Only admins can upload and generate file links.")

    file_id = message.video.file_id
    slug = generate_slug()

    while files_col.find_one({"slug": slug}):
        slug = generate_slug()

    files_col.insert_one({
        "slug": slug,
        "file_id": file_id,
        "uploaded_by": user_id,
        "created_at": datetime.utcnow()
    })

    link = f"https://t.me/irish1Obot?start={slug}"
    await message.reply_text(f"Here's your download link:\n{link}")
    logger.info(f"File uploaded by {user_id}, slug: {slug}")


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
                [InlineKeyboardButton("How to verify?", callback_data="How_to_verify❓")],
                [InlineKeyboardButton("💳 Buy subscription| No ads", callback_data="buy_subs")]
            ])
            return await message.reply(
                f"You are not verified, please verify yourself to continue:\n\nVerification link: {verify_link}",
                reply_markup=buttons
            )

        file_data = files_col.find_one({"slug": slug})
        if not file_data:
            return await message.reply("Invalid file link.")

        sent = await client.send_video(
            chat_id=message.chat.id,
            video=file_data["file_id"],
            caption="This message will be deleted in 30 minutes"
        )
        asyncio.create_task(delete_message_after_delay(client, message.chat.id, sent.id))
        logger.info(f"Sent file {file_data['file_id']} to {user_id}")

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

        logger.info(f"User {user_id} verified for 12 hours")
        return await message.reply("You are now verified for 12 hours!")

    else:
        return await message.reply("Invalid or unrecognized link.")


@app.on_callback_query(filters.regex("buy_sub"))
async def handle_buy_subscription(client, callback_query: CallbackQuery):
    await callback_query.message.edit_media(
        media=InputMediaPhoto(
            media="https://envs.sh/8-u.jpg",
            caption=(
                "10 days - 20 INR\n"
                "1 Month - 50 INR\n"
                "3 Month - 120 INR\n\n"
                "• This plan allows you to use our bots without any verification steps (ads).\n\n"
                "For other payment methods, contact @JN_DEV"
            )
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Send screenshots", url="https://t.me/JN_DEV")],
            [InlineKeyboardButton("Back", callback_data="back_to_verify")]
        ])
    )


@app.on_callback_query(filters.regex("back_to_verify"))
async def handle_back_verify(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    verification_slug = generate_verification_slug()
    verifications_col.insert_one({
        "slug": verification_slug,
        "user_id": user_id,
        "created_at": datetime.utcnow()
    })
    verify_link = f"https://t.me/{(await app.get_me()).username}?start={verification_slug}"
    short_link = get_short_link(verify_link)

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("Buy subscription | No ads", callback_data="buy_sub")]
    ])
    await callback_query.message.edit_caption(
        caption=f"You are not verified, please verify yourself to continue:\n\nVerification link: {verify_link}",
        reply_markup=buttons
    )


async def delete_message_after_delay(client, chat_id, message_id, delay_minutes=30):
    await asyncio.sleep(delay_minutes * 60)
    try:
        await client.delete_messages(chat_id, message_id)
        logger.info(f"Deleted message {message_id} in chat {chat_id}")
    except Exception as e:
        logger.warning(f"Failed to delete message {message_id} in chat {chat_id}: {e}")


@app.on_message(filters.command("upgrade"))
async def admin_upgrade_user(client, message: Message):
    if message.from_user.id not in ADMINS:
        return await message.reply("You are not authorized to use this command.")

    args = message.text.split()
    if len(args) != 3 or not args[1].isdigit() or not args[2].isdigit():
        return await message.reply("Usage: /upgrade <user_id> <days>")

    user_id = int(args[1])
    days = int(args[2])
    expires_at = datetime.utcnow() + timedelta(days=days)

    users_col.update_one(
        {"user_id": user_id},
        {"$set": {"verified_at": datetime.utcnow(), "expires_at": expires_at}},
        upsert=True
    )

    await message.reply(f"User {user_id} has been upgraded for {days} day(s).")
    await client.send_message(
        chat_id=user_id,
        text=f"You have been upgraded for **{days} day(s).**"
    )
    logger.info(f"Admin {message.from_user.id} upgraded user {user_id} for {days} days")


@app.on_message(filters.command("check"))
async def check_verification(client, message: Message):
    user_id = message.from_user.id
    user = users_col.find_one({"user_id": user_id})

    if not user or user.get("expires_at", datetime.min) < datetime.utcnow():
        return await message.reply("You are not verified.")

    time_left = user["expires_at"] - datetime.utcnow()
    hours = time_left.total_seconds() // 3600
    minutes = (time_left.total_seconds() % 3600) // 60

    return await message.reply(f"You are verified for another {int(hours)}h {int(minutes)}m.")


@app.on_message(filters.command("broadcast") & filters.reply)
async def broadcast_message(client, message: Message):
    if message.from_user.id not in ADMINS:
        return await message.reply("You're not authorized to use this command.")

    replied = message.reply_to_message
    if not replied:
        return await message.reply("Please reply to the message you want to broadcast.")

    users = users_col.find()
    sent_count = 0
    for user in users:
        try:
            await replied.copy(chat_id=user["user_id"])
            sent_count += 1
        except Exception as e:
            logger.warning(f"Failed to send to {user['user_id']}: {e}")

    await message.reply(f"Broadcast sent to {sent_count} users.")


@app.on_callback_query(filters.regex("how_to_verify"))
async def how_to_verify_handler(client, callback_query):
    await callback_query.answer()
    try:
        await client.send_video(
            chat_id=callback_query.from_user.id,
            video="BAACAgUAAxkBAAEEleloHg1hR92Z1YRh4RveU_kjHVGLHwACgxUAAtum8FQyo6V8lYfYTR4E",
            caption="Watch this video to learn how to verify yourself."
        )
    except Exception as e:
        logger.error(f"Error sending how-to video: {e}")


# Run the bot
if __name__ == "__main__":
    app.run()
    

