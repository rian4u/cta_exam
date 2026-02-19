FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY tax_exam.db /app/tax_exam.db

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "-m", "tax_exam_app.serve"]
