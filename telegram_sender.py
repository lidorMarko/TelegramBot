from html import escape
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from config import Config


class TelegramSender:

    def format_message(self, job: dict, company_name: str, hashtags: list = None, english_only: bool = False) -> str:
        _fallback = "Not specified" if english_only else "לא צוין"
        title = escape(job.get(Config.FIELD_TITLE, _fallback) or _fallback)
        location = escape(job.get(Config.FIELD_LOCATION, "") or "")
        company = escape(company_name or "")

        message = ""
        message += f"💼 <b>{title}</b>\n"
        message += f"🏢 {company}\n"

        if location:
            message += f"📍 {location}\n"

        message += "━━━━━━━━━━━━━━"

        if hashtags:
            line = " ".join(f"#{t}" if not t.startswith("#") else t for t in hashtags)
            message += f"\n{line}"

        return message

    async def send_for_review(self, bot: Bot, job: dict, company_name: str, queue_id: str, hashtags: list = None, channel_id: str = None, cross_promo_url: str = "", footer_message: str = "", english_only: bool = False, channel_label: str = "", reroute_options: list = None, current_target_id: str = "", donation_url: str = ""):
        """Send the job to the review group with Approve / Reject / Udemy / Hashtag buttons."""
        if channel_id is None:
            channel_id = Config.REVIEW_CHANNEL_ID
        count = len(hashtags) if hashtags else 0
        if english_only:
            hashtag_label = f"🏷️ {count} tags ✅" if count else "🏷️ Add Hashtag"
        else:
            hashtag_label = f"🏷️ {count} תגיות ✅" if count else "🏷️ הוסף האשטאג"
        url = job.get(Config.FIELD_URL, "") or ""
        view_label = "🔗 View Job" if english_only else "🔗 לצפייה במשרה"
        udemy_label = "🎓 Add Udemy Course" if english_only else "🎓 הוסף קורס Udemy"
        rows = []
        if url and url.startswith(("http://", "https://")):
            rows.append([InlineKeyboardButton(view_label, url=url)])
        schedule_label = "🕒 Schedule Send" if english_only else "🕒 תזמן שליחה"
        rows += [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve:{queue_id}"),
                InlineKeyboardButton("❌ Reject",  callback_data=f"reject:{queue_id}"),
            ],
            [InlineKeyboardButton(schedule_label, callback_data=f"sched_menu:{queue_id}")],
            [
                InlineKeyboardButton(udemy_label, callback_data=f"udemy:{queue_id}"),
                InlineKeyboardButton(hashtag_label, callback_data=f"hashtag:{queue_id}"),
            ],
        ]
        if cross_promo_url:
            cross_promo_label = "📢 Add Cross Promo" if english_only else "📢 הוסף פרסום צולב"
            rows.append([InlineKeyboardButton(cross_promo_label, callback_data=f"cross_promo:{queue_id}")])
        if footer_message:
            footer_label = "📌 Add Footer Message" if english_only else "📌 הוסף הודעה קטנה"
            rows.append([InlineKeyboardButton(footer_label, callback_data=f"footer_message:{queue_id}")])
        if donation_url:
            rows.append([InlineKeyboardButton("💝 הוסף תרומות", callback_data=f"donation:{queue_id}")])
        if reroute_options:
            reroute_row = []
            for name, ch_id in reroute_options:
                if ch_id == current_target_id:
                    reroute_row.append(InlineKeyboardButton(f"📡 {name} ✅", callback_data="noop"))
                else:
                    reroute_row.append(InlineKeyboardButton(f"📤 {name}", callback_data=f"reroute:{queue_id}:{ch_id}"))
            for i in range(0, len(reroute_row), 2):
                rows.append(reroute_row[i:i + 2])
        keyboard = InlineKeyboardMarkup(rows)
        text = self.format_message(job, company_name, hashtags=hashtags, english_only=english_only)
        if channel_label:
            text = f"📡 <b>{channel_label}</b>\n\n{text}"
        return await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    async def send_to_public(self, bot: Bot, job: dict, company_name: str, channel_id: str = None, udemy_url: str = None, hashtags: list = None, cross_promo_url: str = "", footer_message: str = "", footer_url: str = "", english_only: bool = False, donation_url: str = "", cta_text: str = "", cta_url: str = ""):
        """Send an approved job to the specified public channel."""
        if channel_id is None:
            channel_id = Config.TELEGRAM_PROD_CHANNEL_ID
        text = self.format_message(job, company_name, hashtags=hashtags, english_only=english_only)
        job_url = job.get(Config.FIELD_URL, "") or ""
        view_label = "🔗 View Job" if english_only else "🔗 לצפייה במשרה"
        udemy_label = "🎓 Interview Prep" if english_only else "🎓 שאלות הכנה למשרה זו"
        button_rows = []
        if job_url and job_url.startswith(("http://", "https://")):
            button_rows.append([InlineKeyboardButton(view_label, url=job_url)])
        if udemy_url:
            button_rows.append([InlineKeyboardButton(udemy_label, url=udemy_url)])
        if cross_promo_url:
            button_rows.append([InlineKeyboardButton("🔌 לעוד משרות בתחום החשמל ואלקטרוניקה עברו לערוץ הייעודי", url=cross_promo_url)])
        if footer_message and footer_url:
            button_rows.append([InlineKeyboardButton(footer_message, url=footer_url)])
        if donation_url:
            button_rows.append([InlineKeyboardButton("💝 לתרומות לערוץ", url=donation_url)])
        if cta_text and cta_url and cta_url.startswith(("http://", "https://")):
            button_rows.append([InlineKeyboardButton(cta_text, url=cta_url)])
        keyboard = InlineKeyboardMarkup(button_rows) if button_rows else None
        await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
