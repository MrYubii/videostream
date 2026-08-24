from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_optional_user
from app.models import Rating, User, Video
from app.repositories import RatingRepository
from app.schemas import RatingOut, RatingPut

router = APIRouter(prefix="/api/videos", tags=["ratings"])


def get_ratings(db: Session = Depends(get_db)) -> RatingRepository:
    return RatingRepository(db)


@router.get("/{video_id}/rating", response_model=RatingOut)
def get_rating(
    video_id: int,
    db: Session = Depends(get_db),
    ratings: RatingRepository = Depends(get_ratings),
    user: User | None = Depends(get_optional_user),
):
    if db.get(Video, video_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    average, count = ratings.summary(video_id)
    user_rating = None
    if user is not None:
        mine = ratings.get_for_user(video_id, user.id)
        user_rating = mine.value if mine else None
    return RatingOut(video_id=video_id, average=average, count=count, user_rating=user_rating)


@router.put("/{video_id}/rating", response_model=RatingOut)
def put_rating(
    video_id: int,
    payload: RatingPut,
    db: Session = Depends(get_db),
    ratings: RatingRepository = Depends(get_ratings),
    user: User = Depends(get_current_user),
):
    if db.get(Video, video_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    rating = ratings.get_for_user(video_id, user.id)
    if rating is None:
        ratings.add_or_update(Rating(video_id=video_id, user_id=user.id, value=payload.value))
    else:
        rating.value = payload.value
        ratings.save(rating)
    average, count = ratings.summary(video_id)
    return RatingOut(video_id=video_id, average=average, count=count, user_rating=payload.value)
