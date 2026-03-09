from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import mgr
from api.routers import expenses, receipts


@asynccontextmanager
async def lifespan(app: FastAPI):
    mgr.init()
    yield


app = FastAPI(title="Receipt Analyzer API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(receipts.router, prefix="/api")
app.include_router(expenses.router, prefix="/api")

STATIC_DIR = Path(__file__).parent.parent / "ui" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Receipt Analyzer API", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
