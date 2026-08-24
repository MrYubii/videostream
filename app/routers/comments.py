from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Comment, User, Video
from app.repositories import CommentRepository
from app.schemas import CommentCreate, CommentOut

router = APIRouter(prefix="/api/videos", tags=["comments"])


def get_comments(db: Session = Depends(get_db)) -> CommentRepository:
    return CommentRepository(db)


@router.get("/{video_id}/comments", response_model=list[CommentOut])
def list_comments(video_id: int, db: Session = Depends(get_db), comments: CommentRepository = Depends(get_comments)):
    if db.get(Video, video_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    return [
        CommentOut(
            id=c.id,
            body=c.body,
            video_id=c.video_id,
            author=c.user.username if c.user else "",
            created_at=c.created_at,
        )
        for c in comments.list_for_video(video_id)
    ]


@router.post("/{video_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def create_comment(
    video_id: int,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    comments: CommentRepository = Depends(get_comments),
    user: User = Depends(get_current_user),
):
    if db.get(Video, video_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    comment = comments.add(Comment(video_id=video_id, user_id=user.id, body=payload.body))
    return CommentOut(
        id=comment.id,
        body=comment.body,
        video_id=comment.video_id,
        author=user.username,
        created_at=comment.created_at,
    )
