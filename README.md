# VideoStream — Scalable Video Sharing Platform

A cloud-native, TikTok-style video sharing web application built with **FastAPI** (Python 3.11+). Features role-based access (Admin / Creator / Consumer), JWT authentication, video upload with background transcoding & thumbnail generation, searchable dashboard, comments, star ratings, and HTTP Range streaming.

---

## Features

- **Three roles** — Admin manages creators; Creators upload videos with metadata (Title, Publisher, Producer, Genre, Age Rating); Consumers sign up, browse, search, watch, comment, and rate.
- **REST API + Static Frontend** — FastAPI serves OpenAPI docs at `/docs`; static HTML/CSS/JS under `/static` mounted at root (`/`) for a complete single-origin experience.
- **Scalable storage abstraction** — `StorageBackend` interface with `LocalStorageBackend` (filesystem), `AzureBlobStorageBackend`, and `S3StorageBackend` implementations. Swap via config for cloud deployment.
- **Media processing pipeline** — Background task probes duration (ffprobe) and generates a poster thumbnail using the bundled `imageio-ffmpeg` binary (no system ffmpeg required).
- **HTTP Range streaming** — Video playback supports seeking via standard `Range` header (open-ended and suffix ranges included); unsatisfiable ranges return `416`; works with all backends (local file seek, Azure ranged download, S3 ranged GET).
- **Video management** — Uploaders and admins can edit metadata or delete videos (media, thumbnail, comments, ratings cleaned up).
- **Caching & rate limiting** — In-memory TTL cache (`TTLCache`) for dashboard/search lists; sliding-window rate limiter on API endpoints (static/media/streaming excluded so playback never stalls).
- **Zero-config local dev** — `./scripts/run.ps1` creates venv, installs deps, seeds demo users + 5 sample videos, starts server with hot reload.
- **Admin analytics** — `/api/admin/stats` powers a summary dashboard (creators, videos, views, comments, ratings).
- **Test suite** — 31 pytest tests covering auth, roles, upload/process/stream, range streaming edge cases, video management, admin actions, static serving, and OpenAPI.

---

## Quick Start (Windows / PowerShell)

```powershell
# From the project root
.\scripts\run.ps1
```

This will:
1. Create `.venv` and install dependencies from `requirements.txt`
2. Seed the database (`data/videostream.db`) with:
   - **Admin**: `admin` / `AdminPass123!`
   - **Creators**: `creator_one` / `CreatorPass1!`, `creator_two` / `CreatorPass2!`
   - **Consumer**: `consumer_demo` / `ConsumerPass1!`
   - 5 sample videos (auto-generated test patterns with audio)
3. Start Uvicorn at `http://localhost:8000`

**Open in browser:**
- Dashboard: `http://localhost:8000/`
- API docs (Swagger): `http://localhost:8000/docs`
- Admin panel: `http://localhost:8000/admin.html` (sign in as admin)

**Linux / macOS:** use `./scripts/run.sh` (same behaviour).

---

## Demo Credentials

| Role      | Username        | Password        | Capabilities                                   |
|-----------|-----------------|-----------------|------------------------------------------------|
| Admin     | `admin`         | `AdminPass123!` | Create/disable creators, view all              |
| Creator   | `creator_one`   | `CreatorPass1!` | Upload videos, full metadata                   |
| Creator   | `creator_two`   | `CreatorPass2!` | Upload videos                                  |
| Consumer  | `consumer_demo` | `ConsumerPass1!`| Browse, search, watch, comment, rate           |

---

## Project Structure

```
videostream/
├── .env.example              # Copy to .env and customise
├── .gitignore
├── requirements.txt
├── README.md
├── scripts/
│   ├── run.ps1               # Windows launcher (venv + seed + server)
│   ├── run.sh                # Linux/macOS launcher
│   └── seed.py               # Creates demo users & sample videos
├── tests/
│   ├── conftest.py           # Test fixtures (temp DB, sample video)
│   └── test_api.py           # 18 integration tests
├── docs/
│   ├── ARCHITECTURE.md       # System design, data flow, scalability
│   ├── API.md                # Full REST reference with examples
│   └── DEPLOYMENT.md         # Azure deployment guide (Task 2)
└── app/
    ├── main.py               # FastAPI app, lifespan, middleware, static mounts
    ├── config.py             # Pydantic Settings (.env driven)
    ├── database.py           # SQLAlchemy engine / session
    ├── models.py             # User, Video, Comment, Rating (+ enums)
    ├── schemas.py            # Pydantic request/response models
    ├── security.py           # bcrypt password hashing + JWT
    ├── deps.py               # FastAPI dependencies (auth, roles, optional user)
    ├── routers/
    │   ├── auth.py           # /api/auth/register, /login, /me
    │   ├── admin.py          # /api/admin/creators (CRUD)
    │   ├── videos.py         # /api/videos (list, detail, upload, stream)
    │   ├── comments.py       # /api/videos/{id}/comments
    │   └── ratings.py        # /api/videos/{id}/rating (GET/PUT)
    ├── services/
    │   ├── storage.py        # StorageBackend + Local / Azure / S3
    │   ├── media.py          # MediaProcessor (duration probe + thumbnail)
    │   ├── cache.py          # TTLCache (in-memory, thread-safe)
    │   └── ratelimit.py      # Sliding-window middleware
    └── static/
        ├── index.html        # Dashboard (search, filter, grid)
        ├── video.html        # Player + comments + rating
        ├── login.html        # Consumer sign-in
        ├── signup.html       # Consumer registration
        ├── admin.html        # Creator management
        ├── css/style.css     # Dark, responsive, TikTok-like UI
        └── js/
            ├── api.js        # Fetch wrapper + JWT handling
            ├── common.js     # Nav injection + auth state
            ├── app.js        # Dashboard logic
            ├── video.js      # Player page logic
            └── admin.js      # Admin page logic
```

---

## Configuration (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | `development` \| `production` |
| `SECRET_KEY` | *required* | JWT signing secret (long random string in prod) |
| `TOKEN_EXPIRY_MINUTES` | `120` | Access token lifetime |
| `DATABASE_URL` | `sqlite:///data/videostream.db` | SQLAlchemy URL (PostgreSQL, Azure SQL, etc. for cloud) |
| `STORAGE_BACKEND` | `local` | `local` \| `azure` \| `s3` |
| `MEDIA_ROOT` | `data/media` | Local filesystem root for uploads/thumbnails |
| `MAX_UPLOAD_MB` | `200` | Max upload size |
| `AZURE_CONNECTION_STRING` | — | Required if `STORAGE_BACKEND=azure` |
| `AZURE_CONTAINER` | `videos` | Blob container name |
| `S3_BUCKET` | — | Required if `STORAGE_BACKEND=s3` |
| `S3_REGION` | `eu-west-1` | AWS region |
| `CACHE_TTL_SECONDS` | `30` | Dashboard/list cache lifetime |
| `RATE_LIMIT_REQUESTS` | `30` | Max requests per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit window |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |

---

## Running Tests

```powershell
# From project root
.\.venv\Scripts\python.exe -m pytest tests -v
```

Expected: **31 passed**. Tests use a throw-away temp SQLite DB and an auto-generated 2-second test video (via `imageio-ffmpeg`), so no external dependencies.

---

## Development Notes

- **Hot reload**: `run.ps1` / `run.sh` pass `--reload` to Uvicorn; code changes restart the server automatically.
- **Database**: Local SQLite file at `data/videostream.db` (WAL mode, busy timeout, foreign keys enabled). Delete to reset; re-run `seed.py` to repopulate.
- **Sample videos**: Generated on-the-fly during seeding using `ffmpeg -f lavfi testsrc2` (colour bars) + sine tone. No external assets needed.
- **Upload processing**: `POST /api/videos` returns immediately with `status: "processing"`. Background task runs ffmpeg probe + thumbnail, then updates to `ready`. Poll `GET /api/videos/{id}` or refresh dashboard; the UI polls automatically after upload.
- **View counting**: A view is recorded at most once per 30 minutes per IP per video — byte-range requests during playback don't inflate the counter.
- **CORS**: Default `CORS_ORIGINS=*` disables credentialed CORS (credentials require an explicit origin allow-list). Set explicit origins in production.

---

## Cloud Deployment (Task 2)

See **`docs/DEPLOYMENT.md`** for a complete Azure guide:
- Azure App Service (Linux container or native Python)
- Azure Database for PostgreSQL / Azure SQL
- Azure Blob Storage (videos + thumbnails)
- Azure Cache for Redis (replace in-memory cache)
- Azure Front Door / Application Gateway (dynamic DNS + TLS)
- Optional: Azure Media Services for advanced transcoding, Entra ID for OIDC auth

---

## License

MIT — see `LICENSE.md` (if present).