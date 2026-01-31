import signal
import sys
from config import Config
from mongo_watcher import MongoWatcher


def main():
    print("MongoDB to Telegram Job Notifier")
    print("=================================\n")

    try:
        Config.validate()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("\nPlease copy .env.example to .env and fill in your values.")
        sys.exit(1)

    watcher = MongoWatcher()

    def signal_handler(sig, frame):
        print("\n\nShutting down...")
        watcher.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        watcher.watch()
    except Exception as e:
        print(f"Error: {e}")
        watcher.close()
        sys.exit(1)


if __name__ == "__main__":
    main()
