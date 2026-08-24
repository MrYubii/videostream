from fastapi import HTTPException, status

from app.models import Role, User
from app.repositories import UserRepository
from app.schemas import CreatorCreateRequest, LoginRequest, RegisterRequest
from app.security import create_access_token, create_refresh_token, hash_password, verify_password


class AuthService:
    """Business/application tier for consumer and creator authentication."""

    def __init__(self, users: UserRepository) -> None:
        self.users = users

    def register_consumer(self, payload: RegisterRequest) -> User:
        if self.users.username_exists(payload.username):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
        if self.users.email_exists(payload.email):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        return self.users.add(
            User(
                username=payload.username,
                email=payload.email,
                full_name=payload.full_name,
                password_hash=hash_password(payload.password),
                role=Role.CONSUMER,
            )
        )

    def create_creator(self, payload: CreatorCreateRequest) -> User:
        """Creator enrolment is deliberately admin-only per the coursework brief."""
        if self.users.username_exists(payload.username):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
        if self.users.email_exists(payload.email):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        return self.users.add(
            User(
                username=payload.username,
                email=payload.email,
                full_name=payload.full_name,
                password_hash=hash_password(payload.password),
                role=Role.CREATOR,
            )
        )

    def login(self, payload: LoginRequest) -> tuple[str, str, User]:
        user = self.users.get_by_username(payload.username)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
        return create_access_token(user.id, user.role.value), create_refresh_token(user.id), user
