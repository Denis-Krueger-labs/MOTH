from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def root():
    return {
        "name": "MOTH",
        "status": "awake",
        "message": "mof found the api",
    }