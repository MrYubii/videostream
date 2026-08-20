import re
import time
import uuid
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BeforeValidator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, get_db
from app.deps import get_current_user, require_role
from app.models import AgeRating, Comment, Rating, Reaction, Role, User, Video, VideoStatus
from app.schemas import VideoCreate, VideoDetail, VideoList, VideoOut, VideoUpdate
from app.services.cache import cache
from app.services.media import MediaProcessor
from app.services.storage import LocalStorageBackend, get_storage_backend, materialise_local_path

router = APIRouter(prefix="/api/videos", tags=["videos"])

settings = get_settings()
storage = get_storage_backend()
processor = MediaProcessor()

CHUNK_SIZE = 1024 * 1024
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")

VIEW_WINDOW_SECONDS = 1800
_view_cache: dict[tuple[int, str], float] = {}

ALLOWED_SUFFIXES = {".mp4", ".webm", ".ogg", ".mov", ".m4v"}


def _empty_to_none(value: object) -> object:
    return None if value == "" else value


AgeRatingParam = Annotated[Optional[AgeRating], BeforeValidator(_empty_to_none)]


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _parse_range(header: str, file_size: int) -> tuple[int, int] | None:
    match = RANGE_RE.fullmatch(header.strip())
    if not match:
        return None
    start_s, end_s = match.groups()
    if start_s == "":
        if end_s == "":
            return None
        suffix = int(end_s)
        if suffix <= 0:
            return (-1, -1)
        return max(file_size - suffix, 0), file_size - 1
    start = int(start_s)
    end = int(end_s) if end_s else file_size - 1
    if end >= file_size:
        end = file_size - 1
    if start > end or start >= file_size:
        return (-1, -1)
    return start, end


def _should_count_view(video_id: int, client_ip: str) -> bool:
    key = (video_id, client_ip)
    now = time.monotonic()
    last = _view_cache.get(key)
    if last is not None and now - last < VIEW_WINDOW_SECONDS:
        return False
    if len(_view_cache) > 10000:
        _view_cache.clear()
    _view_cache[key] = now
    return True


def _aggregate(db: Session, video_ids: list[int]) -> dict[int, dict]:
    rating_rows = (
        db.query(Rating.video_id, func.avg(Rating.value), func.count(Rating.id))
        .filter(Rating.video_id.in_(video_ids))
        .group_by(Rating.video_id)
        .all()
    )
    comment_rows = (
        db.query(Comment.video_id, func.count(Comment.id))
        .filter(Comment.video_id.in_(video_ids))
        .group_by(Comment.video_id)
        .all()
    )
    reaction_rows = (
        db.query(Reaction.video_id, Reaction.reaction, func.count(Reaction.id))
        .filter(Reaction.video_id.in_(video_ids))
        .group_by(Reaction.video_id, Reaction.reaction)
        .all()
    )
    aggregates: dict[int, dict] = {}
    for video_id, avg, count in rating_rows:
        aggregates.setdefault(video_id, {}).update(rating_average=round(float(avg), 1), rating_count=count)
    for video_id, count in comment_rows:
        aggregates.setdefault(video_id, {}).update(comment_count=count)
    for video_id, reaction, count in reaction_rows:
        agg = aggregates.setdefault(video_id, {})
        agg[f"{reaction.value}_count"] = count
    return aggregates


def _serialize(video: Video, agg: Optional[dict] = None, include_detail: bool = False) -> dict:
    agg = agg or {}
    payload = {
        "id": video.id,
        "title": video.title,
        "publisher": video.publisher,
        "producer": video.producer,
        "genre": video.genre,
        "age_rating": video.age_rating.value,
        "description": video.description,
        "thumbnail_url": storage.public_url(video.thumbnail_key) if video.thumbnail_key else "",
        "duration_seconds": video.duration_seconds,
        "status": video.status.value,
        "view_count": video.view_count,
        "uploader": video.uploader.username if video.uploader else "",
        "created_at": video.created_at,
        "rating_average": agg.get("rating_average"),
        "rating_count": agg.get("rating_count", 0),
        "comment_count": agg.get("comment_count", 0),
        "like_count": agg.get("like_count", 0),
        "dislike_count": agg.get("dislike_count", 0),
    }
    if include_detail:
        payload.update(
            stream_url=f"/api/videos/{video.id}/stream",
            size_bytes=video.size_bytes,
            content_type=video.content_type,
        )
    return payload


@router.get("", response_model=VideoList)
def list_videos(
    request: Request,
    search: str = "",
    genre: str = "",
    age_rating: AgeRatingParam = None,
    sort: str = "latest",
    offset: int = 0,
    limit: int = 0,
    db: Session = Depends(get_db),
):
    limit = limit if limit > 0 else settings.dashboard_page_size
    limit = min(limit, 100)
    cache_key = f"videos:list:{search}:{genre}:{age_rating}:{sort}:{offset}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    query = db.query(Video).filter(Video.status == VideoStatus.READY)
    if search:
        like = f"%{_escape_like(search)}%"
        query = query.filter(
            (Video.title.ilike(like, escape="\\"))
            | (Video.publisher.ilike(like, escape="\\"))
            | (Video.producer.ilike(like, escape="\\"))
            | (Video.genre.ilike(like, escape="\\"))
        )
    if genre:
        query = query.filter(Video.genre == genre)
    if age_rating:
        query = query.filter(Video.age_rating == age_rating)

    total = query.count()
    if sort == "popular":
        query = query.order_by(Video.view_count.desc(), Video.created_at.desc())
    else:
        query = query.order_by(Video.created_at.desc())

    videos = query.offset(offset).limit(limit).all()
    aggregates = _aggregate(db, [v.id for v in videos])
    items = [_serialize(v, aggregates.get(v.id)) for v in videos]

    response = VideoList(total=total, offset=offset, limit=limit, items=items)
    cache.set(cache_key, response, settings.cache_ttl_seconds)
    return response


@router.get("/{video_id}", response_model=VideoDetail)
def get_video(video_id: int, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    agg = _aggregate(db, [video.id]).get(video.id, {})
    return _serialize(video, agg, include_detail=True)


@router.patch("/{video_id}", response_model=VideoDetail)
def update_video(
    video_id: int,
    payload: VideoUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    if video.uploader_id != user.id and user.role != Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your video")
    if payload.title is not None:
        video.title = payload.title
    if payload.publisher is not None:
        video.publisher = payload.publisher
    if payload.producer is not None:
        video.producer = payload.producer
    if payload.genre is not None:
        video.genre = payload.genre
    if payload.age_rating is not None:
        video.age_rating = payload.age_rating
    if payload.description is not None:
        video.description = payload.description
    db.commit()
    db.refresh(video)
    cache.invalidate_prefix("videos:list:")
    agg = _aggregate(db, [video.id]).get(video.id, {})
    return _serialize(video, agg, include_detail=True)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    if video.uploader_id != user.id and user.role != Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your video")

    storage.delete(video.storage_key)
    if video.thumbnail_key:
        storage.delete(video.thumbnail_key)
    db.delete(video)
    db.commit()
    cache.invalidate_prefix("videos:list:")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{video_id}/stream")
async def stream_video(video_id: int, request: Request, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    if video.status != VideoStatus.READY:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Video is still being processed")

    file_size = storage.size(video.storage_key) or video.size_bytes
    if file_size == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media file missing")

    range_header = request.headers.get("range")
    start, end = 0, file_size - 1
    status_code = 200
    if range_header:
        parsed = _parse_range(range_header, file_size)
        if parsed == (-1, -1):
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                detail="Requested range not satisfiable",
                headers={"Content-Range": f"bytes */{file_size}"},
            )
        if parsed is not None:
            start, end = parsed
            status_code = 206

    client_ip = request.client.host if request.client else "unknown"
    if _should_count_view(video_id, client_ip):
        db.query(Video).filter(Video.id == video_id).update({Video.view_count: Video.view_count + 1})
        db.commit()
        cache.invalidate_prefix("videos:list:")

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Content-Type": video.content_type,
        "Cache-Control": "public, max-age=3600",
    }
    if status_code == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    async def gen():
        for chunk in storage.iter_read(video.storage_key, start=start, length=end - start + 1):
            yield chunk

    return StreamingResponse(gen(), status_code=status_code, headers=headers)


@router.post("", response_model=VideoDetail, status_code=status.HTTP_201_CREATED)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    title: str = Form(..., min_length=1, max_length=255),
    publisher: str = Form(..., min_length=1, max_length=128),
    producer: str = Form("", max_length=128),
    genre: str = Form(..., min_length=1, max_length=64),
    age_rating: AgeRating = Form(AgeRating.U),
    description: str = Form("", max_length=2000),
    user: User = Depends(require_role(Role.CREATOR, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    suffix = Path(file.filename or "").suffix.lower()
    content_type = (file.content_type or "").lower()
    if suffix not in ALLOWED_SUFFIXES or content_type not in settings.allowed_video_types:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported video format")

    fh = file.file
    fh.seek(0, 2)
    total_size = fh.tell()
    fh.seek(0)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if total_size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_mb} MB limit",
        )

    storage_key = f"videos/{uuid.uuid4().hex}{suffix}"
    storage.save(storage_key, fh, content_type)

    video = Video(
        title=title,
        publisher=publisher,
        producer=producer,
        genre=genre,
        age_rating=age_rating,
        description=description,
        storage_key=storage_key,
        content_type=content_type,
        status=VideoStatus.PROCESSING,
        uploader_id=user.id,
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    background_tasks.add_task(_process_video, video.id)
    cache.invalidate_prefix("videos:list:")

    agg = _aggregate(db, [video.id]).get(video.id, {})
    return _serialize(video, agg, include_detail=True)


def _process_video(video_id: int) -> None:
    db = SessionLocal()
    source_path: Optional[Path] = None
    thumb_local: Optional[Path] = None
    transcode_path: Optional[Path] = None
    try:
        video = db.get(Video, video_id)
        if video is None:
            return
        try:
            source_path = materialise_local_path(storage, video.storage_key)
            if source_path is None:
                video.status = VideoStatus.FAILED
                db.commit()
                return

            duration, size_bytes = processor.probe(source_path)

            transcode_path = Path(source_path.parent) / f"trans-{video_id}.mp4"
            if processor.transcode(source_path, transcode_path):
                with open(transcode_path, "rb") as fh:
                    storage.save(video.storage_key, fh, "video/mp4")
                video.content_type = "video/mp4"
                video.size_bytes = transcode_path.stat().st_size
                video.duration_seconds = duration
                thumb_source = transcode_path
            else:
                video.size_bytes = size_bytes
                video.duration_seconds = duration
                thumb_source = source_path

            thumb_key = f"thumbnails/{video_id}.jpg"
            thumb_local = Path(thumb_source.parent) / f"thumb-{video_id}.jpg"
            if processor.make_thumbnail(thumb_source, thumb_local):
                with open(thumb_local, "rb") as fh:
                    storage.save(thumb_key, fh, "image/jpeg")
                video.thumbnail_key = thumb_key

            video.status = VideoStatus.READY
        except Exception:
            video.status = VideoStatus.FAILED
        db.commit()
        cache.invalidate_prefix("videos:list:")
    finally:
        for tmp in (thumb_local, transcode_path):
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
        if not isinstance(storage, LocalStorageBackend) and source_path is not None:
            source_path.unlink(missing_ok=True)
        db.close()
