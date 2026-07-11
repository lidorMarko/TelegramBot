import logging
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo import MongoClient

from config import Config


class MongoWatcher:
    def __init__(self):
        self.client = MongoClient(Config.MONGO_URI)
        self.db = self.client[Config.MONGO_DATABASE]
        self.collection = self.db[Config.MONGO_COLLECTION]
        self.review_queue = self.db["review_queue"]
        self.auto_approve = self.db["auto_approve_companies"]

    # ── Keyword sets ──────────────────────────────────────────────────────────

    CS_KEYWORDS = {
        "software", "software engineer", "software developer",
        "developer", "engineer", "engineering", "programmer", "coding",
        "backend", "back-end",
        "frontend", "front-end",
        "fullstack", "full-stack", "full stack",
        "web developer", "web engineer",
        "mobile developer", "android", "android developer",
        "ios", "ios developer", "react native", "flutter",
        "devops", "devsecops", "sre", "site reliability",
        "platform engineer", "platform",
        "cloud", "cloud engineer",
        "infrastructure", "infra engineer",
        "kubernetes", "k8s", "docker",
        "terraform", "ansible",
        "data engineer", "data scientist", "data analyst",
        "analytics engineer", "big data",
        "etl", "data pipeline",
        "database", "dba", "sql", "nosql",
        "bi developer", "business intelligence",
        "machine learning", "ml engineer",
        "ai engineer", "artificial intelligence",
        "deep learning", "nlp", "computer vision",
        "llm", "generative ai",
        "security engineer", "security researcher",
        "application security", "appsec",
        "pentester", "penetration tester",
        "cybersecurity", "cyber security",
        "qa engineer", "qa automation",
        "automation engineer", "test engineer",
        "quality assurance", "test automation",
        "embedded", "embedded engineer",
        "firmware", "firmware engineer",
        "hardware engineer",
        "fpga", "vlsi", "rtl",
        "network engineer", "network architect",
        "network security",
        "solution architect", "software architect",
        "tech lead", "technical lead",
        "principal engineer", "staff engineer",
        "engineering manager", "vp engineering", "vp r&d", "cto",
        "technical program manager", "tpm",
        "product manager", "technical product manager",
        "product owner",
        "r&d", "research engineer",
        "research scientist",
        "computer science",
        "game developer", "game engineer", "unity", "unreal",
        "graphics engineer", "gpu",
        "blockchain", "web3", "smart contract", "solidity",
        "system engineer", "systems engineer",
        "linux", "kernel",
        "python", "java", "c++", "c#", "golang", "go",
        "typescript", "javascript", "node", "nodejs",
        "react", "angular", "vue",
        "ruby", "scala", "kotlin", "swift", "rust", "php",
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
        "electrical engineer", "electronics engineer",
        "electrical engineering", "electronics engineering",
        "electro-optics engineer", "electro-optics",
        "avionics engineer", "avionics",
        "instrumentation engineer", "instrumentation",
        "hardware engineer",
        "circuit design", "circuit engineer",
        "pcb", "pcb design", "pcb designer", "pcb layout",
        "schematic design", "layout engineer",
        "analog design", "analog engineer",
        "mixed signal", "mixed-signal",
        "digital design", "digital engineer",
        "asic", "asic design", "asic verification",
        "fpga", "fpga engineer", "fpga developer",
        "vlsi", "rtl design",
        "verilog", "vhdl",
        "chip design", "chip verification",
        "power electronics", "power systems", "power engineer",
        "power supply", "power management",
        "power conversion", "inverter design",
        "solar engineer", "renewable energy engineer",
        "battery engineer", "energy storage",
        "motor drive", "motor control",
        "high voltage", "low voltage",
        "plc", "scada", "dcs",
        "control engineer", "control systems",
        "automation engineer", "automation technician",
        "robotics engineer", "robot programmer",
        "motion control", "servo engineer",
        "industrial automation", "factory automation",
        "mechatronics", "mechatronic engineer",
        "rf engineer", "rf design", "rf developer",
        "antenna engineer", "antenna design",
        "signal processing", "dsp engineer",
        "radar engineer", "radar systems",
        "microwave engineer",
        "communications engineer", "wireless engineer",
        "5g engineer", "lte engineer",
        "baseband engineer",
        "semiconductor", "semiconductor engineer",
        "ic design", "ic verification",
        "process engineer", "fab engineer",
        "characterization engineer",
        "embedded hardware", "embedded systems engineer",
        "firmware engineer",
        "bsp developer",
        "electromechanical", "electro-mechanical",
        "hvac", "hvac engineer",
        "field service engineer",
        "חשמל", "אלקטרוניקה",
        "מהנדס חשמל", "מהנדסת חשמל",
        "מהנדס אלקטרוניקה", "מהנדסת אלקטרוניקה",
        "מהנדס מעגלים", "תכנון מעגלים",
        "מעגל מודפס", "מעגלים",
        "מהנדס אוטומציה", "אוטומציה תעשייתית",
        "מהנדס כוח", "אנרגיה מתחדשת",
        "מהנדס בקרה", "מערכות בקרה",
        "פלק", "סקאדה",
        "מהנדס rf", "עיבוד אותות",
        "מהנדס רדאר", "מהנדס תקשורת",
        "סמיקונדקטור", "עיצוב שבבים",
        "אלקטרו-אופטיקה", "אביוניקה",
        "מכטרוניקה", "רובוטיקה",
        "מהנדס חומרה", "פירמוור",
        "מהנדס שדה",
    }

    ISRAEL_TERMS = {
        "israel", "isr-",
        "tel aviv", "tel-aviv",
        "haifa", "jerusalem", "raanana", "ra'anana",
        "herzliya", "beer sheva", "be'er sheva", "beersheba", "netanya", "petah tikva",
        "petach tikva", "rehovot", "rishon lezion", "rishon le-zion", "kfar saba",
        "rosh haayin", "hod hasharon", "givatayim", "ramat gan", "ramat-gan",
        "bnei brak", "ashdod", "ashkelon", "modiin", "caesarea", "yokneam",
        "nahariya", "karmiel", "holon", "bat yam", "lod", "ramla", "eilat",
        "nazareth", "afula", "tiberias", "yavne", "hadera", "tzrifin",
        "nes ziona", "nes-ziona", "migdal ha'emek", "migdal haemek",
        "kiryat gat", "kiryat-gat",
        # Hebrew city names
        "תל אביב", "חיפה", "ירושלים", "פתח תקווה", "ראשון לציון",
        "נס ציונה", "אילת", "בת ים", "טבריה", "באר שבע", "נתניה",
    }
    REMOTE_TERMS = {"remote", "hybrid", "work from home", "wfh", "home based"}

    # ── EU geography ──────────────────────────────────────────────────────────
    EU_COUNTRY_TERMS = {
        # Countries
        "germany", "deutschland", "france", "netherlands", "holland", "spain",
        "italy", "sweden", "norway", "denmark", "finland", "poland",
        "czech republic", "czechia", "austria", "switzerland", "belgium",
        "portugal", "ireland", "united kingdom", "uk", "england", "scotland",
        "wales", "romania", "hungary", "bulgaria", "croatia", "slovakia",
        "slovenia", "estonia", "latvia", "lithuania", "luxembourg", "malta",
        "cyprus", "greece", "serbia", "ukraine",
        # Major tech-hub cities
        "berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne",
        "düsseldorf", "amsterdam", "rotterdam", "paris", "lyon", "marseille",
        "madrid", "barcelona", "milan", "rome", "stockholm", "gothenburg",
        "oslo", "copenhagen", "helsinki", "warsaw", "krakow", "prague",
        "vienna", "zurich", "geneva", "brussels", "lisbon", "porto", "dublin",
        "london", "manchester", "birmingham", "edinburgh", "bucharest",
        "budapest", "sofia", "zagreb", "tallinn", "riga", "vilnius",
        "bratislava", "ljubljana", "nicosia", "athens", "thessaloniki",
        "belgrade", "kyiv",
    }
    # Explicit "remote in Europe" hints — generic "remote" alone stays with IL bots.
    # Worldwide/home-based locations are also treated as EU-eligible.
    EU_REMOTE_HINTS = {
        "remote europe", "europe remote", "remote eu", "eu remote",
        "remote emea", "emea remote", "remote, europe", "europe, remote",
        "fully remote europe", "european union", "remote (europe)",
        "(europe) remote", "remote - europe", "europe - remote",
        "worldwide", "world wide", "home base", "home based", "home-based",
        "global remote", "remote worldwide", "work from anywhere",
    }

    # ── EU role keyword sets (used for sub-category routing) ──────────────────
    AIML_KEYWORDS = {
        "machine learning", "ml engineer", "ml developer", "ml researcher",
        "ai engineer", "ai developer", "ai researcher", "artificial intelligence",
        "deep learning", "nlp", "computer vision", "llm", "generative ai",
        "data scientist", "applied scientist", "research scientist",
    }
    BACKEND_KEYWORDS = {
        "backend", "back-end", "back end", "server side", "server-side",
        "backend developer", "backend engineer", "api developer", "api engineer",
        "backend architect",
    }
    FULLSTACK_KEYWORDS = {
        "fullstack", "full-stack", "full stack",
        "fullstack developer", "full-stack developer", "full stack developer",
        "fullstack engineer", "full-stack engineer", "full stack engineer",
    }

    HASHTAG_MAP = [
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
        (["react native"], "reactnative"),
        (["react"], "react"),
        (["angular"], "angular"),
        (["vue"], "vue"),
        (["node.js", "nodejs", "node "], "nodejs"),
        (["next.js", "nextjs"], "nextjs"),
        (["django", "flask", "fastapi"], "python"),
        (["spring"], "java"),
        (["flutter"], "flutter"),
        (["fullstack", "full-stack", "full stack"], "fullstack"),
        (["backend", "back-end", "back end", "server side", "server-side"], "backend"),
        (["frontend", "front-end", "front end", "ui developer", "ui engineer"], "frontend"),
        (["mobile developer", "mobile engineer", "mobile "], "mobile"),
        (["android"], "android"),
        (["ios developer", "ios engineer"], "ios"),
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
        (["data engineer", "data engineering"], "dataengineering"),
        (["data scientist"], "datascience"),
        (["data analyst", "analytics engineer"], "dataanalytics"),
        (["big data", "etl", "data pipeline"], "data"),
        (["machine learning", "ml engineer", "ml developer"], "machinelearning"),
        (["deep learning", "computer vision", " nlp ", "generative ai", " llm "], "ai"),
        (["ai engineer", "ai developer", "artificial intelligence"], "ai"),
        (["appsec", "application security"], "appsec"),
        (["penetration", "pentester", "pen test"], "pentest"),
        (["cybersecurity", "cyber security", "security engineer", "security researcher"], "cybersecurity"),
        (["network security"], "networksecurity"),
        (["qa automation", "test automation", "automation engineer"], "qaautomation"),
        (["qa engineer", "quality assurance", "test engineer"], "qa"),
        (["embedded", "firmware"], "embedded"),
        (["fpga", "vlsi", "rtl", "hardware engineer"], "hardware"),
        (["remote"], "remote"),
        (["hybrid"], "hybrid"),
    ]

    # Most-specific rules first — first match wins
    UDEMY_MAP = [
        # ── Electronics ──────────────────────────────────────────────────────
        (["vlsi", "asic", "verilog", "vhdl", "rtl", "fpga", "chip design", "ic design", "ic verification", "digital design"], "https://trk.udemy.com/WO2v9M"),
        (["signal processing", "dsp", "baseband engineer", "baseband developer"], "https://trk.udemy.com/NG2kvb"),
        (["rf ", "rf/", "rf-", "antenna", "microwave", "radar"], "https://trk.udemy.com/Pz4dZY"),
        # ── CS ───────────────────────────────────────────────────────────────
        (["deep learning", "computer vision"], "https://trk.udemy.com/7Xn7G3"),
        (["llm", "generative ai", "gen ai", "large language model", "בינה מלאכותית"], "https://trk.udemy.com/jROaDn"),
        (["machine learning", "ml engineer", "ml developer", "data scientist"], "https://trk.udemy.com/jROaDn"),
        (["solution architect", "solutions architect", "cloud architect"], "https://trk.udemy.com/KB4679"),
        (["devops", "devsecops", "kubernetes", " k8s ", "docker", "terraform", "site reliability", " sre "], "https://trk.udemy.com/m4n2AZ"),
        (["embedded", "firmware", "linux kernel", "kernel developer"], "https://trk.udemy.com/PzKV0Y"),
        (["react native", "react"], "https://trk.udemy.com/oNzQqY"),
        (["javascript", "typescript", "frontend", "front-end", "angular", "vue", "nodejs", "next.js"], "https://trk.udemy.com/gRDm7X"),
        (["python", "django", "flask", "fastapi"], "https://trk.udemy.com/k4zyvV"),
        (["java ", "java,", "java-", "java/", "spring", "kotlin"], "https://trk.udemy.com/VOZJKj"),
        (["rpa", "robotic process automation"], "https://trk.udemy.com/MK2VjN"),
        (["system design", "system architect", "principal engineer", "staff engineer"], "https://trk.udemy.com/4adLj1"),
        # General software/backend — algorithmic prep as fallback
        (["software engineer", "software developer", "backend", "fullstack", "full-stack", "full stack", "מפתח", "מפתחת", "פיתוח תוכנה"], "https://trk.udemy.com/oNzxvW"),
    ]

    # ── Filters ───────────────────────────────────────────────────────────────

    def is_cs_job(self, job: dict) -> bool:
        title = (job.get(Config.FIELD_TITLE, "") or "").lower()
        return any(kw in title for kw in self.CS_KEYWORDS)

    def is_electronics_job(self, job: dict) -> bool:
        title = (job.get(Config.FIELD_TITLE, "") or "").lower()
        return any(kw in title for kw in self.ELECTRONICS_KEYWORDS)

    def is_eu_relevant(self, job: dict) -> bool:
        """True when the location explicitly names an EU country/city, or says 'remote Europe/EU'."""
        location = (job.get(Config.FIELD_LOCATION, "") or "").lower()
        if not location.strip():
            return False
        return (
            any(t in location for t in self.EU_COUNTRY_TERMS)
            or any(hint in location for hint in self.EU_REMOTE_HINTS)
        )

    def is_israel_or_remote(self, job: dict) -> bool:
        """True for Israel-located jobs, generic remote/hybrid, or no location (assume Israel)."""
        location = job.get(Config.FIELD_LOCATION, "") or ""
        if not location.strip():
            return True
        loc = location.lower()
        return any(t in loc for t in self.REMOTE_TERMS) or any(t in loc for t in self.ISRAEL_TERMS)

    def get_job_category(self, job: dict) -> str:
        """Return the routing category for a job.

        All EU/worldwide CS jobs route to 'backend_eu' (the unified Tech Jobs EU channel).
        Israel/generic-remote jobs fall back to 'cs'.
        """
        if self.is_electronics_job(job):
            return "electronics"
        if self.is_eu_relevant(job) and self.is_cs_job(job):
            return "backend_eu"
        return "cs"

    def suggest_udemy_url(self, job: dict) -> str | None:
        title = (job.get(Config.FIELD_TITLE, "") or "").lower()
        description = (job.get(Config.FIELD_DESCRIPTION, "") or "").lower()
        text = f" {title} {description} "
        for keywords, url in self.UDEMY_MAP:
            if any(kw in text for kw in keywords):
                return url
        return None

    def extract_hashtags_from_job(self, job: dict) -> list[str]:
        title = (job.get(Config.FIELD_TITLE, "") or "").lower()
        description = (job.get(Config.FIELD_DESCRIPTION, "") or "").lower()
        text = f" {title} {description} "

        tags: list[str] = []
        seen: set[str] = set()
        for keywords, hashtag in self.HASHTAG_MAP:
            if hashtag in seen:
                continue
            if any(kw in text for kw in keywords):
                tags.append(hashtag)
                seen.add(hashtag)
        return tags

    # ── Companies collection ──────────────────────────────────────────────────

    def get_pending_jobs(self):
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

    def try_claim_job(self, company_id: str, job_hash: str) -> bool:
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

    def update_job_status(self, company_id: str, job_hash: str, status: str):
        self.collection.update_one(
            {
                "_id": company_id,
                f"{Config.FIELD_LATEST_JOBS}.{Config.FIELD_JOB_HASH}": job_hash,
            },
            {"$set": {f"{Config.FIELD_LATEST_JOBS}.$.{Config.FIELD_STATUS}": status}},
        )

    def get_job_by_hash(self, company_id: str, job_hash: str) -> dict | None:
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

    # ── Review queue (stored in MongoDB) ─────────────────────────────────────

    def add_to_review_queue(self, company_id: str, job_hash: str, initial_hashtags: list | None = None, category: str = "cs", job: dict | None = None, company_name: str | None = None, initial_udemy_url: str | None = None, target_channel_id: str = "") -> str:
        result = self.review_queue.insert_one({
            "company_id": company_id,
            "job_hash": job_hash,
            "created_at": datetime.utcnow(),
            "udemy_url": initial_udemy_url,
            "hashtags": initial_hashtags or [],
            "cross_promo": False,
            "footer_message": False,
            "donation": False,
            "cta_text": None,
            "cta_url": None,
            "review_message_id": None,
            "category": category,
            "job_snapshot": job or {},
            "company_name_snapshot": company_name or "",
            "target_channel_id": target_channel_id,
        })
        return str(result.inserted_id)

    def get_review_entry(self, queue_id: str) -> dict | None:
        try:
            entry = self.review_queue.find_one({"_id": ObjectId(queue_id)})
            if entry:
                entry["id"] = str(entry["_id"])
            return entry
        except Exception:
            return None

    def remove_from_review_queue(self, queue_id: str):
        try:
            self.review_queue.delete_one({"_id": ObjectId(queue_id)})
        except Exception:
            pass

    def expire_stale_queue_entries(self, max_age_days: int = 3) -> int:
        """Auto-reject queue entries older than max_age_days that were never acted on."""
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        stale = list(self.review_queue.find({"created_at": {"$lt": cutoff}}))
        if not stale:
            return 0

        for entry in stale:
            company_id = entry.get("company_id")
            job_hash = entry.get("job_hash")
            if company_id and job_hash:
                self.update_job_status(company_id, job_hash, Config.STATUS_REJECTED)
            self.review_queue.delete_one({"_id": entry["_id"]})

        logging.info(
            "Expired %d stale review queue entries (older than %d days)",
            len(stale), max_age_days,
        )
        return len(stale)

    def set_udemy_url(self, queue_id: str, url: str):
        try:
            self.review_queue.update_one(
                {"_id": ObjectId(queue_id)},
                {"$set": {"udemy_url": url}},
            )
        except Exception:
            pass

    def set_cross_promo(self, queue_id: str, value: bool):
        try:
            self.review_queue.update_one(
                {"_id": ObjectId(queue_id)},
                {"$set": {"cross_promo": value}},
            )
        except Exception:
            pass

    def set_target_channel(self, queue_id: str, channel_id: str):
        try:
            self.review_queue.update_one(
                {"_id": ObjectId(queue_id)},
                {"$set": {"target_channel_id": channel_id}},
            )
        except Exception:
            pass

    def set_footer_message(self, queue_id: str, value: bool):
        try:
            self.review_queue.update_one(
                {"_id": ObjectId(queue_id)},
                {"$set": {"footer_message": value}},
            )
        except Exception:
            pass

    def set_donation(self, queue_id: str, value: bool):
        try:
            self.review_queue.update_one(
                {"_id": ObjectId(queue_id)},
                {"$set": {"donation": value}},
            )
        except Exception:
            pass

    def add_hashtag(self, queue_id: str, hashtag: str):
        try:
            self.review_queue.update_one(
                {"_id": ObjectId(queue_id)},
                {"$addToSet": {"hashtags": hashtag}},
            )
        except Exception:
            pass

    def set_cta(self, queue_id: str, text: str, url: str):
        try:
            self.review_queue.update_one(
                {"_id": ObjectId(queue_id)},
                {"$set": {"cta_text": text, "cta_url": url}},
            )
        except Exception:
            pass

    def set_review_message_id(self, queue_id: str, message_id: int):
        try:
            self.review_queue.update_one(
                {"_id": ObjectId(queue_id)},
                {"$set": {"review_message_id": message_id}},
            )
        except Exception:
            pass

    # ── Auto-approve companies ────────────────────────────────────────────────

    def add_auto_approve_company(self, company_name: str):
        key = company_name.strip().lower()
        self.auto_approve.update_one(
            {"key": key},
            {"$set": {"key": key, "name": company_name.strip(), "added_at": datetime.utcnow()}},
            upsert=True,
        )

    def remove_auto_approve_company(self, company_name: str) -> bool:
        key = company_name.strip().lower()
        result = self.auto_approve.delete_one({"key": key})
        return result.deleted_count > 0

    def get_auto_approve_companies(self) -> list[str]:
        return [doc["name"] for doc in self.auto_approve.find({}, {"name": 1})]

    def is_auto_approve_company(self, company_name: str) -> bool:
        key = (company_name or "").strip().lower()
        return self.auto_approve.find_one({"key": key}) is not None

    # ── Main loop ─────────────────────────────────────────────────────────────

    MAX_JOBS_PER_POLL = 5
    SEND_DELAY_SECONDS = 2

    async def process_pending_jobs(self, bot, category: str, review_channel_id: str, public_channel_id: str = "", cross_promo_url: str = "", footer_message: str = "", english_only: bool = False, channel_label: str = "", reroute_options: list = None, donation_url: str = ""):
        import asyncio
        from telegram_sender import TelegramSender
        sender = TelegramSender()

        sent = 0
        for company in self.get_pending_jobs():
            if sent >= self.MAX_JOBS_PER_POLL:
                break

            company_name = company.get(Config.FIELD_COMPANY_NAME, "Unknown")
            company_id = company.get("_id")
            is_auto = self.is_auto_approve_company(company_name)

            for job in company.get(Config.FIELD_LATEST_JOBS, []):
                if sent >= self.MAX_JOBS_PER_POLL:
                    break

                job_hash = job.get(Config.FIELD_JOB_HASH)
                job_category = self.get_job_category(job)

                # Reject jobs that are completely unclassifiable (no CS or electronics match).
                # Only the CS bot does this to avoid all bots racing to reject.
                if category == "cs" and not self.is_cs_job(job) and not self.is_electronics_job(job):
                    if job_hash:
                        self.update_job_status(company_id, job_hash, Config.STATUS_REJECTED)
                    continue

                # Skip (don't reject) if the job belongs to a different category.
                # Another bot with the matching category will pick it up.
                if job_category != category:
                    continue

                # Location filter: EU bots want EU-explicit jobs; IL bots want Israel/remote.
                # Skip without rejecting — stale jobs are cleaned up by expire_stale_queue_entries.
                if category.endswith("_eu"):
                    if not self.is_eu_relevant(job):
                        continue
                else:
                    if not self.is_israel_or_remote(job):
                        continue

                if self.review_queue.find_one({"company_id": company_id, "job_hash": job_hash}):
                    self.update_job_status(company_id, job_hash, Config.STATUS_IN_REVIEW)
                    continue

                if not self.try_claim_job(company_id, job_hash):
                    continue

                auto_hashtags = self.extract_hashtags_from_job(job)
                auto_udemy = self.suggest_udemy_url(job)

                if is_auto and public_channel_id:
                    try:
                        await sender.send_to_public(bot, job, company_name, channel_id=public_channel_id, hashtags=auto_hashtags, english_only=english_only)
                        self.update_job_status(company_id, job_hash, Config.STATUS_SENT)
                        await bot.send_message(
                            chat_id=review_channel_id,
                            text=f"⚡ אישור אוטומטי: <b>{job.get(Config.FIELD_TITLE, '')}</b> @ {company_name}",
                            parse_mode="HTML",
                        )
                        sent += 1
                        await asyncio.sleep(self.SEND_DELAY_SECONDS)
                    except Exception as e:
                        print(f"Failed to auto-approve '{job.get(Config.FIELD_TITLE)}': {e}")
                        self.update_job_status(company_id, job_hash, Config.STATUS_PENDING)
                    continue

                queue_id = self.add_to_review_queue(company_id, job_hash, initial_hashtags=auto_hashtags, category=category, job=job, company_name=company_name, initial_udemy_url=auto_udemy, target_channel_id=public_channel_id)
                try:
                    message = await sender.send_for_review(bot, job, company_name, queue_id, hashtags=auto_hashtags, channel_id=review_channel_id, cross_promo_url=cross_promo_url, footer_message=footer_message, english_only=english_only, channel_label=channel_label, reroute_options=reroute_options, current_target_id=public_channel_id, donation_url=donation_url)
                    self.set_review_message_id(queue_id, message.message_id)
                    sent += 1
                    await asyncio.sleep(self.SEND_DELAY_SECONDS)
                except Exception as e:
                    print(f"Failed to send for review '{job.get(Config.FIELD_TITLE)}': {e}")
                    self.update_job_status(company_id, job_hash, Config.STATUS_PENDING)
                    self.remove_from_review_queue(queue_id)

    def get_zero_result_companies(self) -> list[str]:
        """Return names of companies whose latestJobs array is empty."""
        docs = self.collection.find(
            {"$or": [{"latestJobs": []}, {"latestJobs": {"$exists": False}}]},
            {"name": 1},
        )
        return [doc.get("name", "Unknown") for doc in docs]

    def close(self):
        self.client.close()
