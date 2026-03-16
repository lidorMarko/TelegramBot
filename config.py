import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # MongoDB
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DATABASE = os.getenv("MONGO_DATABASE")
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

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    REVIEW_CHANNEL_ID = os.getenv("REVIEW_CHANNEL_ID")          # private group for reviewers
    TELEGRAM_PROD_CHANNEL_ID = os.getenv("TELEGRAM_PROD_CHANNEL_ID")  # public channel for approved jobs

    # Polling interval in seconds
    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))

    @classmethod
    def validate(cls):
        required = [
            ("MONGO_DATABASE", cls.MONGO_DATABASE),
            ("TELEGRAM_BOT_TOKEN", cls.TELEGRAM_BOT_TOKEN),
            ("REVIEW_CHANNEL_ID", cls.REVIEW_CHANNEL_ID),
            ("TELEGRAM_PROD_CHANNEL_ID", cls.TELEGRAM_PROD_CHANNEL_ID),
        ]
        missing = [name for name, value in required if not value]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
