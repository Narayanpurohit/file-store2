from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import asyncio

from config import API_ID, API_HASH

BOT_TOKEN2 = "6907718633:AAGw-xOIW0pFVhKy7VAtvZBgUI3L2PFEQAA"
app2 = Client("redirect-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN2)


@app2.on_message(filters.private & filters.command("start"))
async def start_handler(client, message):
    if len(message.command) > 1:
        payload = message.command[1]

        # Choose the target bot based on the payload length
        target_bot = "Itadori101bot" if len(payload) < 15 else "jin_ho_bot"
        new_link = f"https://t.me/{target_bot}?start={payload}"

        sent = await message.reply_text(
            "This message will be deleted in 10 minutes. Use link before that.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Click here", url=new_link)]
            ])
        )

        await asyncio.sleep(600)
        await sent.delete()
    else:
        await message.reply_text("Welcome! Please use a valid start link.")


if __name__ == "__main__":
    