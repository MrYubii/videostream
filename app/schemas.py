from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import AgeRating, ReactionType, Role, VideoStatus


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=128)

    @field_validator("username")
    @classmethod
    def username_alnum(cls, v: str) -> str:
        if not v.replace("_", "").isalnum():
            raise ValueError("username may only contain letters, digits and underscores")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime


class CreatorCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=128)

    @field_validator("username")
    @classmethod
    def username_alnum(cls, v: str) -> str:
        if not v.replace("_", "").isalnum():
            raise ValueError("username may only contain letters, digits and underscores")
        return v


class CreatorUpdate(BaseModel):
    is_active: Optional[bool] = None
    role: Optional[Role] = None


class VideoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    publisher: str = Field(min_length=1, max_length=128)
    producer: str = Field(default="", max_length=128)
    genre: str = Field(min_length=1, max_length=64)
    age_rating: AgeRating = AgeRating.U
    description: str = Field(default="", max_length=2000)


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    publisher: str
    producer: str
    genre: str
    age_rating: AgeRating
    description: str
    thumbnail_url: str
    duration_seconds: int
    status: VideoStatus
    view_count: int
    uploader: str
    created_at: datetime
    rating_average: Optional[float] = None
    rating_count: int = 0
    comment_count: int = 0
    like_count: int = 0
    dislike_count: int = 0


class VideoDetail(VideoOut):
    stream_url: str = ""
    size_bytes: int = 0
    content_type: str = ""


class VideoUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    publisher: Optional[str] = Field(default=None, min_length=1, max_length=128)
    producer: Optional[str] = Field(default=None, max_length=128)
    genre: Optional[str] = Field(default=None, min_length=1, max_length=64)
    age_rating: Optional[AgeRating] = None
    description: Optional[str] = Field(default=None, max_length=2000)


class VideoList(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[VideoOut]


class StatsOut(BaseModel):
    total_creators: int
    total_videos: int
    total_views: int
    total_comments: int
    total_ratings: int


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    body: str
    video_id: int
    author: str
    created_at: datetime


class RatingPut(BaseModel):
    value: int = Field(ge=1, le=5)


class RatingOut(BaseModel):
    video_id: int
    average: float
    count: int
    user_rating: Optional[int] = None


class ReactionPut(BaseModel):
    reaction: Optional[ReactionType] = None


class ReactionOut(BaseModel):
    video_id: int
    like_count: int
    dislike_count: int
    user_reaction: Optional[ReactionType] = None
