import asyncio
import contextlib
import datetime
import logging
import re
import signal
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from channels import CHANNEL_CONFIGS, BotChannelConfig
from config import Config
from mongo_watcher import MongoWatcher
from telegram_sender import TelegramSender

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

_IL_TZ = ZoneInfo("Asia/Jerusalem")
_SCHEDULE_PRESETS_MINUTES = [15, 30, 60, 90, 120, 180]
_SCHEDULE_MAX_MINUTES = 10080  # 7 days


def _schedule_job_name(queue_id: str) -> str:
    return f"scheduled_send:{queue_id}"


def _to_il_time(dt: datetime.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(_IL_TZ).strftime("%H:%M")


def _cancel_scheduled_job(context, queue_id: str):
    if not context.job_queue:
        return
    for job in context.job_queue.get_jobs_by_name(_schedule_job_name(queue_id)):
        job.schedule_removal()


async def poll_jobs(context):
    watcher: MongoWatcher = context.bot_data["watcher"]
    category: str = context.bot_data["category"]
    review_channel_id: str = context.bot_data["review_channel_id"]
    public_channel_id: str = context.bot_data["public_channel_id"]
    cross_promo_url: str = context.bot_data.get("cross_promo_url", "")
    footer_message: str = context.bot_data.get("footer_message", "")
    english_only: bool = context.bot_data.get("english_only", False)
    channel_label: str = context.bot_data.get("channel_label", "")
    reroute_options: list = context.bot_data.get("reroute_options", [])
    donation_url: str = context.bot_data.get("donation_url", "")
    await watcher.process_pending_jobs(context.bot, category=category, review_channel_id=review_channel_id, public_channel_id=public_channel_id, cross_promo_url=cross_promo_url, footer_message=footer_message, english_only=english_only, channel_label=channel_label, reroute_options=reroute_options, donation_url=donation_url)


async def notify_zero_result_companies(context):
    """Daily 8 PM notification: companies with no jobs extracted."""
    watcher: MongoWatcher = context.bot_data["watcher"]
    review_channel_id: str = context.bot_data["review_channel_id"]
    names = watcher.get_zero_result_companies()
    if not names:
        await context.bot.send_message(
            chat_id=review_channel_id,
            text="✅ כל החברות יש להן משרות פעילות — אין חברות ריקות היום.",
        )
        return
    lines = "\n".join(f"• {n}" for n in sorted(names))
    text = (
        f"🚨 חברות ללא משרות ({len(names)}):\n\n{lines}"
    )
    await context.bot.send_message(chat_id=review_channel_id, text=text)


async def expire_stale_queue(context):
    """Daily job: auto-reject review queue entries older than 7 days."""
    watcher: MongoWatcher = context.bot_data["watcher"]
    expired = watcher.expire_stale_queue_entries(max_age_days=3)
    if expired:
        review_channel_id: str = context.bot_data["review_channel_id"]
        await context.bot.send_message(
            chat_id=review_channel_id,
            text=f"🗑️ {expired} משרות ישנות (3+ ימים) נדחו אוטומטית מתור הבדיקה.",
        )


async def handle_approval(update, context):
    query = update.callback_query
    print(f"[CALLBACK] data={query.data!r} from user={query.from_user.id}")

    if not query.data or not query.data.startswith(("approve:", "reject:")):
        await query.answer()
        return

    await query.answer(text="Processing...", show_alert=False)

    try:
        await _do_approval(query, context)
    except Exception as e:
        import traceback
        logging.exception("Unhandled error in handle_approval")
        print(f"[CALLBACK ERROR] {traceback.format_exc()}")
        try:
            await context.bot.send_message(
                chat_id=context.bot_data["review_channel_id"],
                text=f"⚠️ שגיאה לא צפויה בעת אישור:\n<code>{traceback.format_exc()[-800:]}</code>",
                parse_mode="HTML",
            )
        except Exception as send_err:
            print(f"[CALLBACK ERROR] also failed to send error message: {send_err}")


async def _do_approval(query, context):
    action, queue_id = query.data.split(":", 1)
    print(f"[APPROVAL] action={action} queue_id={queue_id}")
    watcher: MongoWatcher = context.bot_data["watcher"]

    entry = watcher.get_review_entry(queue_id)
    print(f"[APPROVAL] entry found: {entry is not None}")
    if not entry:
        logging.warning("Review entry not found for queue_id=%s", queue_id)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([]))
        await context.bot.send_message(
            chat_id=context.bot_data["review_channel_id"],
            text=f"⚠️ לא נמצא רשומה בתור הבדיקה (queue_id={queue_id}). ייתכן שכבר טופלה.",
        )
        return

    company_id = entry["company_id"]
    job_hash = entry["job_hash"]

    _cancel_scheduled_job(context, queue_id)
    if entry.get("scheduled_send_at"):
        watcher.set_scheduled_send(queue_id, None)

    if action == "approve":
        ok, error = await _send_approved_job(context, queue_id, entry)
        if not ok:
            await context.bot.send_message(
                chat_id=context.bot_data["review_channel_id"],
                text=f"⚠️ שליחה לערוץ הציבורי נכשלה: {error}",
            )
            return

        watcher.remove_from_review_queue(queue_id)
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Approved & Sent", callback_data="noop")
            ]])
        )

    elif action == "reject":
        watcher.update_job_status(company_id, job_hash, Config.STATUS_REJECTED)
        watcher.remove_from_review_queue(queue_id)
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Rejected", callback_data="noop")
            ]])
        )


async def _send_approved_job(context, queue_id: str, entry: dict) -> tuple[bool, str | None]:
    """Send an approved job to its public channel. Shared by manual approve and scheduled sends."""
    watcher: MongoWatcher = context.bot_data["watcher"]
    sender: TelegramSender = context.bot_data["sender"]
    company_id = entry["company_id"]
    job_hash = entry["job_hash"]

    job_data = watcher.get_job_by_hash(company_id, job_hash)
    if not job_data:
        snapshot = entry.get("job_snapshot")
        company_name_snap = entry.get("company_name_snapshot", "")
        if snapshot:
            job_data = {"job": snapshot, "company_name": company_name_snap}
        else:
            return False, f"לא נמצאו נתוני משרה עבור queue_id={queue_id}"

    watcher.update_job_status(company_id, job_hash, Config.STATUS_APPROVED)
    target_channel_id = entry.get("target_channel_id") or context.bot_data["public_channel_id"]
    target_cfg = next((c for c in CHANNEL_CONFIGS if c.public_channel_id == target_channel_id), None)
    english_only = target_cfg.english_only if target_cfg else context.bot_data.get("english_only", False)
    try:
        await sender.send_to_public(
            context.bot,
            job_data["job"],
            job_data["company_name"],
            channel_id=target_channel_id,
            udemy_url=entry.get("udemy_url"),
            hashtags=entry.get("hashtags") or [],
            cross_promo_url=context.bot_data.get("cross_promo_url", "") if entry.get("cross_promo") else "",
            footer_message=context.bot_data.get("footer_message", "") if entry.get("footer_message") else "",
            footer_url=context.bot_data.get("footer_url", ""),
            english_only=english_only,
            donation_url=context.bot_data.get("donation_url", "") if entry.get("donation") else "",
            cta_text=entry.get("cta_text") or "",
            cta_url=entry.get("cta_url") or "",
        )
        watcher.update_job_status(company_id, job_hash, Config.STATUS_SENT)
        print(f"Sent to public: {job_data['job'].get('title')} @ {job_data['company_name']}")
        return True, None
    except Exception as e:
        print(f"Failed to send to public channel: {e}")
        watcher.update_job_status(company_id, job_hash, Config.STATUS_APPROVED)
        return False, str(e)


async def handle_donation_callback(update, context):
    query = update.callback_query
    await query.answer()

    _, queue_id = query.data.split(":", 1)
    watcher: MongoWatcher = context.bot_data["watcher"]
    entry = watcher.get_review_entry(queue_id)
    if not entry:
        return

    new_value = not entry.get("donation", False)
    watcher.set_donation(queue_id, new_value)

    entry = watcher.get_review_entry(queue_id)
    await query.edit_message_reply_markup(reply_markup=_keyboard_for_entry(entry, context.bot_data))


async def handle_cta_callback(update, context):
    query = update.callback_query
    await query.answer("שלח לי את הכפתור המותאם בפרטי 👇")

    _, queue_id = query.data.split(":", 1)
    user_id = query.from_user.id

    watcher: MongoWatcher = context.bot_data["watcher"]
    entry = watcher.get_review_entry(queue_id)
    if not entry:
        return

    context.bot_data.setdefault("awaiting_udemy", {}).pop(user_id, None)
    context.bot_data.setdefault("awaiting_hashtag", {}).pop(user_id, None)
    context.bot_data.setdefault("awaiting_cta", {})[user_id] = {
        "queue_id": queue_id,
        "review_message_id": entry.get("review_message_id"),
    }

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="שלח לי את הכפתור בפורמט: טקסט | https://link.com\nלמשל: לאתר החברה | https://example.com",
        )
    except Exception:
        await context.bot.send_message(
            chat_id=context.bot_data["review_channel_id"],
            text=f"⚠️ לא ניתן לשלוח הודעה פרטית. פתח שיחה עם הבוט קודם: https://t.me/{(await context.bot.get_me()).username}",
        )


async def handle_cta_input(update, context):
    user_id = update.effective_user.id
    awaiting = context.bot_data.get("awaiting_cta", {})

    if user_id not in awaiting:
        return

    raw = update.message.text.strip()
    if "|" not in raw:
        await update.message.reply_text("פורמט לא תקין. שלח: טקסט | https://link.com")
        return

    text_part, url_part = raw.split("|", 1)
    cta_text = text_part.strip()
    cta_url = url_part.strip()

    if not cta_text or not cta_url.startswith(("http://", "https://")):
        await update.message.reply_text("פורמט לא תקין. ודא שהקישור מתחיל ב-http:// או https://")
        return

    info = awaiting.pop(user_id)
    queue_id = info["queue_id"]
    review_message_id = info["review_message_id"]

    watcher: MongoWatcher = context.bot_data["watcher"]
    watcher.set_cta(queue_id, cta_text, cta_url)

    await update.message.reply_text(f"✅ כפתור נשמר: «{cta_text}» → {cta_url}")

    if review_message_id:
        try:
            entry = watcher.get_review_entry(queue_id)
            if entry:
                await context.bot.edit_message_reply_markup(
                    chat_id=context.bot_data["review_channel_id"],
                    message_id=review_message_id,
                    reply_markup=_keyboard_for_entry(entry, context.bot_data),
                )
        except Exception as e:
            print(f"Failed to update review message keyboard: {e}")


async def handle_udemy_callback(update, context):
    query = update.callback_query
    await query.answer("שלח לי את קישור קורס Udemy בפרטי 👇")

    _, queue_id = query.data.split(":", 1)
    user_id = query.from_user.id

    watcher: MongoWatcher = context.bot_data["watcher"]
    entry = watcher.get_review_entry(queue_id)
    if not entry:
        return

    context.bot_data.setdefault("awaiting_hashtag", {}).pop(user_id, None)
    context.bot_data.setdefault("awaiting_udemy", {})[user_id] = {
        "queue_id": queue_id,
        "review_message_id": entry.get("review_message_id"),
    }

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="שלח לי את קישור קורס Udemy עבור המשרה הזו:",
        )
    except Exception:
        await context.bot.send_message(
            chat_id=context.bot_data["review_channel_id"],
            text=f"⚠️ לא ניתן לשלוח הודעה פרטית. פתח שיחה עם הבוט קודם: https://t.me/{(await context.bot.get_me()).username}",
        )


async def handle_hashtag_callback(update, context):
    query = update.callback_query
    await query.answer("שלח לי את ההאשטאג בפרטי 👇")

    _, queue_id = query.data.split(":", 1)
    user_id = query.from_user.id

    watcher: MongoWatcher = context.bot_data["watcher"]
    entry = watcher.get_review_entry(queue_id)
    if not entry:
        return

    context.bot_data.setdefault("awaiting_udemy", {}).pop(user_id, None)
    context.bot_data.setdefault("awaiting_hashtag", {})[user_id] = {
        "queue_id": queue_id,
        "review_message_id": entry.get("review_message_id"),
    }

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="שלח לי את ההאשטאג עבור המשרה (לדוגמה: #python או python):",
        )
    except Exception:
        await context.bot.send_message(
            chat_id=context.bot_data["review_channel_id"],
            text=f"⚠️ לא ניתן לשלוח הודעה פרטית. פתח שיחה עם הבוט קודם: https://t.me/{(await context.bot.get_me()).username}",
        )


def _build_review_keyboard(queue_id: str, udemy_set: bool, hashtags: list = None, cross_promo: bool = False, cross_promo_url: str = "", footer_message: bool = False, has_footer: bool = False, english_only: bool = False, reroute_options: list = None, current_target_id: str = "", job_url: str = "", donation: bool = False, donation_url: str = "", cta_text: str = "", cta_url: str = "", scheduled_at: datetime.datetime | None = None) -> InlineKeyboardMarkup:
    if english_only:
        udemy_label = "🎓 Udemy ✅" if udemy_set else "🎓 Add Udemy Course"
    else:
        udemy_label = "🎓 Udemy ✅" if udemy_set else "🎓 הוסף קורס Udemy"
    udemy_data = "noop" if udemy_set else f"udemy:{queue_id}"

    count = len(hashtags) if hashtags else 0
    if english_only:
        hashtag_label = f"🏷️ {count} tags ✅" if count else "🏷️ Add Hashtag"
    else:
        hashtag_label = f"🏷️ {count} תגיות ✅" if count else "🏷️ הוסף האשטאג"

    view_label = "🔗 View Job" if english_only else "🔗 לצפייה במשרה"
    rows = []
    if job_url and job_url.startswith(("http://", "https://")):
        rows.append([InlineKeyboardButton(view_label, url=job_url)])
    rows.append([
        InlineKeyboardButton("✅ Approve", callback_data=f"approve:{queue_id}"),
        InlineKeyboardButton("❌ Reject",  callback_data=f"reject:{queue_id}"),
    ])
    if scheduled_at:
        local_time = _to_il_time(scheduled_at)
        schedule_label = f"🕒 Scheduled {local_time} — cancel" if english_only else f"🕒 מתוזמן לשעה {local_time} — ביטול"
        rows.append([InlineKeyboardButton(schedule_label, callback_data=f"sched_cancel:{queue_id}")])
    else:
        schedule_label = "🕒 Schedule Send" if english_only else "🕒 תזמן שליחה"
        rows.append([InlineKeyboardButton(schedule_label, callback_data=f"sched_menu:{queue_id}")])
    rows.append([
        InlineKeyboardButton(udemy_label, callback_data=udemy_data),
        InlineKeyboardButton(hashtag_label, callback_data=f"hashtag:{queue_id}"),
    ])
    if cross_promo_url:
        promo_label = ("📢 Cross Promo ✅" if cross_promo else "📢 Add Cross Promo") if english_only else ("📢 פרסום צולב ✅" if cross_promo else "📢 הוסף פרסום צולב")
        rows.append([InlineKeyboardButton(promo_label, callback_data=f"cross_promo:{queue_id}")])
    if has_footer:
        footer_label = ("📌 Footer ✅" if footer_message else "📌 Add Footer Message") if english_only else ("📌 הודעה קטנה ✅" if footer_message else "📌 הוסף הודעה קטנה")
        rows.append([InlineKeyboardButton(footer_label, callback_data=f"footer_message:{queue_id}")])
    if donation_url:
        donation_label = "💝 תרומות ✅" if donation else "💝 הוסף תרומות"
        rows.append([InlineKeyboardButton(donation_label, callback_data=f"donation:{queue_id}")])
    cta_label = (f"🔗 CTA ✅ ({cta_text})" if cta_text else ("🔗 Add CTA Button" if english_only else "🔗 הוסף כפתור מותאם"))
    rows.append([InlineKeyboardButton(cta_label, callback_data=f"cta:{queue_id}")])
    if reroute_options:
        reroute_row = []
        for name, ch_id in reroute_options:
            if ch_id == current_target_id:
                reroute_row.append(InlineKeyboardButton(f"📡 {name} ✅", callback_data="noop"))
            else:
                reroute_row.append(InlineKeyboardButton(f"📤 {name}", callback_data=f"reroute:{queue_id}:{ch_id}"))
        for i in range(0, len(reroute_row), 2):
            rows.append(reroute_row[i:i + 2])
    return InlineKeyboardMarkup(rows)


def _keyboard_for_entry(entry: dict, bot_data: dict) -> InlineKeyboardMarkup:
    """Rebuild the review keyboard from a fresh review_queue entry + this bot's static config."""
    return _build_review_keyboard(
        entry["id"],
        udemy_set=bool(entry.get("udemy_url")),
        hashtags=entry.get("hashtags") or [],
        cross_promo=entry.get("cross_promo", False),
        cross_promo_url=bot_data.get("cross_promo_url", ""),
        footer_message=entry.get("footer_message", False),
        has_footer=bool(bot_data.get("footer_message")),
        english_only=bot_data.get("english_only", False),
        reroute_options=bot_data.get("reroute_options", []),
        current_target_id=entry.get("target_channel_id") or bot_data.get("public_channel_id", ""),
        job_url=entry.get("job_snapshot", {}).get(Config.FIELD_URL, "") or "",
        donation=entry.get("donation", False),
        donation_url=bot_data.get("donation_url", ""),
        cta_text=entry.get("cta_text") or "",
        cta_url=entry.get("cta_url") or "",
        scheduled_at=entry.get("scheduled_send_at"),
    )


async def _refresh_review_keyboard(query, context, queue_id: str, entry: dict = None):
    watcher: MongoWatcher = context.bot_data["watcher"]
    entry = entry or watcher.get_review_entry(queue_id)
    if not entry:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([]))
        return
    await query.edit_message_reply_markup(reply_markup=_keyboard_for_entry(entry, context.bot_data))


async def _apply_schedule(context, queue_id: str, minutes: int) -> str:
    """Cancel any existing scheduled job for this entry and schedule a new send. Returns the local HH:MM."""
    watcher: MongoWatcher = context.bot_data["watcher"]
    _cancel_scheduled_job(context, queue_id)
    when = datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes)
    watcher.set_scheduled_send(queue_id, when)
    context.job_queue.run_once(
        _scheduled_send_job,
        when=minutes * 60,
        name=_schedule_job_name(queue_id),
        data={"queue_id": queue_id},
    )
    return _to_il_time(when)


async def _scheduled_send_job(context):
    """job_queue callback: fires when a scheduled review entry's delay elapses."""
    queue_id = context.job.data["queue_id"]
    watcher: MongoWatcher = context.bot_data["watcher"]
    entry = watcher.get_review_entry(queue_id)
    if not entry or not entry.get("scheduled_send_at"):
        return  # cancelled, or already handled manually in the meantime

    review_channel_id = context.bot_data["review_channel_id"]
    review_message_id = entry.get("review_message_id")
    ok, error = await _send_approved_job(context, queue_id, entry)

    if ok:
        watcher.remove_from_review_queue(queue_id)
        if review_message_id:
            english_only = context.bot_data.get("english_only", False)
            label = "✅ Sent (scheduled)" if english_only else "✅ נשלח (מתוזמן)"
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=review_channel_id,
                    message_id=review_message_id,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data="noop")]]),
                )
            except Exception as e:
                print(f"Failed to update review message after scheduled send: {e}")
    else:
        watcher.set_scheduled_send(queue_id, None)
        await context.bot.send_message(
            chat_id=review_channel_id,
            text=f"⚠️ שליחה מתוזמנת נכשלה עבור queue_id={queue_id}: {error}",
        )
        if review_message_id:
            try:
                entry = watcher.get_review_entry(queue_id)
                if entry:
                    await context.bot.edit_message_reply_markup(
                        chat_id=review_channel_id,
                        message_id=review_message_id,
                        reply_markup=_keyboard_for_entry(entry, context.bot_data),
                    )
            except Exception as e:
                print(f"Failed to restore review keyboard after failed scheduled send: {e}")


async def _reschedule_pending_jobs(context):
    """Startup recovery: re-register job_queue jobs for entries that were scheduled before a restart."""
    watcher: MongoWatcher = context.bot_data["watcher"]
    category: str = context.bot_data["category"]
    now = datetime.datetime.utcnow()
    entries = watcher.get_scheduled_entries(category)
    for entry in entries:
        queue_id = entry["id"]
        when = entry["scheduled_send_at"]
        delay = max((when - now).total_seconds(), 0)
        context.job_queue.run_once(
            _scheduled_send_job,
            when=delay,
            name=_schedule_job_name(queue_id),
            data={"queue_id": queue_id},
        )
    if entries:
        print(f"[SCHEDULE] Restored {len(entries)} pending scheduled send(s) for category={category}")


async def handle_schedule_menu_callback(update, context):
    query = update.callback_query
    await query.answer()
    _, queue_id = query.data.split(":", 1)

    english_only = context.bot_data.get("english_only", False)
    option_buttons = [
        InlineKeyboardButton(
            f"{m} min" if english_only else f"{m} דק׳",
            callback_data=f"sched_set:{queue_id}:{m}",
        )
        for m in _SCHEDULE_PRESETS_MINUTES
    ]
    rows = [option_buttons[i:i + 3] for i in range(0, len(option_buttons), 3)]
    custom_label = "✏️ Custom" if english_only else "✏️ מספר דקות אחר"
    back_label = "🔙 Back" if english_only else "🔙 חזרה"
    rows.append([InlineKeyboardButton(custom_label, callback_data=f"sched_custom:{queue_id}")])
    rows.append([InlineKeyboardButton(back_label, callback_data=f"sched_back:{queue_id}")])
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(rows))


async def handle_schedule_back_callback(update, context):
    query = update.callback_query
    await query.answer()
    _, queue_id = query.data.split(":", 1)
    await _refresh_review_keyboard(query, context, queue_id)


async def handle_schedule_set_callback(update, context):
    query = update.callback_query
    _, queue_id, minutes_str = query.data.split(":", 2)
    minutes = int(minutes_str)

    watcher: MongoWatcher = context.bot_data["watcher"]
    entry = watcher.get_review_entry(queue_id)
    if not entry:
        await query.answer("⚠️ הרשומה כבר לא בתור הבדיקה.", show_alert=True)
        return

    local_time = await _apply_schedule(context, queue_id, minutes)
    english_only = context.bot_data.get("english_only", False)
    await query.answer(f"Scheduled for {local_time}" if english_only else f"מתוזמן לשעה {local_time}")
    await _refresh_review_keyboard(query, context, queue_id)


async def handle_schedule_custom_callback(update, context):
    query = update.callback_query
    english_only = context.bot_data.get("english_only", False)
    await query.answer(
        "Send the number of minutes in DM 👇" if english_only else "שלח לי בפרטי מספר דקות 👇"
    )
    _, queue_id = query.data.split(":", 1)
    user_id = query.from_user.id

    watcher: MongoWatcher = context.bot_data["watcher"]
    entry = watcher.get_review_entry(queue_id)
    if not entry:
        return

    context.bot_data.setdefault("awaiting_udemy", {}).pop(user_id, None)
    context.bot_data.setdefault("awaiting_hashtag", {}).pop(user_id, None)
    context.bot_data.setdefault("awaiting_cta", {}).pop(user_id, None)
    context.bot_data.setdefault("awaiting_schedule", {})[user_id] = {
        "queue_id": queue_id,
        "review_message_id": entry.get("review_message_id"),
    }

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"In how many minutes should I send it? Send a number (1-{_SCHEDULE_MAX_MINUTES}):"
                if english_only else
                f"בעוד כמה דקות לשלוח? שלח מספר (1-{_SCHEDULE_MAX_MINUTES}):"
            ),
        )
    except Exception:
        await context.bot.send_message(
            chat_id=context.bot_data["review_channel_id"],
            text=f"⚠️ לא ניתן לשלוח הודעה פרטית. פתח שיחה עם הבוט קודם: https://t.me/{(await context.bot.get_me()).username}",
        )


async def handle_schedule_input(update, context):
    user_id = update.effective_user.id
    awaiting = context.bot_data.get("awaiting_schedule", {})
    if user_id not in awaiting:
        return

    raw = update.message.text.strip()
    if not raw.isdigit() or not (1 <= int(raw) <= _SCHEDULE_MAX_MINUTES):
        await update.message.reply_text(f"מספר לא תקין. שלח מספר דקות בין 1 ל-{_SCHEDULE_MAX_MINUTES}.")
        return
    minutes = int(raw)

    info = awaiting.pop(user_id)
    queue_id = info["queue_id"]
    review_message_id = info["review_message_id"]

    watcher: MongoWatcher = context.bot_data["watcher"]
    entry = watcher.get_review_entry(queue_id)
    if not entry:
        await update.message.reply_text("⚠️ הרשומה כבר לא בתור הבדיקה.")
        return

    local_time = await _apply_schedule(context, queue_id, minutes)
    await update.message.reply_text(f"✅ תוזמן לשעה {local_time}")

    if review_message_id:
        try:
            entry = watcher.get_review_entry(queue_id)
            if entry:
                await context.bot.edit_message_reply_markup(
                    chat_id=context.bot_data["review_channel_id"],
                    message_id=review_message_id,
                    reply_markup=_keyboard_for_entry(entry, context.bot_data),
                )
        except Exception as e:
            print(f"Failed to update review message keyboard: {e}")


async def handle_schedule_cancel_callback(update, context):
    query = update.callback_query
    _, queue_id = query.data.split(":", 1)

    watcher: MongoWatcher = context.bot_data["watcher"]
    _cancel_scheduled_job(context, queue_id)
    watcher.set_scheduled_send(queue_id, None)

    english_only = context.bot_data.get("english_only", False)
    await query.answer("Schedule cancelled" if english_only else "התזמון בוטל")
    await _refresh_review_keyboard(query, context, queue_id)


async def handle_reroute_callback(update, context):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":", 2)
    if len(parts) != 3:
        return
    _, queue_id, new_channel_id = parts

    watcher: MongoWatcher = context.bot_data["watcher"]
    sender: TelegramSender = context.bot_data["sender"]
    watcher.set_target_channel(queue_id, new_channel_id)

    entry = watcher.get_review_entry(queue_id)
    if not entry:
        return

    reroute_options = context.bot_data.get("reroute_options", [])
    target_cfg = next((c for c in CHANNEL_CONFIGS if c.public_channel_id == new_channel_id), None)
    english_only = target_cfg.english_only if target_cfg else context.bot_data.get("english_only", False)
    new_name = next((name for name, ch_id in reroute_options if ch_id == new_channel_id), new_channel_id)

    job = entry.get("job_snapshot", {})
    company_name = entry.get("company_name_snapshot", "")
    hashtags = entry.get("hashtags") or []

    text = sender.format_message(job, company_name, hashtags=hashtags, english_only=english_only)
    text = f"📡 <b>{new_name}</b>\n\n{text}"

    keyboard = _build_review_keyboard(
        queue_id,
        udemy_set=bool(entry.get("udemy_url")),
        hashtags=hashtags,
        cross_promo=entry.get("cross_promo", False),
        cross_promo_url=context.bot_data.get("cross_promo_url", ""),
        footer_message=entry.get("footer_message", False),
        has_footer=bool(context.bot_data.get("footer_message")),
        english_only=english_only,
        reroute_options=reroute_options,
        current_target_id=new_channel_id,
        job_url=job.get(Config.FIELD_URL, "") or "",
        donation=entry.get("donation", False),
        donation_url=context.bot_data.get("donation_url", ""),
        cta_text=entry.get("cta_text") or "",
        cta_url=entry.get("cta_url") or "",
        scheduled_at=entry.get("scheduled_send_at"),
    )
    await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=keyboard)


async def handle_cross_promo_callback(update, context):
    query = update.callback_query
    await query.answer()

    _, queue_id = query.data.split(":", 1)
    watcher: MongoWatcher = context.bot_data["watcher"]
    entry = watcher.get_review_entry(queue_id)
    if not entry:
        return

    new_value = not entry.get("cross_promo", False)
    watcher.set_cross_promo(queue_id, new_value)

    entry = watcher.get_review_entry(queue_id)
    await query.edit_message_reply_markup(reply_markup=_keyboard_for_entry(entry, context.bot_data))


async def handle_footer_message_callback(update, context):
    query = update.callback_query
    await query.answer()

    _, queue_id = query.data.split(":", 1)
    watcher: MongoWatcher = context.bot_data["watcher"]
    entry = watcher.get_review_entry(queue_id)
    if not entry:
        return

    new_value = not entry.get("footer_message", False)
    watcher.set_footer_message(queue_id, new_value)

    entry = watcher.get_review_entry(queue_id)
    await query.edit_message_reply_markup(reply_markup=_keyboard_for_entry(entry, context.bot_data))


async def handle_udemy_input(update, context):
    user_id = update.effective_user.id
    awaiting = context.bot_data.get("awaiting_udemy", {})

    if user_id not in awaiting:
        return

    url = update.message.text.strip()
    if "udemy.com" not in url:
        await update.message.reply_text("נראה שזה לא קישור Udemy תקין. נסה שוב.")
        return

    info = awaiting.pop(user_id)
    queue_id = info["queue_id"]
    review_message_id = info["review_message_id"]

    watcher: MongoWatcher = context.bot_data["watcher"]
    watcher.set_udemy_url(queue_id, url)

    await update.message.reply_text("✅ קישור Udemy נשמר! יצורף להודעה בערוץ הציבורי בעת האישור.")

    if review_message_id:
        try:
            entry = watcher.get_review_entry(queue_id)
            if entry:
                await context.bot.edit_message_reply_markup(
                    chat_id=context.bot_data["review_channel_id"],
                    message_id=review_message_id,
                    reply_markup=_keyboard_for_entry(entry, context.bot_data),
                )
        except Exception as e:
            print(f"Failed to update review message keyboard: {e}")


async def handle_hashtag_input(update, context):
    user_id = update.effective_user.id
    awaiting = context.bot_data.get("awaiting_hashtag", {})

    if user_id not in awaiting:
        return

    raw = update.message.text.strip()
    hashtag = raw.lstrip("#").strip()
    if not hashtag:
        await update.message.reply_text("האשטאג לא תקין. נסה שוב.")
        return

    info = awaiting.pop(user_id)
    queue_id = info["queue_id"]
    review_message_id = info["review_message_id"]

    watcher: MongoWatcher = context.bot_data["watcher"]
    watcher.add_hashtag(queue_id, hashtag)

    await update.message.reply_text(f"✅ האשטאג #{hashtag} נשמר! ניתן להוסיף עוד תגיות או לאשר את המשרה.")

    if review_message_id:
        try:
            entry = watcher.get_review_entry(queue_id)
            if entry:
                await context.bot.edit_message_reply_markup(
                    chat_id=context.bot_data["review_channel_id"],
                    message_id=review_message_id,
                    reply_markup=_keyboard_for_entry(entry, context.bot_data),
                )
        except Exception as e:
            print(f"Failed to update review message keyboard: {e}")


_URL_PATTERN = re.compile(r"https?://\S+|www\.\S+|\b[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?(?:/\S*)?\b")


async def handle_company_suggestion(update, context):
    """Forward a company name/URL suggestion to the review channel."""
    user = update.effective_user
    text = update.message.text.strip()
    sender_info = f"@{user.username}" if user.username else f"{user.full_name} (id: {user.id})"
    reply_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 השב למציע", callback_data=f"reply_suggestion:{user.id}")
    ]])

    if not _URL_PATTERN.search(text):
        await context.bot.send_message(
            chat_id=context.bot_data["review_channel_id"],
            text=f"⚠️ הצעת חברה ללא קישור מ-{sender_info}:\n\n{text}",
            reply_markup=reply_keyboard,
        )
        await update.message.reply_text("⚠️ לא צורף קישור לאתר חברה. אנא שלח/י הודעה הכוללת קישור.")
        return

    await context.bot.send_message(
        chat_id=context.bot_data["review_channel_id"],
        text=f"💡 הצעת חברה חדשה מ-{sender_info}:\n\n{text}",
        reply_markup=reply_keyboard,
    )
    await update.message.reply_text("✅ תודה! ההצעה נשלחה לבדיקה.")


async def handle_reply_suggestion_callback(update, context):
    query = update.callback_query
    await query.answer("שלח לי את התגובה שלך בפרטי 👇")

    _, target_user_id = query.data.split(":", 1)
    admin_id = query.from_user.id

    context.bot_data.setdefault("awaiting_reply", {})[admin_id] = {"target_user_id": int(target_user_id)}

    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text="שלח לי את ההודעה שתועבר למציע:",
        )
    except Exception:
        await context.bot.send_message(
            chat_id=context.bot_data["review_channel_id"],
            text=f"⚠️ לא ניתן לשלוח הודעה פרטית. פתח שיחה עם הבוט קודם: https://t.me/{(await context.bot.get_me()).username}",
        )


async def handle_reply_input(update, context):
    admin_id = update.effective_user.id
    awaiting = context.bot_data.get("awaiting_reply", {})
    if admin_id not in awaiting:
        return

    target_user_id = awaiting.pop(admin_id)["target_user_id"]
    text = update.message.text.strip()

    try:
        await context.bot.send_message(chat_id=target_user_id, text=text)
        await update.message.reply_text("✅ ההודעה נשלחה למציע.")
        context.bot_data.setdefault("contacted_users", set()).add(target_user_id)
    except Exception as e:
        await update.message.reply_text(f"⚠️ שליחת ההודעה נכשלה: {e}")


async def handle_followup_message(update, context):
    """Forward a follow-up reply from a user who was already contacted by an admin."""
    user = update.effective_user
    text = update.message.text.strip()
    sender_info = f"@{user.username}" if user.username else f"{user.full_name} (id: {user.id})"
    reply_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 השב", callback_data=f"reply_suggestion:{user.id}")
    ]])
    await context.bot.send_message(
        chat_id=context.bot_data["review_channel_id"],
        text=f"💬 תגובה חוזרת מ-{sender_info}:\n\n{text}",
        reply_markup=reply_keyboard,
    )
    await update.message.reply_text("✅ הודעתך הועברה.")


async def handle_private_message(update, context):
    user_id = update.effective_user.id
    if user_id in context.bot_data.get("awaiting_udemy", {}):
        await handle_udemy_input(update, context)
    elif user_id in context.bot_data.get("awaiting_hashtag", {}):
        await handle_hashtag_input(update, context)
    elif user_id in context.bot_data.get("awaiting_cta", {}):
        await handle_cta_input(update, context)
    elif user_id in context.bot_data.get("awaiting_schedule", {}):
        await handle_schedule_input(update, context)
    elif user_id in context.bot_data.get("awaiting_reply", {}):
        await handle_reply_input(update, context)
    elif user_id in context.bot_data.get("contacted_users", set()):
        await handle_followup_message(update, context)
    else:
        await handle_company_suggestion(update, context)


async def handle_autoapprove_command(update, context):
    if not context.args:
        await update.message.reply_text("שימוש: /autoapprove <שם החברה>")
        return
    company_name = " ".join(context.args).strip()
    watcher: MongoWatcher = context.bot_data["watcher"]
    watcher.add_auto_approve_company(company_name)
    await update.message.reply_text(f"✅ החברה '{company_name}' נוספה לרשימת האישור האוטומטי.")


async def handle_removeautoapprove_command(update, context):
    if not context.args:
        await update.message.reply_text("שימוש: /removeautoapprove <שם החברה>")
        return
    company_name = " ".join(context.args).strip()
    watcher: MongoWatcher = context.bot_data["watcher"]
    removed = watcher.remove_auto_approve_company(company_name)
    if removed:
        await update.message.reply_text(f"✅ החברה '{company_name}' הוסרה מרשימת האישור האוטומטי.")
    else:
        await update.message.reply_text(f"⚠️ החברה '{company_name}' לא נמצאה ברשימת האישור האוטומטי.")


async def handle_listautoapprove_command(update, context):
    watcher: MongoWatcher = context.bot_data["watcher"]
    companies = watcher.get_auto_approve_companies()
    if not companies:
        await update.message.reply_text("📋 רשימת האישור האוטומטי ריקה.")
        return
    lines = "\n".join(f"• {c}" for c in sorted(companies))
    await update.message.reply_text(f"📋 חברות באישור אוטומטי ({len(companies)}):\n\n{lines}")


def _build_app(token: str, watcher: MongoWatcher, sender: TelegramSender,
               category: str, review_channel_id: str, public_channel_id: str,
               cross_promo_url: str = "", footer_message: str = "", footer_url: str = "", enable_expiry: bool = False, english_only: bool = False, channel_label: str = "", reroute_options: list = None, donation_url: str = "") -> Application:
    app = Application.builder().token(token).build()
    app.bot_data["watcher"] = watcher
    app.bot_data["sender"] = sender
    app.bot_data["category"] = category
    app.bot_data["review_channel_id"] = review_channel_id
    app.bot_data["public_channel_id"] = public_channel_id
    app.bot_data["cross_promo_url"] = cross_promo_url
    app.bot_data["footer_message"] = footer_message
    app.bot_data["footer_url"] = footer_url
    app.bot_data["english_only"] = english_only
    app.bot_data["channel_label"] = channel_label
    app.bot_data["reroute_options"] = reroute_options or []
    app.bot_data["donation_url"] = donation_url

    app.add_handler(CommandHandler("autoapprove", handle_autoapprove_command))
    app.add_handler(CommandHandler("removeautoapprove", handle_removeautoapprove_command))
    app.add_handler(CommandHandler("listautoapprove", handle_listautoapprove_command))
    app.add_handler(CallbackQueryHandler(handle_cta_callback, pattern="^cta:"))
    app.add_handler(CallbackQueryHandler(handle_udemy_callback, pattern="^udemy:"))
    app.add_handler(CallbackQueryHandler(handle_hashtag_callback, pattern="^hashtag:"))
    app.add_handler(CallbackQueryHandler(handle_cross_promo_callback, pattern="^cross_promo:"))
    app.add_handler(CallbackQueryHandler(handle_footer_message_callback, pattern="^footer_message:"))
    app.add_handler(CallbackQueryHandler(handle_donation_callback, pattern="^donation:"))
    app.add_handler(CallbackQueryHandler(handle_reroute_callback, pattern="^reroute:"))
    app.add_handler(CallbackQueryHandler(handle_reply_suggestion_callback, pattern="^reply_suggestion:"))
    app.add_handler(CallbackQueryHandler(handle_schedule_menu_callback, pattern="^sched_menu:"))
    app.add_handler(CallbackQueryHandler(handle_schedule_back_callback, pattern="^sched_back:"))
    app.add_handler(CallbackQueryHandler(handle_schedule_set_callback, pattern="^sched_set:"))
    app.add_handler(CallbackQueryHandler(handle_schedule_custom_callback, pattern="^sched_custom:"))
    app.add_handler(CallbackQueryHandler(handle_schedule_cancel_callback, pattern="^sched_cancel:"))
    app.add_handler(CallbackQueryHandler(handle_approval))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, handle_private_message))
    app.job_queue.run_repeating(poll_jobs, interval=Config.POLL_INTERVAL, first=5)
    app.job_queue.run_once(_reschedule_pending_jobs, when=2)
    if enable_expiry:
        app.job_queue.run_repeating(expire_stale_queue, interval=86400, first=86400)
        app.job_queue.run_daily(
            notify_zero_result_companies,
            time=datetime.time(20, 0, 0, tzinfo=_IL_TZ),
        )

    return app


async def _run(watcher: MongoWatcher):
    sender = TelegramSender()

    apps = [
        _build_app(
            cfg.bot_token, watcher, sender,
            category=cfg.category,
            review_channel_id=cfg.review_channel_id,
            public_channel_id=cfg.public_channel_id,
            cross_promo_url=cfg.cross_promo_url,
            footer_message=cfg.footer_message,
            footer_url=cfg.footer_url,
            enable_expiry=cfg.enable_expiry,
            english_only=cfg.english_only,
            channel_label=cfg.name,
            reroute_options=[
                (other.name, other.public_channel_id)
                for other in CHANNEL_CONFIGS
                if other.public_channel_id != cfg.public_channel_id
            ],
            donation_url=cfg.donation_url,
        )
        for cfg in CHANNEL_CONFIGS
    ]

    if not apps:
        print("No bots configured. Check your .env file.")
        return

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    allowed = ["message", "callback_query"]

    async with contextlib.AsyncExitStack() as stack:
        for app in apps:
            await stack.enter_async_context(app)

        for app in apps:
            await app.updater.start_polling(allowed_updates=allowed)
            await app.start()

        names = ", ".join(cfg.name for cfg in CHANNEL_CONFIGS)
        print(f"{len(apps)} bot(s) started [{names}]. Polling every {Config.POLL_INTERVAL}s...")
        await stop_event.wait()

        for app in reversed(apps):
            await app.updater.stop()
            await app.stop()


def main():
    try:
        Config.validate()
    except ValueError as e:
        print(f"Configuration error: {e}")
        return

    watcher = MongoWatcher()
    try:
        asyncio.run(_run(watcher))
    finally:
        watcher.close()


if __name__ == "__main__":
    main()
