import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from slugify import slugify

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import AgeRating, Role, User, Video, VideoStatus
from app.security import hash_password
from app.services.media import MediaProcessor, _ffmpeg
from app.services.storage import get_storage_backend

settings = get_settings()
storage = get_storage_backend()
processor = MediaProcessor()

SAMPLE_VIDEOS = [
    {
        "title": "Neon City After Dark",
        "publisher": "Aurora Studios",
        "producer": "J. Malik",
        "genre": "Music",
        "age_rating": AgeRating.PG,
        "description": "A cinematic test sequence exploring a synthetic neon skyline.",
        "seconds": 6,
        "color": "red",
    },
    {
        "title": "The 5 Second Workout",
        "publisher": "Peak Fitness",
        "producer": "L. Chen",
        "genre": "Sports",
        "age_rating": AgeRating.U,
        "description": "Everything you need for a quick daily routine.",
        "seconds": 5,
        "color": "green",
    },
    {
        "title": "Coding at 3AM",
        "publisher": "DevBits",
        "producer": "A. Okafor",
        "genre": "Education",
        "age_rating": AgeRating.PG,
        "description": "Late-night debugging session, screen-lights only.",
        "seconds": 6,
        "color": "blue",
    },
    {
        "title": "Wild Street Food Tour",
        "publisher": "Nomad Kitchen",
        "producer": "R. Silva",
        "genre": "Food",
        "age_rating": AgeRating.U,
        "description": "Tasting highlights from a midnight food market.",
        "seconds": 4,
        "color": "yellow",
    },
    {
        "title": "Horror Short: The Basement",
        "publisher": "Nightlight Films",
        "producer": "M. Voss",
        "genre": "Film",
        "age_rating": AgeRating.EIGHTEEN,
        "description": "A very short experiment in tension.",
        "seconds": 5,
        "color": "purple",
    },
]


def render_sample(path: Path, seconds: int, color: str) -> bool:
    ffmpeg = _ffmpeg()
    base = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=30:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
    ]
    tail = ["-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)]
    for video_codec in ("libx264", "mpeg4"):
        try:
            result = subprocess.run(base + ["-c:v", video_codec] + tail, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and path.exists() and path.stat().st_size > 0:
                return True
        except (subprocess.TimeoutExpired, OSError):
            continue
    return False


def upsert_user(db, username, email, password, role, full_name=""):
    user = db.query(User).filter(User.username == username).first()
    if user:
        return user
    user = User(
        username=username,
        email=email,
        full_name=full_name,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def seed_video(db, creator, spec, replace: bool):
    existing = db.query(Video).filter(Video.title == spec["title"]).first()
    if existing and not replace:
        print(f"  skip: {spec['title']} (already present)")
        return existing

    if existing:
        storage.delete(existing.storage_key)
        if existing.thumbnail_key:
            storage.delete(existing.thumbnail_key)
        db.delete(existing)
        db.commit()

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "sample.mp4"
        if not render_sample(source, spec["seconds"], spec["color"]):
            raise RuntimeError("Could not render a sample video with the bundled ffmpeg")

        slug = slugify(spec["title"]) or "sample"
        storage_key = f"videos/{slug}.mp4"
        with open(source, "rb") as fh:
            storage.save(storage_key, fh, "video/mp4")

        duration, size_bytes = processor.probe(source)
        thumb_key = f"thumbnails/{slug}.jpg"
        thumb_local = Path(tmp) / "thumb.jpg"
        has_thumb = False
        if processor.make_thumbnail(source, thumb_local):
            with open(thumb_local, "rb") as fh:
                storage.save(thumb_key, fh, "image/jpeg")
            has_thumb = True

        video = Video(
            title=spec["title"],
            publisher=spec["publisher"],
            producer=spec["producer"],
            genre=spec["genre"],
            age_rating=spec["age_rating"],
            description=spec["description"],
            storage_key=storage_key,
            thumbnail_key=thumb_key if has_thumb else "",
            content_type="video/mp4",
            size_bytes=size_bytes,
            duration_seconds=duration,
            status=VideoStatus.READY,
            uploader_id=creator.id,
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        print(f"  ok: {spec['title']} ({duration}s, {size_bytes} bytes)")
        return video


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed VideoStream with users and sample videos")
    parser.add_argument("--replace-videos", action="store_true", help="Recreate sample videos if they exist")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        print("Seeding users...")
        admin = upsert_user(
            db, "admin", "admin@videostream.example", "AdminPass123!",
            Role.ADMIN, "Platform Administrator",
        )
        creators = []
        for i, (username, email, full_name) in enumerate([
            ("creator_one", "creator.one@videostream.example", "Creator One"),
            ("creator_two", "creator.two@videostream.example", "Creator Two"),
        ]):
            creators.append(upsert_user(db, username, email, f"CreatorPass{i + 1}!", Role.CREATOR, full_name))
        consumer = upsert_user(
            db, "consumer_demo", "consumer@videostream.example", "ConsumerPass1!",
            Role.CONSUMER, "Demo Consumer",
        )

        print("Seeding sample videos...")
        creator_passwords = ["CreatorPass1!", "CreatorPass2!"]
        for i, spec in enumerate(SAMPLE_VIDEOS):
            seed_video(db, creators[i % len(creators)], spec, args.replace_videos)

        print("\nDone. Credentials:")
        print(f"  admin    -> {admin.username} / AdminPass123!")
        for i, c in enumerate(creators):
            print(f"  creator  -> {c.username} / {creator_passwords[i]}")
        print(f"  consumer -> {consumer.username} / ConsumerPass1!")
        print("\nStart the app with:  uvicorn app.main:app --reload")
    finally:
        db.close()


if __name__ == "__main__":
    main()
