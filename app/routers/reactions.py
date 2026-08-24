from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_optional_user
from app.models import Reaction, User, Video
from app.repositories import ReactionRepository
from app.schemas import ReactionOut, ReactionPut

router = APIRouter(prefix="/api/videos", tags=["reactions"])


def get_reactions(db: Session = Depends(get_db)) -> ReactionRepository:
    return ReactionRepository(db)


@router.get("/{video_id}/reaction", response_model=ReactionOut)
def get_reaction(
    video_id: int,
    db: Session = Depends(get_db),
    reactions: ReactionRepository = Depends(get_reactions),
    user: User | None = Depends(get_optional_user),
):
    if db.get(Video, video_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    like_count, dislike_count = reactions.counts(video_id)
    user_reaction = None
    if user is not None:
        mine = reactions.get_for_user(video_id, user.id)
        user_reaction = mine.reaction if mine else None
    return ReactionOut(video_id=video_id, like_count=like_count, dislike_count=dislike_count, user_reaction=user_reaction)


@router.put("/{video_id}/reaction", response_model=ReactionOut)
def put_reaction(
    video_id: int,
    payload: ReactionPut,
    db: Session = Depends(get_db),
    reactions: ReactionRepository = Depends(get_reactions),
    user: User = Depends(get_current_user),
):
    if db.get(Video, video_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    reaction = reactions.get_for_user(video_id, user.id)
    if payload.reaction is None:
        if reaction is not None:
            reactions.delete(reaction)
    elif reaction is None:
        reactions.add(Reaction(video_id=video_id, user_id=user.id, reaction=payload.reaction))
    else:
        reaction.reaction = payload.reaction
        reactions.save(reaction)
    like_count, dislike_count = reactions.counts(video_id)
    return ReactionOut(video_id=video_id, like_count=like_count, dislike_count=dislike_count, user_reaction=payload.reaction)
