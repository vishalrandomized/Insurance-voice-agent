# Deterministic build for Railway (root directory = apps/api).
# python:3.12-slim is enough — PyMuPDF/numpy ship manylinux cp312 wheels, so no
# system build tools are needed.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# $PORT is provided by Railway; shell form so it expands.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
