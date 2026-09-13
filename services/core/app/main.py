from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import (
    abdm,
    auth,
    dashboard,
    diagnostics,
    encounters,
    escalations,
    follow_ups,
    health,
    medicine_stock,
    patients,
    queue,
    referrals,
    teleconsults,
    triage,
)

app = FastAPI(title="HealthBridge Core Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().core_allowed_origins_list,
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
app.include_router(referrals.router)
app.include_router(diagnostics.router)
app.include_router(medicine_stock.router)
app.include_router(follow_ups.router)
app.include_router(teleconsults.router)
