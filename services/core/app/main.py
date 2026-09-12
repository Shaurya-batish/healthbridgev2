from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import abdm, auth, dashboard, encounters, escalations, health, patients, queue, triage

app = FastAPI(title="HealthBridge Core Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(encounters.router)
app.include_router(triage.router)
app.include_router(queue.router)
app.include_router(escalations.router)
app.include_router(dashboard.router)
app.include_router(abdm.router)
