# MongoDB to Telegram Job Notifier

Polls a MongoDB database for new job listings and sends notifications to a Telegram channel.

## Setup
venv\Scripts\activate
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your values:
   ```bash
   cp .env.example .env
   ```

3. Configure your environment variables in `.env`

## Database Structure

The bot expects a `companies` collection with this structure:

```javascript
{
  _id: ObjectId,
  name: "Company Name",
  url: "https://company.com/jobs/",
  latestJobs: [
    {
      jobHash: "unique_hash",
      title: "Job Title",
      location: "Location",
      description: "Job description...",
      url: "https://company.com/jobs/123",
      firstSeenAt: ISODate,
      lastSeenAt: ISODate,
      posted: false  // Set to true after sending to Telegram
    }
  ]
}
```

## Usage

```bash
python main.py
```

The bot will:
1. Poll the database every 30 seconds (configurable via `POLL_INTERVAL`)
2. Find jobs where `posted = false`
3. Send them to your Telegram channel
4. Mark them as `posted = true`
