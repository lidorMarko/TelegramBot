from html import escape
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from config import Config


class TelegramSender:

    def format_message(self, job: dict, company_name: str, hashtags: list = None) -> str:
        title = escape(job.get(Config.FIELD_TITLE, "לא צוין") or "לא צוין")
        location = escape(job.get(Config.FIELD_LOCATION, "") or "")
        url = job.get(Config.FIELD_URL, "") or ""
        company = escape(company_name or "")

        message = ""
        message += f"💼 <b>{title}</b>\n"
        message += f"🏢 {company}\n"

        if location:
            message += f"📍 {location}\n"

        message += "\n━━━━━━━━━━━━━━\n"

        if url:
            message += f'\n🔗 <a href="{escape(url)}">לצפייה במשרה</a>'

        if hashtags:
            line = " ".join(f"#{t}" if not t.startswith("#") else t for t in hashtags)
            message += f"\n\n{line}"

        return message

    async def send_for_review(self, bot: Bot, job: dict, company_name: str, queue_id: str, hashtags: list = None, channel_id: str = None):
        """Send the job to the review group with Approve / Reject / Udemy / Hashtag buttons."""
        if channel_id is None:
            channel_id = Config.REVIEW_CHANNEL_ID
        count = len(hashtags) if hashtags else 0
        hashtag_label = f"🏷️ {count} תגיות ✅" if count else "🏷️ הוסף האשטאג"
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve:{queue_id}"),
                InlineKeyboardButton("❌ Reject",  callback_data=f"reject:{queue_id}"),
            ],
            [
                InlineKeyboardButton("🎓 הוסף קורס Udemy", callback_data=f"udemy:{queue_id}"),
                InlineKeyboardButton(hashtag_label, callback_data=f"hashtag:{queue_id}"),
            ],
        ])
        return await bot.send_message(
            chat_id=channel_id,
            text=self.format_message(job, company_name, hashtags=hashtags),
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    async def send_to_public(self, bot: Bot, job: dict, company_name: str, channel_id: str = None, udemy_url: str = None, hashtags: list = None):
        """Send an approved job to the specified public channel."""
        if channel_id is None:
            channel_id = Config.TELEGRAM_PROD_CHANNEL_ID
        keyboard = None
        if udemy_url:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎓 הכינו את עצמכם לשאלות ראיון עבודה", url=udemy_url)
            ]])
        await bot.send_message(
            chat_id=channel_id,
            text=self.format_message(job, company_name, hashtags=hashtags),
            parse_mode="HTML",
            reply_markup=keyboard,
        )
