# syntax=docker/dockerfile:1

# ---- Build stage ----
FROM python:3.12-slim-bookworm AS build
WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Runtime stage ----
FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app

# zoneinfo (used for Asia/Jerusalem scheduling) needs the IANA tz database.
RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 appuser
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY channels.py config.py main.py mongo_watcher.py telegram_sender.py ./
RUN chown -R appuser:appuser /app

USER appuser
CMD ["python", "main.py"]
