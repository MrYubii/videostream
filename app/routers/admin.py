from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_role
from app.models import Comment, Rating, Role, User, Video
from app.repositories import UserRepository
from app.schemas import CreatorCreateRequest, CreatorUpdate, StatsOut, UserOut
from app.services.auth import AuthService

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_role(Role.ADMIN))])


def get_user_repo(db: Session = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(UserRepository(db))


@router.get("/stats", response_model=StatsOut)
def get_stats(db: Session = Depends(get_db), users: UserRepository = Depends(get_user_repo)):
    return StatsOut(
        total_creators=users.count_by_role(Role.CREATOR),
        total_videos=db.query(Video).count(),
        total_views=int(db.query(func.sum(Video.view_count)).scalar() or 0),
        total_comments=db.query(Comment).count(),
        total_ratings=db.query(Rating).count(),
    )


@router.post("/creators", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_creator(payload: CreatorCreateRequest, service: AuthService = Depends(get_auth_service)):
    return service.create_creator(payload)


@router.get("/creators", response_model=list[UserOut])
def list_creators(users: UserRepository = Depends(get_user_repo)):
    return users.list_by_role(Role.CREATOR)


@router.patch("/creators/{creator_id}", response_model=UserOut)
def update_creator(
    creator_id: int,
    payload: CreatorUpdate,
    users: UserRepository = Depends(get_user_repo),
    user: User = Depends(get_current_user),
):
    creator = users.get(creator_id)
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
    return users.save(creator)
