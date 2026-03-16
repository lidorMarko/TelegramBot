from html import escape
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from config import Config


class TelegramSender:

    def format_message(self, job: dict, company_name: str) -> str:
        title = escape(job.get(Config.FIELD_TITLE, "לא צוין") or "לא צוין")
        location = escape(job.get(Config.FIELD_LOCATION, "") or "")
        url = job.get(Config.FIELD_URL, "") or ""
        company = escape(company_name or "")

        message = "\u200F🚀 <b>משרה חדשה</b>\n\n"
        message += f"💼 <b>{title}</b>\n"
        message += f"🏢 {company}\n"

        if location:
            message += f"📍 {location}\n"

        message += "\n━━━━━━━━━━━━━━\n"

        if url:
            message += f'\n🔗 <a href="{escape(url)}">לצפייה במשרה</a>'

        return message

    async def send_for_review(self, bot: Bot, job: dict, company_name: str, queue_id: str):
        """Send the job to the private review group with Approve / Reject buttons."""
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{queue_id}"),
            InlineKeyboardButton("❌ Reject",  callback_data=f"reject:{queue_id}"),
        ]])
        await bot.send_message(
            chat_id=Config.REVIEW_CHANNEL_ID,
            text=self.format_message(job, company_name),
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    async def send_to_public(self, bot: Bot, job: dict, company_name: str):
        """Send an approved job to the public channel."""
        await bot.send_message(
            chat_id=Config.TELEGRAM_PROD_CHANNEL_ID,
            text=self.format_message(job, company_name),
            parse_mode="HTML",
        )
