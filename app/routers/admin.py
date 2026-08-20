from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_role
from app.models import Comment, Rating, Role, User, Video
from app.schemas import CreatorCreateRequest, CreatorUpdate, StatsOut, UserOut
from app.security import hash_password

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_role(Role.ADMIN))])


@router.get("/stats", response_model=StatsOut)
def get_stats(db: Session = Depends(get_db)):
    return StatsOut(
        total_creators=db.query(User).filter(User.role == Role.CREATOR).count(),
        total_videos=db.query(Video).count(),
        total_views=int(db.query(func.sum(Video.view_count)).scalar() or 0),
        total_comments=db.query(Comment).count(),
        total_ratings=db.query(Rating).count(),
    )


@router.post("/creators", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_creator(payload: CreatorCreateRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(func.lower(User.username) == payload.username.lower()).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
    if db.query(User).filter(func.lower(User.email) == payload.email.lower()).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    creator = User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=Role.CREATOR,
    )
    db.add(creator)
    db.commit()
    db.refresh(creator)
    return creator


@router.get("/creators", response_model=list[UserOut])
def list_creators(db: Session = Depends(get_db)):
    return db.query(User).filter(User.role == Role.CREATOR).order_by(User.created_at).all()


@router.patch("/creators/{creator_id}", response_model=UserOut)
def update_creator(
    creator_id: int,
    payload: CreatorUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    creator = db.get(User, creator_id)
    if creator is None or creator.role not in (Role.CREATOR, Role.CONSUMER):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")
    if creator.id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify your own account here")
    if payload.role is not None:
        if payload.role == Role.ADMIN:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot grant the admin role")
        creator.role = payload.role
    if payload.is_active is not None:
        creator.is_active = payload.is_active
    db.commit()
    db.refresh(creator)
    return creator
