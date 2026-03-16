import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler
from config import Config
from mongo_watcher import MongoWatcher
from telegram_sender import TelegramSender

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


async def poll_jobs(context):
    """Periodic task: pick up new PENDING_REVIEW jobs and send them to the review group."""
    watcher: MongoWatcher = context.bot_data["watcher"]
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
    watcher: MongoWatcher = context.bot_data["watcher"]
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
                await sender.send_to_public(context.bot, job_data["job"], job_data["company_name"])
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


def main():
    try:
        Config.validate()
    except ValueError as e:
        print(f"Configuration error: {e}")
        return

    app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

    watcher = MongoWatcher()
    app.bot_data["watcher"] = watcher
    app.bot_data["sender"] = TelegramSender()

    app.add_handler(CallbackQueryHandler(handle_approval))
    app.job_queue.run_repeating(poll_jobs, interval=Config.POLL_INTERVAL, first=5)

    print(f"Bot started. Polling every {Config.POLL_INTERVAL}s for new jobs...")
    try:
        app.run_polling()
    finally:
        watcher.close()


if __name__ == "__main__":
    main()
