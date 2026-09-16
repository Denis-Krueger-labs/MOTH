from fastapi import FastAPI

from app.api.flags import router as flags_router
from app.api.health import router as health_router
from app.db.database import initialize_database


initialize_database()

app = FastAPI()

app.include_router(health_router)
app.include_router(flags_router)


@app.get("/")
async def root():
    return {
        "name": "MOTH",
        "status": "awake",
        "message": "mof found the api",
    }