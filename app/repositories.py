from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Comment, Rating, Reaction, Role, User, Video, VideoStatus


class UserRepository:
    """Data-access tier for users. Business rules stay in services/routers."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, user_id: int) -> Optional[User]:
        return self.db.get(User, user_id)

    def get_by_username(self, username: str) -> Optional[User]:
        return self.db.query(User).filter(User.username == username).first()

    def username_exists(self, username: str) -> bool:
        return self.db.query(User).filter(func.lower(User.username) == username.lower()).first() is not None

    def email_exists(self, email: str) -> bool:
        return self.db.query(User).filter(func.lower(User.email) == email.lower()).first() is not None

    def list_by_role(self, role: Role) -> list[User]:
        return self.db.query(User).filter(User.role == role).order_by(User.created_at).all()

    def count_by_role(self, role: Role) -> int:
        return self.db.query(User).filter(User.role == role).count()

    def add(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def save(self, user: User) -> User:
        self.db.commit()
        self.db.refresh(user)
        return user


class VideoRepository:
    """Data-access tier for videos and read-side aggregates."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, video_id: int) -> Optional[Video]:
        return self.db.get(Video, video_id)

    def list_ready(
        self,
        *,
        search: str,
        genre: str,
        age_rating,
        sort: str,
        offset: int,
        limit: int,
    ) -> tuple[int, list[Video]]:
        query = self.db.query(Video).filter(Video.status == VideoStatus.READY)
        if search:
            like = f"%{search}%"
            query = query.filter(
                (Video.title.ilike(like, escape="\\"))
                | (Video.publisher.ilike(like, escape="\\"))
                | (Video.producer.ilike(like, escape="\\"))
                | (Video.genre.ilike(like, escape="\\"))
            )
        if genre:
            query = query.filter(Video.genre == genre)
        if age_rating:
            query = query.filter(Video.age_rating == age_rating)

        total = query.count()
        if sort == "popular":
            query = query.order_by(Video.view_count.desc(), Video.created_at.desc())
        else:
            query = query.order_by(Video.created_at.desc())
        return total, query.offset(offset).limit(limit).all()

    def aggregate(self, video_ids: list[int]) -> dict[int, dict]:
        if not video_ids:
            return {}
        rating_rows = (
            self.db.query(Rating.video_id, func.avg(Rating.value), func.count(Rating.id))
            .filter(Rating.video_id.in_(video_ids))
            .group_by(Rating.video_id)
            .all()
        )
        comment_rows = (
            self.db.query(Comment.video_id, func.count(Comment.id))
            .filter(Comment.video_id.in_(video_ids))
            .group_by(Comment.video_id)
            .all()
        )
        reaction_rows = (
            self.db.query(Reaction.video_id, Reaction.reaction, func.count(Reaction.id))
            .filter(Reaction.video_id.in_(video_ids))
            .group_by(Reaction.video_id, Reaction.reaction)
            .all()
        )
        aggregates: dict[int, dict] = {}
        for video_id, avg, count in rating_rows:
            aggregates.setdefault(video_id, {}).update(rating_average=round(float(avg), 1), rating_count=count)
        for video_id, count in comment_rows:
            aggregates.setdefault(video_id, {}).update(comment_count=count)
        for video_id, reaction, count in reaction_rows:
            aggregates.setdefault(video_id, {})[f"{reaction.value}_count"] = count
        return aggregates

    def add(self, video: Video) -> Video:
        self.db.add(video)
        self.db.commit()
        self.db.refresh(video)
        return video

    def save(self, video: Video) -> Video:
        self.db.commit()
        self.db.refresh(video)
        return video

    def delete(self, video: Video) -> None:
        self.db.delete(video)
        self.db.commit()

    def increment_view(self, video_id: int) -> None:
        self.db.query(Video).filter(Video.id == video_id).update({Video.view_count: Video.view_count + 1})
        self.db.commit()


class CommentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_video(self, video_id: int) -> list[Comment]:
        return self.db.query(Comment).filter(Comment.video_id == video_id).order_by(Comment.created_at).all()

    def add(self, comment: Comment) -> Comment:
        self.db.add(comment)
        self.db.commit()
        self.db.refresh(comment)
        return comment

    def count(self) -> int:
        return self.db.query(Comment).count()


class RatingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_for_user(self, video_id: int, user_id: int) -> Optional[Rating]:
        return self.db.query(Rating).filter(Rating.video_id == video_id, Rating.user_id == user_id).first()

    def summary(self, video_id: int) -> tuple[float, int]:
        row = self.db.query(func.avg(Rating.value), func.count(Rating.id)).filter(Rating.video_id == video_id).one()
        return (round(float(row[0]), 1) if row[0] is not None else 0.0, int(row[1] or 0))

    def add_or_update(self, rating: Rating) -> Rating:
        self.db.add(rating)
        self.db.commit()
        self.db.refresh(rating)
        return rating

    def save(self, rating: Rating) -> Rating:
        self.db.commit()
        self.db.refresh(rating)
        return rating

    def count(self) -> int:
        return self.db.query(Rating).count()


class ReactionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_for_user(self, video_id: int, user_id: int) -> Optional[Reaction]:
        return self.db.query(Reaction).filter(Reaction.video_id == video_id, Reaction.user_id == user_id).first()

    def counts(self, video_id: int) -> tuple[int, int]:
        rows = (
            self.db.query(Reaction.reaction, func.count(Reaction.id))
            .filter(Reaction.video_id == video_id)
            .group_by(Reaction.reaction)
            .all()
        )
        by_type = {reaction: count for reaction, count in rows}
        from app.models import ReactionType
        return int(by_type.get(ReactionType.LIKE, 0)), int(by_type.get(ReactionType.DISLIKE, 0))

    def add(self, reaction: Reaction) -> Reaction:
        self.db.add(reaction)
        self.db.commit()
        self.db.refresh(reaction)
        return reaction

    def save(self, reaction: Reaction) -> Reaction:
        self.db.commit()
        self.db.refresh(reaction)
        return reaction

    def delete(self, reaction: Reaction) -> None:
        self.db.delete(reaction)
        self.db.commit()
