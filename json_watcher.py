import json
import uuid
from datetime import datetime
from pathlib import Path

from filelock import FileLock

from config import Config


class JsonWatcher:
    def __init__(self):
        self.companies_file = Path(Config.COMPANIES_JSON_PATH)
        self.review_queue_file = Path(Config.REVIEW_QUEUE_JSON_PATH)
        self._lock = FileLock(str(self.companies_file) + ".lock")
        self._queue_lock = FileLock(str(self.review_queue_file) + ".lock")

        if not self.review_queue_file.exists():
            self.review_queue_file.parent.mkdir(parents=True, exist_ok=True)
            self._write_queue([])

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
        "database", "dba", "sql", "nosql",
        "bi developer", "business intelligence",

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
        "engineering manager", "vp engineering", "vp r&d", "cto",
        "technical program manager", "tpm",

        # Product (tech-adjacent)
        "product manager", "technical product manager",
        "product owner",

        # Research
        "r&d", "research engineer",
        "research scientist",
        "computer science",

        # Game development
        "game developer", "game engineer", "unity", "unreal",
        "graphics engineer", "gpu",

        # Blockchain / Web3
        "blockchain", "web3", "smart contract", "solidity",

        # Systems
        "system engineer", "systems engineer",
        "linux", "kernel",

        # Common programming languages
        "python", "java", "c++", "c#", "golang", "go",
        "typescript", "javascript", "node", "nodejs",
        "react", "angular", "vue",
        "ruby", "scala", "kotlin", "swift", "rust", "php",

        # Hebrew
        "מפתח", "מפתחת", "מהנדס", "מהנדסת",
        "תוכנה", "פיתוח", "פיתוח תוכנה",
        "איש פיתוח", "devops", "ענן",
        "אבטחת מידע", "סייבר",
        "בדיקות", "בדיקות תוכנה",
        "אוטומציה", "בדיקות אוטומציה",
        "דאטה", "נתונים",
        "למידת מכונה", "בינה מלאכותית",
        "מנהל מוצר", "מנהל הנדסה",
    }

    ELECTRONICS_KEYWORDS = {
        # English — electrical/electronics engineering
        "electrical engineer", "electronics engineer",
        "electrical engineering", "electronics engineering",
        "circuit design", "pcb", "pcb design", "pcb designer",
        "power electronics", "power systems", "power engineer",
        "power supply", "power management",
        "plc", "scada", "control engineer", "control systems",
        "rf engineer", "rf design", "antenna", "signal processing",
        "semiconductor", "analog", "analog design",
        "hvac", "electromechanical",
        # Hebrew
        "חשמל", "אלקטרוניקה", "מהנדס חשמל", "מהנדסת חשמל",
        "מעגל מודפס", "מעגלים",
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

    def is_electronics_job(self, job: dict) -> bool:
        title = (job.get(Config.FIELD_TITLE, "") or "").lower()
        return any(kw in title for kw in self.ELECTRONICS_KEYWORDS)

    def get_job_category(self, job: dict) -> str:
        """Returns 'electronics' or 'cs'."""
        if self.is_electronics_job(job):
            return "electronics"
        return "cs"

    def is_israel_or_remote(self, job: dict) -> bool:
        location = job.get(Config.FIELD_LOCATION, "") or ""
        if not location.strip():
            return True  # no location → assume Israel
        loc = location.lower()
        return any(t in loc for t in self.REMOTE_TERMS) or any(t in loc for t in self.ISRAEL_TERMS)

    # ── JSON file helpers ─────────────────────────────────────────────────────

    def _read_companies(self) -> list:
        if not self.companies_file.exists():
            return []
        with open(self.companies_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_companies(self, companies: list):
        with open(self.companies_file, "w", encoding="utf-8") as f:
            json.dump(companies, f, indent=2, default=str)

    def _read_queue(self) -> list:
        if not self.review_queue_file.exists():
            return []
        with open(self.review_queue_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_queue(self, queue: list):
        with open(self.review_queue_file, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2, default=str)

    # ── Data access ───────────────────────────────────────────────────────────

    def get_pending_jobs(self):
        """Return companies that have at least one PENDING_REVIEW job."""
        with self._lock:
            companies = self._read_companies()

        result = []
        for company in companies:
            pending = [
                j for j in company.get(Config.FIELD_LATEST_JOBS, [])
                if j.get(Config.FIELD_STATUS) == Config.STATUS_PENDING
            ]
            if pending:
                result.append({
                    "_id": company.get("id"),
                    Config.FIELD_COMPANY_NAME: company.get(Config.FIELD_COMPANY_NAME, "Unknown"),
                    Config.FIELD_LATEST_JOBS: pending,
                })
        return result

    def try_claim_job(self, company_id: str, job_hash: str) -> bool:
        """Atomically move a job PENDING_REVIEW → IN_REVIEW using a file lock."""
        with self._lock:
            companies = self._read_companies()
            claimed = False
            for company in companies:
                if company.get("id") != company_id:
                    continue
                for job in company.get(Config.FIELD_LATEST_JOBS, []):
                    if (job.get(Config.FIELD_JOB_HASH) == job_hash
                            and job.get(Config.FIELD_STATUS) == Config.STATUS_PENDING):
                        job[Config.FIELD_STATUS] = Config.STATUS_IN_REVIEW
                        claimed = True
                        break
                if claimed:
                    break
            if claimed:
                self._write_companies(companies)
        return claimed

    def update_job_status(self, company_id: str, job_hash: str, status: str):
        with self._lock:
            companies = self._read_companies()
            for company in companies:
                if company.get("id") != company_id:
                    continue
                for job in company.get(Config.FIELD_LATEST_JOBS, []):
                    if job.get(Config.FIELD_JOB_HASH) == job_hash:
                        job[Config.FIELD_STATUS] = status
                        break
                break
            self._write_companies(companies)

    def get_job_by_hash(self, company_id: str, job_hash: str) -> dict | None:
        with self._lock:
            companies = self._read_companies()
        for company in companies:
            if company.get("id") != company_id:
                continue
            for job in company.get(Config.FIELD_LATEST_JOBS, []):
                if job.get(Config.FIELD_JOB_HASH) == job_hash:
                    return {
                        "company_name": company.get(Config.FIELD_COMPANY_NAME, "Unknown"),
                        "job": job,
                    }
        return None

    # ── Review queue ──────────────────────────────────────────────────────────

    # keyword fragments → hashtag (longest/most-specific first wins)
    HASHTAG_MAP = [
        # Languages
        (["typescript"], "typescript"),
        (["javascript", " js "], "javascript"),
        (["python"], "python"),
        (["golang", "go developer", "go engineer", " go "], "golang"),
        (["kotlin"], "kotlin"),
        (["swift"], "swift"),
        (["rust"], "rust"),
        (["scala"], "scala"),
        (["ruby"], "ruby"),
        (["php"], "php"),
        (["c++", "c plus plus"], "cpp"),
        (["c#", "csharp", ".net", "dotnet"], "dotnet"),
        (["java ", "java,", "java-", "java/"], "java"),
        # Frameworks / runtimes
        (["react native"], "reactnative"),
        (["react"], "react"),
        (["angular"], "angular"),
        (["vue"], "vue"),
        (["node.js", "nodejs", "node "], "nodejs"),
        (["next.js", "nextjs"], "nextjs"),
        (["django", "flask", "fastapi"], "python"),
        (["spring"], "java"),
        (["flutter"], "flutter"),
        # Role types
        (["fullstack", "full-stack", "full stack"], "fullstack"),
        (["backend", "back-end", "back end", "server side", "server-side"], "backend"),
        (["frontend", "front-end", "front end", "ui developer", "ui engineer"], "frontend"),
        (["mobile developer", "mobile engineer", "mobile "], "mobile"),
        (["android"], "android"),
        (["ios developer", "ios engineer"], "ios"),
        # DevOps / Cloud / Infra
        (["devsecops", "devops"], "devops"),
        (["site reliability", " sre "], "sre"),
        (["platform engineer"], "platform"),
        (["kubernetes", " k8s "], "kubernetes"),
        (["docker"], "docker"),
        (["terraform", "ansible"], "iac"),
        (["aws", "amazon web services"], "aws"),
        (["google cloud", " gcp "], "gcp"),
        (["azure"], "azure"),
        (["cloud engineer", "cloud architect"], "cloud"),
        # Data
        (["data engineer", "data engineering"], "dataengineering"),
        (["data scientist"], "datascience"),
        (["data analyst", "analytics engineer"], "dataanalytics"),
        (["big data", "etl", "data pipeline"], "data"),
        # AI / ML
        (["machine learning", "ml engineer", "ml developer"], "machinelearning"),
        (["deep learning", "computer vision", " nlp ", "generative ai", " llm "], "ai"),
        (["ai engineer", "ai developer", "artificial intelligence"], "ai"),
        # Security
        (["appsec", "application security"], "appsec"),
        (["penetration", "pentester", "pen test"], "pentest"),
        (["cybersecurity", "cyber security", "security engineer", "security researcher"], "cybersecurity"),
        (["network security"], "networksecurity"),
        # QA
        (["qa automation", "test automation", "automation engineer"], "qaautomation"),
        (["qa engineer", "quality assurance", "test engineer"], "qa"),
        # Embedded / HW
        (["embedded", "firmware"], "embedded"),
        (["fpga", "vlsi", "rtl", "hardware engineer"], "hardware"),
        # Work mode
        (["remote"], "remote"),
        (["hybrid"], "hybrid"),
    ]

    def extract_hashtags_from_job(self, job: dict) -> list[str]:
        title = (job.get(Config.FIELD_TITLE, "") or "").lower()
        description = (job.get(Config.FIELD_DESCRIPTION, "") or "").lower()
        text = f" {title} {description} "  # pad with spaces for whole-word matching

        tags: list[str] = []
        seen: set[str] = set()
        for keywords, hashtag in self.HASHTAG_MAP:
            if hashtag in seen:
                continue
            if any(kw in text for kw in keywords):
                tags.append(hashtag)
                seen.add(hashtag)
        return tags

    def add_to_review_queue(self, company_id: str, job_hash: str, initial_hashtags: list | None = None, category: str = "cs") -> str:
        queue_id = str(uuid.uuid4())
        entry = {
            "id": queue_id,
            "company_id": company_id,
            "job_hash": job_hash,
            "created_at": datetime.utcnow().isoformat(),
            "udemy_url": None,
            "hashtags": initial_hashtags or [],
            "review_message_id": None,
            "category": category,
        }
        with self._queue_lock:
            queue = self._read_queue()
            queue.append(entry)
            self._write_queue(queue)
        return queue_id

    def set_udemy_url(self, queue_id: str, url: str):
        with self._queue_lock:
            queue = self._read_queue()
            for entry in queue:
                if entry.get("id") == queue_id:
                    entry["udemy_url"] = url
                    break
            self._write_queue(queue)

    def add_hashtag(self, queue_id: str, hashtag: str):
        with self._queue_lock:
            queue = self._read_queue()
            for entry in queue:
                if entry.get("id") == queue_id:
                    tags = entry.setdefault("hashtags", [])
                    if hashtag not in tags:
                        tags.append(hashtag)
                    break
            self._write_queue(queue)

    def set_review_message_id(self, queue_id: str, message_id: int):
        with self._queue_lock:
            queue = self._read_queue()
            for entry in queue:
                if entry.get("id") == queue_id:
                    entry["review_message_id"] = message_id
                    break
            self._write_queue(queue)

    def get_review_entry(self, queue_id: str) -> dict | None:
        with self._queue_lock:
            queue = self._read_queue()
        return next((e for e in queue if e.get("id") == queue_id), None)

    def remove_from_review_queue(self, queue_id: str):
        with self._queue_lock:
            queue = self._read_queue()
            self._write_queue([e for e in queue if e.get("id") != queue_id])

    # ── Main loop (called by Application job_queue) ───────────────────────────

    async def process_pending_jobs(self, bot, category: str, review_channel_id: str):
        """Poll companies.json for PENDING_REVIEW jobs matching `category` and send them to review."""
        from telegram_sender import TelegramSender
        sender = TelegramSender()

        for company in self.get_pending_jobs():
            company_name = company.get(Config.FIELD_COMPANY_NAME, "Unknown")
            company_id = company.get("_id")

            for job in company.get(Config.FIELD_LATEST_JOBS, []):
                job_hash = job.get(Config.FIELD_JOB_HASH)

                job_category = self.get_job_category(job)

                # Auto-reject jobs that don't match any known category (only once, by CS bot)
                if category == "cs" and not self.is_cs_job(job) and not self.is_electronics_job(job):
                    if job_hash:
                        self.update_job_status(company_id, job_hash, Config.STATUS_REJECTED)
                    continue

                # Each bot only handles its own category
                if job_category != category:
                    continue

                # Claim the job (prevents duplicate review messages if bot restarts)
                if not self.try_claim_job(company_id, job_hash):
                    continue

                auto_hashtags = self.extract_hashtags_from_job(job)
                queue_id = self.add_to_review_queue(company_id, job_hash, initial_hashtags=auto_hashtags, category=category)
                try:
                    message = await sender.send_for_review(bot, job, company_name, queue_id, hashtags=auto_hashtags, channel_id=review_channel_id)
                    self.set_review_message_id(queue_id, message.message_id)
                except Exception as e:
                    print(f"Failed to send for review '{job.get(Config.FIELD_TITLE)}': {e}")
                    # Revert so it's retried next poll
                    self.update_job_status(company_id, job_hash, Config.STATUS_PENDING)
                    self.remove_from_review_queue(queue_id)

    def close(self):
        pass  # nothing to close
