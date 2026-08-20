from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_optional_user
from app.models import Rating, User, Video
from app.schemas import RatingOut, RatingPut

router = APIRouter(prefix="/api/videos", tags=["ratings"])


@router.get("/{video_id}/rating", response_model=RatingOut)
def get_rating(
    video_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    row = (
        db.query(func.avg(Rating.value), func.count(Rating.id))
        .filter(Rating.video_id == video_id)
        .one()
    )
    average = round(float(row[0]), 1) if row[0] is not None else 0.0
    count = int(row[1] or 0)

    user_rating = None
    if user is not None:
        mine = db.query(Rating).filter(Rating.video_id == video_id, Rating.user_id == user.id).first()
        user_rating = mine.value if mine else None

    return RatingOut(video_id=video_id, average=average, count=count, user_rating=user_rating)


@router.put("/{video_id}/rating", response_model=RatingOut)
def put_rating(
    video_id: int,
    payload: RatingPut,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if db.get(Video, video_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    rating = db.query(Rating).filter(Rating.video_id == video_id, Rating.user_id == user.id).first()
    if rating is None:
        rating = Rating(video_id=video_id, user_id=user.id, value=payload.value)
        db.add(rating)
    else:
        rating.value = payload.value
    db.commit()

    row = (
        db.query(func.avg(Rating.value), func.count(Rating.id))
        .filter(Rating.video_id == video_id)
        .one()
    )
    average = round(float(row[0]), 1) if row[0] is not None else 0.0
    count = int(row[1] or 0)
    return RatingOut(video_id=video_id, average=average, count=count, user_rating=payload.value)
