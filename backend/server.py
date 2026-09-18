"""AIScholar FastAPI bootstrap. Route logic lives in routers/*.py; shared code in core.py."""
import os
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from core import client
from routers import auth, pricing, assignments, payments, ai_check, references, stats, settings, user

app = FastAPI(title="AIScholar API", version="1.2.0")

for module in (auth, pricing, assignments, payments, ai_check, references, stats, settings, user):
    app.include_router(module.router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
