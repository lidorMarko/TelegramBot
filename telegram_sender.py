import asyncio
from telegram import Bot
from config import Config


class TelegramSender:
    def __init__(self):
        self.bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
        self.channel_id = Config.TELEGRAM_CHANNEL_ID

    def format_message(self, job: dict, company_name: str) -> str:
        title = job.get(Config.FIELD_TITLE, "N/A")
        location = job.get(Config.FIELD_LOCATION, "")
        url = job.get(Config.FIELD_URL, "")

        message = f"New Job Alert!\n\n"
        message += f"{title}\n"
        message += f"{company_name}\n"
        if location:
            message += f"{location}\n"
        if url:
            message += f"\n{url}"

        return message

    async def send_message_async(self, job: dict, company_name: str):
        message = self.format_message(job, company_name)
        await self.bot.send_message(chat_id=self.channel_id, text=message)

    def send_message(self, job: dict, company_name: str):
        asyncio.run(self.send_message_async(job, company_name))
