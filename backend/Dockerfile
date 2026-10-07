# NiFi NAR Manager — backend image

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libffi-dev openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN groupadd -r narmgr && useradd -r -g narmgr narmgr \
    && mkdir -p /app/data /app/nar_files /app/backup /app/logs \
    && chown -R narmgr:narmgr /app

USER narmgr

EXPOSE 8000

# Apply migrations, then start the API server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
