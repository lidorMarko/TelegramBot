import time
from datetime import datetime, timedelta
from pymongo import MongoClient
from config import Config
from telegram_sender import TelegramSender


class MongoWatcher:
    def __init__(self):
        self.client = MongoClient(Config.MONGO_URI)
        self.db = self.client[Config.MONGO_DATABASE]
        self.collection = self.db[Config.MONGO_COLLECTION]
        self.telegram = TelegramSender()

    def is_recent_job(self, job: dict) -> bool:
        first_seen = job.get(Config.FIELD_FIRST_SEEN)
        if not first_seen:
            return True

        if isinstance(first_seen, datetime):
            cutoff = datetime.utcnow() - timedelta(hours=24)
            return first_seen >= cutoff

        return True

    def get_unposted_jobs(self):
        """Find all companies with unposted jobs and return them."""
        pipeline = [
            {"$match": {f"{Config.FIELD_LATEST_JOBS}.{Config.FIELD_POSTED}": False}},
            {"$project": {
                Config.FIELD_COMPANY_NAME: 1,
                "url": 1,
                Config.FIELD_LATEST_JOBS: {
                    "$filter": {
                        "input": f"${Config.FIELD_LATEST_JOBS}",
                        "as": "job",
                        "cond": {"$eq": [f"$$job.{Config.FIELD_POSTED}", False]}
                    }
                }
            }}
        ]
        return list(self.collection.aggregate(pipeline))

    def mark_job_as_posted(self, company_id, job_hash: str):
        """Mark a specific job as posted in the database."""
        self.collection.update_one(
            {
                "_id": company_id,
                f"{Config.FIELD_LATEST_JOBS}.{Config.FIELD_JOB_HASH}": job_hash
            },
            {
                "$set": {f"{Config.FIELD_LATEST_JOBS}.$.{Config.FIELD_POSTED}": True}
            }
        )

    def process_unposted_jobs(self):
        """Process all unposted jobs and send them to Telegram."""
        companies = self.get_unposted_jobs()
        jobs_processed = 0

        for company in companies:
            company_name = company.get(Config.FIELD_COMPANY_NAME, "Unknown")
            company_id = company.get("_id")
            jobs = company.get(Config.FIELD_LATEST_JOBS, [])

            for job in jobs:
                if not self.is_recent_job(job):
                    job_hash = job.get(Config.FIELD_JOB_HASH)
                    if job_hash:
                        self.mark_job_as_posted(company_id, job_hash)
                    continue

                title = job.get(Config.FIELD_TITLE, "Unknown")
                job_hash = job.get(Config.FIELD_JOB_HASH)

                try:
                    self.telegram.send_message(job, company_name)
                    print(f"Sent: {title} @ {company_name}")

                    if job_hash:
                        self.mark_job_as_posted(company_id, job_hash)

                    jobs_processed += 1
                except Exception as e:
                    print(f"Failed to send '{title}': {e}")

        return jobs_processed

    def watch(self):
        """Poll for unposted jobs at regular intervals."""
        print(f"Watching collection '{Config.MONGO_COLLECTION}' for unposted jobs...")
        print(f"Poll interval: {Config.POLL_INTERVAL} seconds")
        print("Press Ctrl+C to stop.\n")

        # Process any existing unposted jobs immediately
        count = self.process_unposted_jobs()
        if count > 0:
            print(f"Processed {count} existing unposted job(s)\n")

        while True:
            time.sleep(Config.POLL_INTERVAL)
            count = self.process_unposted_jobs()
            if count > 0:
                print(f"Processed {count} new job(s)")

    def close(self):
        self.client.close()
