FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV DB_PATH=/app/tax_exam_service.db

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY tax_exam_service.db /app/tax_exam_service.db

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "-m", "tax_exam_app.serve"]
