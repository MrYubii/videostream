import enum
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _enum_values(cls):
    return [m.value for m in cls]


class Role(str, enum.Enum):
    ADMIN = "admin"
    CREATOR = "creator"
    CONSUMER = "consumer"


class AgeRating(str, enum.Enum):
    U = "U"
    PG = "PG"
    TWELVE = "12"
    FIFTEEN = "15"
    EIGHTEEN = "18"


class VideoStatus(str, enum.Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ReactionType(str, enum.Enum):
    LIKE = "like"
    DISLIKE = "dislike"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(
        Enum(Role, values_callable=_enum_values, native_enum=False, name="role"),
        nullable=False,
        default=Role.CONSUMER,
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    videos: Mapped[list["Video"]] = relationship(back_populates="uploader")
    comments: Mapped[list["Comment"]] = relationship(back_populates="user")
    ratings: Mapped[list["Rating"]] = relationship(back_populates="user")
    reactions: Mapped[list["Reaction"]] = relationship(back_populates="user")


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    publisher: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    producer: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    genre: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    age_rating: Mapped[AgeRating] = mapped_column(
        Enum(AgeRating, values_callable=_enum_values, native_enum=False, name="age_rating"),
        nullable=False,
        default=AgeRating.U,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_key: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, default="video/mp4")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, values_callable=_enum_values, native_enum=False, name="status"),
        nullable=False,
        default=VideoStatus.PROCESSING,
    )
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    uploader: Mapped["User"] = relationship(back_populates="videos")
    comments: Mapped[list["Comment"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    ratings: Mapped[list["Rating"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    reactions: Mapped[list["Reaction"]] = relationship(back_populates="video", cascade="all, delete-orphan")


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    video: Mapped["Video"] = relationship(back_populates="comments")
    user: Mapped["User"] = relationship(back_populates="comments")


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("video_id", "user_id", name="uq_rating_video_user"),
        CheckConstraint("value >= 1 AND value <= 5", name="ck_rating_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    video: Mapped["Video"] = relationship(back_populates="ratings")
    user: Mapped["User"] = relationship(back_populates="ratings")


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (
        UniqueConstraint("video_id", "user_id", name="uq_reaction_video_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reaction: Mapped[ReactionType] = mapped_column(
        Enum(ReactionType, values_callable=_enum_values, native_enum=False, name="reaction_type"),
        nullable=False,
    )
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    video: Mapped["Video"] = relationship(back_populates="reactions")
    user: Mapped["User"] = relationship(back_populates="reactions")
