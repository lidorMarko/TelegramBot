"""
Run once to insert a fake job with PENDING_REVIEW status so you can test
the Approve / Reject buttons in the review channel.

Usage:
    python insert_test_job.py
"""
from pymongo import MongoClient
from config import Config
import uuid

client = MongoClient(Config.MONGO_URI)
db = client[Config.MONGO_DATABASE]
collection = db[Config.MONGO_COLLECTION]

test_job = {
    "title": "Test Software Engineer",
    "location": "Tel Aviv",
    "url": "https://example.com/job/test-123",
    "status": Config.STATUS_PENDING,
    "jobHash": f"test-{uuid.uuid4().hex[:8]}",
}

result = collection.update_one(
    {"name": "__TEST_COMPANY__"},
    {
        "$set": {"name": "__TEST_COMPANY__"},
        "$push": {"latestJobs": test_job},
    },
    upsert=True,
)

print(f"Inserted test job: {test_job['title']} (hash: {test_job['jobHash']})")
print("Now run: python main.py  — the job should appear in your review channel within 30s")
client.close()
