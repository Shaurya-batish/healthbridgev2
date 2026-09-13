FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# ${PORT:-8000}: docker-compose.yml (and app/config.py) already treat PORT
# as the configurable port -- it just didn't do anything here before,
# since this was hardcoded to 8000 regardless of what PORT was set to.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
