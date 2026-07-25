FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    python3-pip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /workspace

# pytest ships in the image so the suite runs the same way the api's does:
# `docker compose run --rm notifier pytest -q`.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY app ./app
COPY pytest.ini ./
COPY tests ./tests

# Subscribers SQLite lives here; mounted as a named volume in compose.
ENV SUBSCRIBERS_DB_PATH=/data/subscribers.db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
