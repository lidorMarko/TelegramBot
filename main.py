import asyncio
import logging
import signal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters
from config import Config
from json_watcher import JsonWatcher
from telegram_sender import TelegramSender

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


async def poll_jobs(context):
    watcher: JsonWatcher = context.bot_data["watcher"]
    category: str = context.bot_data["category"]
    review_channel_id: str = context.bot_data["review_channel_id"]
    await watcher.process_pending_jobs(context.bot, category=category, review_channel_id=review_channel_id)


async def handle_approval(update, context):
    query = update.callback_query

    if not query.data or not query.data.startswith(("approve:", "reject:")):
        await query.answer()
        return

    await query.answer()

    action, queue_id = query.data.split(":", 1)
    watcher: JsonWatcher = context.bot_data["watcher"]
    sender: TelegramSender = context.bot_data["sender"]

    entry = watcher.get_review_entry(queue_id)
    if not entry:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([]))
        return

    company_id = entry["company_id"]
    job_hash = entry["job_hash"]

    if action == "approve":
        job_data = watcher.get_job_by_hash(company_id, job_hash)
        if not job_data:
            await context.bot.send_message(
                chat_id=context.bot_data["review_channel_id"],
                text=f"⚠️ לא נמצאו נתוני משרה עבור queue_id={queue_id}",
            )
            return

        watcher.update_job_status(company_id, job_hash, Config.STATUS_APPROVED)
        try:
            await sender.send_to_public(
                context.bot,
                job_data["job"],
                job_data["company_name"],
                channel_id=context.bot_data["public_channel_id"],
                udemy_url=entry.get("udemy_url"),
                hashtags=entry.get("hashtags") or [],
            )
            watcher.update_job_status(company_id, job_hash, Config.STATUS_SENT)
            print(f"Sent to public: {job_data['job'].get('title')} @ {job_data['company_name']}")
        except Exception as e:
            print(f"Failed to send to public channel: {e}")
            await context.bot.send_message(
                chat_id=context.bot_data["review_channel_id"],
                text=f"⚠️ שליחה לערוץ הציבורי נכשלה: {e}",
            )
            watcher.update_job_status(company_id, job_hash, Config.STATUS_APPROVED)
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


async def handle_udemy_callback(update, context):
    query = update.callback_query
    await query.answer("שלח לי את קישור קורס Udemy בפרטי 👇")

    _, queue_id = query.data.split(":", 1)
    user_id = query.from_user.id

    watcher: JsonWatcher = context.bot_data["watcher"]
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

    watcher: JsonWatcher = context.bot_data["watcher"]
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


def _build_review_keyboard(queue_id: str, udemy_set: bool, hashtags: list = None) -> InlineKeyboardMarkup:
    udemy_label = "🎓 Udemy ✅" if udemy_set else "🎓 הוסף קורס Udemy"
    udemy_data = "noop" if udemy_set else f"udemy:{queue_id}"

    count = len(hashtags) if hashtags else 0
    hashtag_label = f"🏷️ {count} תגיות ✅" if count else "🏷️ הוסף האשטאג"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{queue_id}"),
            InlineKeyboardButton("❌ Reject",  callback_data=f"reject:{queue_id}"),
        ],
        [
            InlineKeyboardButton(udemy_label, callback_data=udemy_data),
            InlineKeyboardButton(hashtag_label, callback_data=f"hashtag:{queue_id}"),
        ],
    ])


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

    watcher: JsonWatcher = context.bot_data["watcher"]
    watcher.set_udemy_url(queue_id, url)

    await update.message.reply_text("✅ קישור Udemy נשמר! יצורף להודעה בערוץ הציבורי בעת האישור.")

    if review_message_id:
        try:
            entry = watcher.get_review_entry(queue_id)
            keyboard = _build_review_keyboard(
                queue_id,
                udemy_set=True,
                hashtags=entry.get("hashtags") if entry else [],
            )
            await context.bot.edit_message_reply_markup(
                chat_id=context.bot_data["review_channel_id"],
                message_id=review_message_id,
                reply_markup=keyboard,
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

    watcher: JsonWatcher = context.bot_data["watcher"]
    watcher.add_hashtag(queue_id, hashtag)

    await update.message.reply_text(f"✅ האשטאג #{hashtag} נשמר! ניתן להוסיף עוד תגיות או לאשר את המשרה.")

    if review_message_id:
        try:
            entry = watcher.get_review_entry(queue_id)
            keyboard = _build_review_keyboard(
                queue_id,
                udemy_set=bool(entry and entry.get("udemy_url")),
                hashtags=entry.get("hashtags") if entry else [],
            )
            await context.bot.edit_message_reply_markup(
                chat_id=context.bot_data["review_channel_id"],
                message_id=review_message_id,
                reply_markup=keyboard,
            )
        except Exception as e:
            print(f"Failed to update review message keyboard: {e}")


async def handle_private_message(update, context):
    user_id = update.effective_user.id
    if user_id in context.bot_data.get("awaiting_udemy", {}):
        await handle_udemy_input(update, context)
    elif user_id in context.bot_data.get("awaiting_hashtag", {}):
        await handle_hashtag_input(update, context)


def _build_app(token: str, watcher: JsonWatcher, sender: TelegramSender,
               category: str, review_channel_id: str, public_channel_id: str) -> Application:
    app = Application.builder().token(token).build()
    app.bot_data["watcher"] = watcher
    app.bot_data["sender"] = sender
    app.bot_data["category"] = category
    app.bot_data["review_channel_id"] = review_channel_id
    app.bot_data["public_channel_id"] = public_channel_id

    app.add_handler(CallbackQueryHandler(handle_udemy_callback, pattern="^udemy:"))
    app.add_handler(CallbackQueryHandler(handle_hashtag_callback, pattern="^hashtag:"))
    app.add_handler(CallbackQueryHandler(handle_approval))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, handle_private_message))
    app.job_queue.run_repeating(poll_jobs, interval=Config.POLL_INTERVAL, first=5)

    return app


async def _run(watcher: JsonWatcher):
    sender = TelegramSender()

    cs_app = _build_app(
        Config.TELEGRAM_BOT_TOKEN, watcher, sender,
        category="cs",
        review_channel_id=Config.REVIEW_CHANNEL_ID,
        public_channel_id=Config.TELEGRAM_PROD_CHANNEL_ID,
    )
    elec_app = _build_app(
        Config.TELEGRAM_ELECTRONICS_BOT_TOKEN, watcher, sender,
        category="electronics",
        review_channel_id=Config.TELEGRAM_ELECTRONICS_REVIEW_CHANNEL_ID,
        public_channel_id=Config.TELEGRAM_ELECTRONICS_CHANNEL_ID,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    async with cs_app, elec_app:
        await cs_app.updater.start_polling()
        await elec_app.updater.start_polling()
        await cs_app.start()
        await elec_app.start()

        print(f"Both bots started. Polling every {Config.POLL_INTERVAL}s for new jobs...")
        await stop_event.wait()

        await cs_app.updater.stop()
        await elec_app.updater.stop()
        await cs_app.stop()
        await elec_app.stop()


def main():
    try:
        Config.validate()
    except ValueError as e:
        print(f"Configuration error: {e}")
        return

    watcher = JsonWatcher()
    try:
        asyncio.run(_run(watcher))
    finally:
        watcher.close()


if __name__ == "__main__":
    main()
