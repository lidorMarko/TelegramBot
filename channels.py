from dataclasses import dataclass, field

from config import Config


@dataclass
class BotChannelConfig:
    name: str           # human-readable label for logs
    category: str       # job category this bot handles (e.g. "cs", "backend_eu")
    bot_token: str
    review_channel_id: str
    public_channel_id: str
    cross_promo_url: str = ""
    footer_message: str = ""
    footer_url: str = ""
    donation_url: str = ""
    enable_expiry: bool = False  # run daily stale-entry cleanup + zero-result notification
    english_only: bool = False   # use English labels (EU channels)


def _all_configs() -> list[BotChannelConfig]:
    return [
        # ── Israel bots ────────────────────────────────────────────────────────
        BotChannelConfig(
            name="CS — Israel",
            category="cs",
            bot_token=Config.TELEGRAM_BOT_TOKEN or "",
            review_channel_id=Config.REVIEW_CHANNEL_ID or "",
            public_channel_id=Config.TELEGRAM_PROD_CHANNEL_ID or "",
            cross_promo_url=Config.TELEGRAM_ELECTRONICS_CHANNEL_URL,
            footer_message=Config.FOOTER_MESSAGE,
            footer_url=Config.FOOTER_URL,
            donation_url="https://paypal.me/DevJobs247",
            enable_expiry=True,
        ),
        BotChannelConfig(
            name="Electronics — Israel",
            category="electronics",
            bot_token=Config.TELEGRAM_ELECTRONICS_BOT_TOKEN or "",
            review_channel_id=Config.REVIEW_CHANNEL_ID or "",  # shared IL review channel
            public_channel_id=Config.TELEGRAM_ELECTRONICS_CHANNEL_ID or "",
            footer_message=Config.FOOTER_MESSAGE_ELECTRONICS,
            footer_url=Config.FOOTER_URL_ELECTRONICS,
            donation_url="https://paypal.me/DevJobs247",
        ),
        # ── EU bot — single unified channel ───────────────────────────────────
        BotChannelConfig(
            name="Tech Jobs EU",
            category="backend_eu",
            bot_token=Config.TELEGRAM_BACKEND_EU_BOT_TOKEN or "",
            review_channel_id=Config.TELEGRAM_BACKEND_EU_REVIEW_CHANNEL_ID or "",
            public_channel_id=Config.TELEGRAM_BACKEND_EU_CHANNEL_ID or "",
            english_only=True,
        ),
    ]


# Bots missing any required credential are silently skipped at startup.
CHANNEL_CONFIGS: list[BotChannelConfig] = [
    c for c in _all_configs()
    if c.bot_token and c.review_channel_id and c.public_channel_id
]
