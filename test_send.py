from config import Config
from telegram_sender import TelegramSender

Config.validate()

sender = TelegramSender()

test_job = {
    "title": "Test Job Title",
    "location": "Tel Aviv (Hybrid)",
    "url": "https://example.com/jobs/123"
}

sender.send_message(test_job, "Test Company")
print("Message sent!")
