FROM python:3.12-slim

WORKDIR /app

# Only runtime assets are copied (enforced by .dockerignore)
COPY webapp ./webapp
COPY data/questions.db ./data/questions.db

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["sh", "-c", "python webapp/server.py --host 0.0.0.0 --port ${PORT:-8000}"]

