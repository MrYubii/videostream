from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from app.config import get_settings
from app.database import Base, engine
from app.routers import admin, auth, comments, ratings, reactions, videos
from app.services.ratelimit import RateLimitMiddleware

settings = get_settings()

STATIC_DIR = Path(__file__).resolve().parent / "static"
MEDIA_DIR = settings.media_root


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="VideoStream API",
    description="TikTok-style video sharing platform. Static frontend + REST backend.",
    version="2.0.0",
    lifespan=lifespan,
)

cors_origins = settings.cors_origin_list
allow_all_origins = "*" in cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    RateLimitMiddleware,
    limit=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)
app.add_middleware(GZipMiddleware, minimum_size=1024)


class NoCacheStaticFiles(StaticFiles):
    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        if Path(full_path).suffix in (".html", ".js", ".css", ".svg"):
            response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/media", NoCacheStaticFiles(directory=str(MEDIA_DIR)), name="media")

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(videos.router)
app.include_router(comments.router)
app.include_router(ratings.router)
app.include_router(reactions.router)

app.mount("/", NoCacheStaticFiles(directory=str(STATIC_DIR), html=True), name="static")
