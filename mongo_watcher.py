from datetime import datetime
from bson import ObjectId
from pymongo import MongoClient
from config import Config


class MongoWatcher:
    def __init__(self):
        self.client = MongoClient(Config.MONGO_URI)
        self.db = self.client[Config.MONGO_DATABASE]
        self.collection = self.db[Config.MONGO_COLLECTION]
        self.review_queue = self.db["review_queue"]

    CS_KEYWORDS = {
        # Core engineering roles
        "software", "software engineer", "software developer",
        "developer", "engineer", "engineering", "programmer", "coding",

        # Web development
        "backend", "back-end",
        "frontend", "front-end",
        "fullstack", "full-stack", "full stack",
        "web developer", "web engineer",

        # Mobile
        "mobile developer", "android", "android developer",
        "ios", "ios developer", "react native", "flutter",

        # DevOps / infrastructure
        "devops", "devsecops", "sre", "site reliability",
        "platform engineer", "platform",
        "cloud", "cloud engineer",
        "infrastructure", "infra engineer",
        "kubernetes", "k8s", "docker",
        "terraform", "ansible",

        # Data
        "data engineer", "data scientist", "data analyst",
        "analytics engineer", "big data",
        "etl", "data pipeline",

        # AI / ML
        "machine learning", "ml engineer",
        "ai engineer", "artificial intelligence",
        "deep learning", "nlp", "computer vision",
        "llm", "generative ai",

        # Security
        "security engineer", "security researcher",
        "application security", "appsec",
        "pentester", "penetration tester",
        "cybersecurity", "cyber security",

        # QA / testing
        "qa engineer", "qa automation",
        "automation engineer", "test engineer",
        "quality assurance", "test automation",

        # Hardware / low level
        "embedded", "embedded engineer",
        "firmware", "firmware engineer",
        "hardware engineer",
        "fpga", "vlsi", "rtl",

        # Networking
        "network engineer", "network architect",
        "network security",

        # Architecture / leadership
        "solution architect", "software architect",
        "tech lead", "technical lead",
        "principal engineer", "staff engineer",

        # Research
        "r&d", "research engineer",
        "research scientist",
        "computer science",

        # Common programming languages
        "python", "java", "c++", "c#", "golang", "go",
        "typescript", "javascript", "node", "nodejs",
        "react", "angular", "vue",

        # Hebrew
        "מפתח", "מפתחת", "מהנדס", "מהנדסת",
        "תוכנה", "פיתוח", "פיתוח תוכנה",
        "איש פיתוח", "devops", "ענן",
        "אבטחת מידע", "סייבר",
        "בדיקות", "בדיקות תוכנה",
        "אוטומציה", "בדיקות אוטומציה",
        "דאטה", "נתונים",
        "למידת מכונה", "בינה מלאכותית"
    }

    ISRAEL_TERMS = {
        "israel", "tel aviv", "tel-aviv", "haifa", "jerusalem", "raanana", "ra'anana",
        "herzliya", "beer sheva", "be'er sheva", "beersheba", "netanya", "petah tikva",
        "petach tikva", "rehovot", "rishon lezion", "rishon le-zion", "kfar saba",
        "rosh haayin", "hod hasharon", "givatayim", "bnei brak", "ashdod", "ashkelon",
        "modiin", "caesarea", "yokneam", "nahariya", "karmiel", "holon",
        "bat yam", "lod", "ramla", "eilat", "nazareth", "afula", "tiberias",
    }
    REMOTE_TERMS = {"remote", "hybrid", "work from home", "wfh"}

    # ── Filters ──────────────────────────────────────────────────────────────

    def is_cs_job(self, job: dict) -> bool:
        title = (job.get(Config.FIELD_TITLE, "") or "").lower()
        return any(kw in title for kw in self.CS_KEYWORDS)

    def is_israel_or_remote(self, job: dict) -> bool:
        location = job.get(Config.FIELD_LOCATION, "") or ""
        if not location.strip():
            return True  # no location → assume Israel
        loc = location.lower()
        return any(t in loc for t in self.REMOTE_TERMS) or any(t in loc for t in self.ISRAEL_TERMS)

    # ── MongoDB helpers ───────────────────────────────────────────────────────

    def get_pending_jobs(self):
        """Return companies that have at least one PENDING_REVIEW job."""
        pipeline = [
            {"$match": {f"{Config.FIELD_LATEST_JOBS}.{Config.FIELD_STATUS}": Config.STATUS_PENDING}},
            {"$project": {
                Config.FIELD_COMPANY_NAME: 1,
                Config.FIELD_LATEST_JOBS: {
                    "$filter": {
                        "input": f"${Config.FIELD_LATEST_JOBS}",
                        "as": "job",
                        "cond": {"$eq": [f"$$job.{Config.FIELD_STATUS}", Config.STATUS_PENDING]},
                    }
                },
            }},
        ]
        return list(self.collection.aggregate(pipeline))

    def try_claim_job(self, company_id, job_hash: str) -> bool:
        """Atomically move a job from PENDING_REVIEW → IN_REVIEW.
        Returns True only if this call performed the transition (prevents race conditions)."""
        result = self.collection.update_one(
            {
                "_id": company_id,
                Config.FIELD_LATEST_JOBS: {
                    "$elemMatch": {
                        Config.FIELD_JOB_HASH: job_hash,
                        Config.FIELD_STATUS: Config.STATUS_PENDING,
                    }
                },
            },
            {"$set": {f"{Config.FIELD_LATEST_JOBS}.$.{Config.FIELD_STATUS}": Config.STATUS_IN_REVIEW}},
        )
        return result.modified_count == 1

    def update_job_status(self, company_id, job_hash: str, status: str):
        self.collection.update_one(
            {
                "_id": company_id,
                f"{Config.FIELD_LATEST_JOBS}.{Config.FIELD_JOB_HASH}": job_hash,
            },
            {"$set": {f"{Config.FIELD_LATEST_JOBS}.$.{Config.FIELD_STATUS}": status}},
        )

    def get_job_by_hash(self, company_id, job_hash: str) -> dict | None:
        """Return {company_name, job} for use when sending to the public channel."""
        company = self.collection.find_one(
            {"_id": company_id, f"{Config.FIELD_LATEST_JOBS}.{Config.FIELD_JOB_HASH}": job_hash},
            {Config.FIELD_COMPANY_NAME: 1, f"{Config.FIELD_LATEST_JOBS}.$": 1},
        )
        if not company:
            return None
        jobs = company.get(Config.FIELD_LATEST_JOBS, [])
        if not jobs:
            return None
        return {"company_name": company.get(Config.FIELD_COMPANY_NAME, "Unknown"), "job": jobs[0]}

    # ── Review queue ──────────────────────────────────────────────────────────

    def add_to_review_queue(self, company_id, job_hash: str) -> str:
        """Insert a review entry and return its _id string (used in callback_data)."""
        result = self.review_queue.insert_one({
            "company_id": company_id,
            "job_hash": job_hash,
            "created_at": datetime.utcnow(),
        })
        return str(result.inserted_id)

    def get_review_entry(self, queue_id: str) -> dict | None:
        try:
            return self.review_queue.find_one({"_id": ObjectId(queue_id)})
        except Exception:
            return None

    def remove_from_review_queue(self, queue_id: str):
        try:
            self.review_queue.delete_one({"_id": ObjectId(queue_id)})
        except Exception:
            pass

    # ── Main loop (called by Application job_queue) ───────────────────────────

    async def process_pending_jobs(self, bot):
        """Poll MongoDB for PENDING_REVIEW jobs and send them to the review channel."""
        from telegram_sender import TelegramSender
        sender = TelegramSender()

        for company in self.get_pending_jobs():
            company_name = company.get(Config.FIELD_COMPANY_NAME, "Unknown")
            company_id = company.get("_id")

            for job in company.get(Config.FIELD_LATEST_JOBS, []):
                job_hash = job.get(Config.FIELD_JOB_HASH)

                # Auto-reject jobs that don't pass our filters
                if not self.is_israel_or_remote(job) or not self.is_cs_job(job):
                    if job_hash:
                        self.update_job_status(company_id, job_hash, Config.STATUS_REJECTED)
                    continue

                # Atomically claim the job (no duplicate review messages if bot restarts)
                if not self.try_claim_job(company_id, job_hash):
                    continue

                queue_id = self.add_to_review_queue(company_id, job_hash)
                try:
                    await sender.send_for_review(bot, job, company_name, queue_id)
                except Exception as e:
                    print(f"Failed to send for review '{job.get(Config.FIELD_TITLE)}': {e}")
                    # Revert so it's retried next poll
                    self.update_job_status(company_id, job_hash, Config.STATUS_PENDING)
                    self.remove_from_review_queue(queue_id)

    def close(self):
        self.client.close()
