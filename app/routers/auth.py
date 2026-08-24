from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.repositories import UserRepository
from app.schemas import LoginRequest, RegisterRequest, RefreshTokenRequest, TokenResponse, UserOut
from app.security import decode_refresh_token
from app.services.auth import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(UserRepository(db))


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, service: AuthService = Depends(get_auth_service)):
    """Public consumer registration. Creator enrolment remains admin-only."""
    return service.register_consumer(payload)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, service: AuthService = Depends(get_auth_service)):
    """Shared login for consumer and creator accounts (and administrators)."""
    access_token, refresh_token, user = service.login(payload)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, role=user.role.value, username=user.username)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshTokenRequest):
    """Refresh access token using refresh token."""
    try:
        decoded = decode_refresh_token(payload.refresh_token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    user_id = int(decoded["sub"])
    db = next(get_db())
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    
    from app.security import create_access_token, create_refresh_token
    new_access = create_access_token(user.id, user.role.value)
    new_refresh = create_refresh_token(user.id)
    return TokenResponse(access_token=new_access, refresh_token=new_refresh, role=user.role.value, username=user.username)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
