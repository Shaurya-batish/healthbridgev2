# Build context is the repo root (see infra/docker-compose.yml) so this
# image can COPY the shared rules/ directory alongside the service code.
FROM python:3.11-slim

WORKDIR /app

COPY services/ai/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ai/app ./app
COPY rules ./rules

ENV PORT=8100
EXPOSE 8100

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
