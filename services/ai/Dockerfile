# Build context is the repo root (see infra/docker-compose.yml) so this
# image can COPY the shared rules/ directory alongside the service code.
FROM python:3.11-slim

WORKDIR /app

COPY services/ai/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 -r requirements.txt

COPY services/ai/app ./app
COPY rules ./rules

ENV PORT=8100
EXPOSE 8100

# Shell form (not exec-form array) so ${PORT} actually expands -- this was
# previously hardcoded to 8100 regardless of the PORT env var's value.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8100}"]
