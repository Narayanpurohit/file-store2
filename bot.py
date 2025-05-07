from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import random, string, time
from config import API_ID, API_HASH, BOT_TOKEN, CHANNEL_1_ID, CHANNEL_2_ID
from db import users_col, files_col, verifications_col

app = Client("FileShareBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Generate short slug (≤ 5 chars)
def generate_short_slug():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(3, 5)))

# Generate long verification slug (≥ 15 chars)
def generate_verification_slug():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=random.randint(15, 18)))

# Check if user joined both channels
async def check_subscription(client, user_id, slug):
    ch1_invite = await client.create_chat_invite_link(CHANNEL_1_ID, creates_join_request=False)
    ch2_invite = await client.create_chat_invite_link(CHANNEL_2_ID, creates_join_request=True)

    try:
        ch1_member = await client.get_chat_member(CHANNEL_1_ID, user_id)
        if ch1_member.status not in ("member", "administrator", "creator"):
            raise Exception()
    except:
        return ch1_invite.invite_link, ch2_invite.invite_link

    try:
        ch2_member = await client.get_chat_member(CHANNEL_2_ID, user_id)
        if ch2_member.status in ("left", "kicked"):
            raise Exception()
    except:
        return ch1_invite.invite_link, ch2_invite.invite_link

    return None, None

@app.on_message(filters.private & filters.command("start"))
async def start_handler(client, message):
    user_id = message.from_user.id
    slug = message.text.split(" ", 1)[1] if len(message.command) > 1 else None

    # Add user to DB if not exists
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({"user_id": user_id})

    if slug:
        # Force subscription check
        ch1_link, ch2_link = await check_subscription(client, user_id, slug)
        if ch1_link or ch2_link:
            try_again_url = f"https://t.me/{(await client.get_me()).username}?start={slug}"
            buttons = [
                [InlineKeyboardButton("Join Channel 1", url=ch1_link)],
                [InlineKeyboardButton("Request to Join Channel 2", url=ch2_link)],
                [InlineKeyboardButton("✅ Try Again", url=try_again_url)]
            ]
            await message.reply_text(
                "You must join both channels to use this bot.",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

        # If it's a verification slug
        if len(slug) >= 15:
            data = verifications_col.find_one({"slug": slug})
            if data:
                verifications_col.update_one(
                    {"slug": slug},
                    {"$set": {"user_id": user_id, "verified_at": int(time.time())}}
                )
                await message.reply_text("You’ve been verified for 4 hours. Now try the file link again.")
            else:
                await message.reply_text("Invalid or expired verification link.")
        # If it's a file slug
        else:
            # Check if user is verified
            verified = verifications_col.find_one({"user_id": user_id})
            if verified and time.time() - verified["verified_at"] <= 4 * 3600:
                file_data = files_col.find_one({"slug": slug})
                if file_data:
                    await client.send_cached_media(message.chat.id, file_data["file_id"])
                else:
                    await message.reply_text("File not found.")
            else:
                # Not verified: generate verification link
                verify_slug = generate_verification_slug()
                verifications_col.insert_one({
                    "user_id": user_id,
                    "slug": verify_slug,
                    "verified_at": 0
                })
                verify_link = f"https://t.me/{(await client.get_me()).username}?start={verify_slug}"
                await message.reply_text(
                    "You are not verified. Click below to verify (valid for 4 hours):",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("✅ Verify Me", url=verify_link)]]
                    )
                )
    else:
        await message.reply_text("Send me a file and I’ll give you a sharable link!")

@app.on_message(filters.private & filters.document)
async def handle_file(client, message):
    slug = generate_short_slug()
    file_id = message.document.file_id
    files_col.insert_one({"slug": slug, "file_id": file_id})
    link = f"https://t.me/{(await client.get_me()).username}?start={slug}"
    await message.reply_text(f"Here is your link:\n`{link}`", quote=True)

app.run()