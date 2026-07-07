import os
from urllib.parse import quote as _url_quote
from dotenv import load_dotenv

load_dotenv()


class Config:
    # MongoDB
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DATABASE = os.getenv("MONGO_DATABASE", "jobsense")
    MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "companies")

    # Job field names (embedded in latestJobs array)
    FIELD_TITLE = os.getenv("FIELD_TITLE", "title")
    FIELD_LOCATION = os.getenv("FIELD_LOCATION", "location")
    FIELD_DESCRIPTION = os.getenv("FIELD_DESCRIPTION", "description")
    FIELD_URL = os.getenv("FIELD_URL", "url")
    FIELD_FIRST_SEEN = os.getenv("FIELD_FIRST_SEEN", "firstSeenAt")
    FIELD_STATUS = os.getenv("FIELD_STATUS", "status")
    FIELD_JOB_HASH = os.getenv("FIELD_JOB_HASH", "jobHash")

    # Company field names
    FIELD_COMPANY_NAME = os.getenv("FIELD_COMPANY_NAME", "name")
    FIELD_LATEST_JOBS = os.getenv("FIELD_LATEST_JOBS", "latestJobs")

    # Job status values
    STATUS_PENDING = "PENDING_REVIEW"
    STATUS_IN_REVIEW = "IN_REVIEW"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_SENT = "SENT"

    # Telegram — main bot (CS jobs)
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    REVIEW_CHANNEL_ID = os.getenv("REVIEW_CHANNEL_ID")
    TELEGRAM_PROD_CHANNEL_ID = os.getenv("TELEGRAM_PROD_CHANNEL_ID")

    # Telegram — electronics bot
    TELEGRAM_ELECTRONICS_BOT_TOKEN = os.getenv("TELEGRAM_ELECTRONICS_BOT_TOKEN")
    TELEGRAM_ELECTRONICS_REVIEW_CHANNEL_ID = os.getenv("TELEGRAM_ELECTRONICS_REVIEW_CHANNEL_ID")
    TELEGRAM_ELECTRONICS_CHANNEL_ID = os.getenv("TELEGRAM_ELECTRONICS_CHANNEL_ID")
    TELEGRAM_ELECTRONICS_CHANNEL_URL = os.getenv("TELEGRAM_ELECTRONICS_CHANNEL_URL", "")

    # Telegram — EU bot (optional; bot is skipped if any field is missing)
    TELEGRAM_BACKEND_EU_BOT_TOKEN = os.getenv("TELEGRAM_BACKEND_EU_BOT_TOKEN")
    TELEGRAM_BACKEND_EU_REVIEW_CHANNEL_ID = os.getenv("TELEGRAM_BACKEND_EU_REVIEW_CHANNEL_ID")
    TELEGRAM_BACKEND_EU_CHANNEL_ID = os.getenv("TELEGRAM_BACKEND_EU_CHANNEL_ID")

    # Optional footer CTA button added to public messages when enabled during review
    _FOOTER_PREFILL = _url_quote(
        "היי, ברצוני להוסיף חברה למאגר החברות של הבוט.\n"
        "הנה קישור לאתר המשרות של החברה: "
    )
    FOOTER_MESSAGE = os.getenv("FOOTER_MESSAGE", "📌 לחצו להוספת חברה למאגר")
    FOOTER_URL = os.getenv("FOOTER_URL", f"tg://resolve?domain=DevJobsILBot&text={_FOOTER_PREFILL}")
    FOOTER_MESSAGE_ELECTRONICS = os.getenv("FOOTER_MESSAGE_ELECTRONICS", "📌 לחצו להוספת חברה למאגר")
    FOOTER_URL_ELECTRONICS = os.getenv("FOOTER_URL_ELECTRONICS", f"tg://resolve?domain=ElectroJobsBot&text={_FOOTER_PREFILL}")

    # Polling interval in seconds
    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))

    @classmethod
    def validate(cls):
        # EU bot vars are optional — missing ones just disable that bot at startup.
        required = [
            ("TELEGRAM_BOT_TOKEN", cls.TELEGRAM_BOT_TOKEN),
            ("REVIEW_CHANNEL_ID", cls.REVIEW_CHANNEL_ID),
            ("TELEGRAM_PROD_CHANNEL_ID", cls.TELEGRAM_PROD_CHANNEL_ID),
            ("TELEGRAM_ELECTRONICS_BOT_TOKEN", cls.TELEGRAM_ELECTRONICS_BOT_TOKEN),
            ("TELEGRAM_ELECTRONICS_REVIEW_CHANNEL_ID", cls.TELEGRAM_ELECTRONICS_REVIEW_CHANNEL_ID),
            ("TELEGRAM_ELECTRONICS_CHANNEL_ID", cls.TELEGRAM_ELECTRONICS_CHANNEL_ID),
        ]
        missing = [name for name, value in required if not value]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
