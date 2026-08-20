from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_optional_user
from app.models import Reaction, ReactionType, User, Video
from app.schemas import ReactionOut, ReactionPut

router = APIRouter(prefix="/api/videos", tags=["reactions"])


def _counts(db: Session, video_id: int) -> tuple[int, int]:
    rows = (
        db.query(Reaction.reaction, func.count(Reaction.id))
        .filter(Reaction.video_id == video_id)
        .group_by(Reaction.reaction)
        .all()
    )
    by_type = {reaction: count for reaction, count in rows}
    like_count = int(by_type.get(ReactionType.LIKE, 0))
    dislike_count = int(by_type.get(ReactionType.DISLIKE, 0))
    return like_count, dislike_count


@router.get("/{video_id}/reaction", response_model=ReactionOut)
def get_reaction(
    video_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    like_count, dislike_count = _counts(db, video_id)
    user_reaction = None
    if user is not None:
        mine = db.query(Reaction).filter(Reaction.video_id == video_id, Reaction.user_id == user.id).first()
        user_reaction = mine.reaction if mine else None

    return ReactionOut(video_id=video_id, like_count=like_count, dislike_count=dislike_count, user_reaction=user_reaction)


@router.put("/{video_id}/reaction", response_model=ReactionOut)
def put_reaction(
    video_id: int,
    payload: ReactionPut,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if db.get(Video, video_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    reaction = db.query(Reaction).filter(Reaction.video_id == video_id, Reaction.user_id == user.id).first()
    if payload.reaction is None:
        if reaction is not None:
            db.delete(reaction)
    elif reaction is None:
        db.add(Reaction(video_id=video_id, user_id=user.id, reaction=payload.reaction))
    else:
        reaction.reaction = payload.reaction
    db.commit()

    like_count, dislike_count = _counts(db, video_id)
    return ReactionOut(video_id=video_id, like_count=like_count, dislike_count=dislike_count, user_reaction=payload.reaction)