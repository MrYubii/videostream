import os
import subprocess
import sys
import tempfile
from pathlib import Path

import imageio_ffmpeg
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_ROOT = Path(tempfile.mkdtemp(prefix="vs-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["MEDIA_ROOT"] = str(TEST_ROOT / "media")
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["CACHE_TTL_SECONDS"] = "0"
os.environ["RATE_LIMIT_REQUESTS"] = "10000"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402
from app.security import hash_password  # noqa: E402


@pytest.fixture(scope="session")
def client():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    users = [
        ("admin_seed", "admin_seed@example.com", "AdminPass123!", Role.ADMIN),
        ("creator_x", "creator_x@example.com", "CreatorPass9!", Role.CREATOR),
        ("alice", "alice@example.com", "ConsumerPass1!", Role.CONSUMER),
    ]
    for username, email, password, role in users:
        if not db.query(User).filter(User.username == username).first():
            db.add(User(username=username, email=email, password_hash=hash_password(password), role=role))
    db.commit()
    db.close()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def sample_video():
    path = TEST_ROOT / "sample.mp4"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [
            ffmpeg, "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
            str(path),
        ],
        capture_output=True,
        check=True,
        timeout=120,
    )
    return path
