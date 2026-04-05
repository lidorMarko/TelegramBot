import logging
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
    """Periodic task: pick up new PENDING_REVIEW jobs and send them to the review group."""
    watcher: JsonWatcher = context.bot_data["watcher"]
    await watcher.process_pending_jobs(context.bot)


async def handle_approval(update, context):
    """Handle Approve / Reject button clicks from the review group."""
    query = update.callback_query

    # Ignore any stale/unknown callbacks (e.g. already-processed buttons)
    if not query.data or not query.data.startswith(("approve:", "reject:")):
        await query.answer()
        return

    await query.answer()

    action, queue_id = query.data.split(":", 1)
    watcher: JsonWatcher = context.bot_data["watcher"]
    sender: TelegramSender = context.bot_data["sender"]

    entry = watcher.get_review_entry(queue_id)
    if not entry:
        # Already processed (e.g. double-click)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([]))
        return

    company_id = entry["company_id"]
    job_hash = entry["job_hash"]

    if action == "approve":
        job_data = watcher.get_job_by_hash(company_id, job_hash)
        if job_data:
            watcher.update_job_status(company_id, job_hash, Config.STATUS_APPROVED)
            try:
                udemy_url = entry.get("udemy_url")
                await sender.send_to_public(context.bot, job_data["job"], job_data["company_name"], udemy_url=udemy_url)
                watcher.update_job_status(company_id, job_hash, Config.STATUS_SENT)
                print(f"Sent to public: {job_data['job'].get('title')} @ {job_data['company_name']}")
            except Exception as e:
                print(f"Failed to send to public channel: {e}")

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
    """Handle the 'Add Udemy Link' button click — DM the reviewer asking for the URL."""
    query = update.callback_query
    await query.answer("שלח לי את קישור קורס Udemy בפרטי 👇")

    _, queue_id = query.data.split(":", 1)
    user_id = query.from_user.id

    watcher: JsonWatcher = context.bot_data["watcher"]
    entry = watcher.get_review_entry(queue_id)
    if not entry:
        return

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
            chat_id=Config.REVIEW_CHANNEL_ID,
            text=f"⚠️ לא ניתן לשלוח הודעה פרטית. פתח שיחה עם הבוט קודם: https://t.me/{(await context.bot.get_me()).username}",
        )


async def handle_udemy_input(update, context):
    """Handle the Udemy URL sent by the reviewer in private chat."""
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
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve:{queue_id}"),
                    InlineKeyboardButton("❌ Reject",  callback_data=f"reject:{queue_id}"),
                ],
                [
                    InlineKeyboardButton("🎓 Udemy ✅", callback_data="noop"),
                ],
            ])
            await context.bot.edit_message_reply_markup(
                chat_id=Config.REVIEW_CHANNEL_ID,
                message_id=review_message_id,
                reply_markup=keyboard,
            )
        except Exception as e:
            print(f"Failed to update review message keyboard: {e}")


def main():
    try:
        Config.validate()
    except ValueError as e:
        print(f"Configuration error: {e}")
        return

    app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

    watcher = JsonWatcher()
    app.bot_data["watcher"] = watcher
    app.bot_data["sender"] = TelegramSender()

    app.add_handler(CallbackQueryHandler(handle_udemy_callback, pattern="^udemy:"))
    app.add_handler(CallbackQueryHandler(handle_approval))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, handle_udemy_input))
    app.job_queue.run_repeating(poll_jobs, interval=Config.POLL_INTERVAL, first=5)

    print(f"Bot started. Polling every {Config.POLL_INTERVAL}s for new jobs...")
    try:
        app.run_polling()
    finally:
        watcher.close()


if __name__ == "__main__":
    main()
