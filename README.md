# VideoStream — Scalable Video Sharing Platform

A cloud-native, TikTok-style video sharing web application for **COM769 Scalable Advanced Software Solutions Coursework 2**. The solution uses **FastAPI + Python**, role-based JWT authentication, N-tier architecture, object storage abstraction, background media processing, HTTP Range streaming, caching, rate limiting, automated testing and Azure deployment.

## Coursework features

- **Consumer accounts** — public sign-up, login, browse/search/watch, comments, ratings and reactions.
- **Creator accounts** — created by an administrator, login through the shared JWT authentication service, upload videos and metadata.
- **Admin** — create/disable creators and view platform statistics.
- **Video metadata** — Title, Publisher, Producer, Genre, Age Rating and description.
- **Media processing** — FFmpeg duration probing, MP4 conversion and thumbnail generation.
- **HTTP Range streaming** — browser seeking and partial-content responses.
- **Cloud storage abstraction** — local filesystem, Azure Blob Storage and S3 implementations.
- **N-tier architecture** — presentation, application/business, data-access and infrastructure/persistence boundaries.
- **Scalability features** — stateless JWT API, TTL cache, rate limiting, GZip and object storage.
- **CI/CD** — GitHub Actions runs tests and deploys successful `main` changes to Azure App Service.

## Authentication model

| Role | Registration | Login | Upload | Admin management |
|---|---|---|---|---|
| Consumer | Public | Yes | No | No |
| Creator | Admin-created | Yes | Yes | No |
| Admin | Seeded/managed | Yes | Yes | Yes |

Creator enrolment is intentionally not public, matching the coursework specification.

## Project structure

```text
videostream/
├── .github/workflows/ci-cd.yml     # CI + Azure CD
├── .env.example
├── requirements.txt
├── scripts/
│   ├── run.ps1
│   ├── run.sh
│   └── seed.py
├── tests/
├── docs/
│   ├── ARCHITECTURE.md             # Final N-tier design
│   ├── API.md
│   └── DEPLOYMENT.md               # Azure + CI/CD guide
└── app/
    ├── main.py                     # application composition
    ├── config.py
    ├── database.py
    ├── models.py
    ├── repositories.py             # data-access tier
    ├── schemas.py                  # API DTOs
    ├── security.py
    ├── deps.py
    ├── routers/                    # presentation tier
    │   ├── auth.py
    │   ├── admin.py
    │   ├── videos.py
    │   ├── comments.py
    │   ├── ratings.py
    │   └── reactions.py
    ├── services/                   # application/infrastructure services
    │   ├── auth.py
    │   ├── storage.py
    │   ├── media.py
    │   ├── cache.py
    │   └── ratelimit.py
    └── static/
        ├── index.html
        ├── video.html
        ├── login.html
        ├── creator-login.html
        ├── signup.html
        └── admin.html
```

## Local quick start

Windows PowerShell:

```powershell
.\scripts\run.ps1
```

Linux/macOS:

```bash
./scripts/run.sh
```

The seed script creates demo roles/users and sample media for local demonstration.

Open:

```text
http://localhost:8000/
http://localhost:8000/docs
http://localhost:8000/admin.html
http://localhost:8000/creator-login.html
```

## Tests

```bash
python -m pytest tests -q
```

The test suite covers authentication, role restrictions, creator administration, upload/processing, streaming/range handling, comments, ratings, reactions, management, static serving and OpenAPI behaviour.

## Configuration

Copy `.env.example` to `.env` for local development. Production configuration belongs in Azure App Service settings or Key Vault.

Important settings:

```text
DATABASE_URL
STORAGE_BACKEND
AZURE_CONNECTION_STRING
AZURE_CONTAINER
SECRET_KEY
CORS_ORIGINS
MAX_UPLOAD_MB
CACHE_TTL_SECONDS
RATE_LIMIT_REQUESTS
RATE_LIMIT_WINDOW_SECONDS
```

## Azure deployment

The final deployment path is documented in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). It covers:

1. Resource group.
2. PostgreSQL Flexible Server.
3. Azure Blob Storage.
4. Linux/Python App Service.
5. FastAPI Gunicorn/Uvicorn startup command.
6. Production environment variables.
7. GitHub Actions CI/CD with Azure OpenID Connect.
8. Consumer/creator/admin validation.
9. Streaming/media validation.
10. Optional Azure Managed Redis and Front Door scale-out.

The architecture and rationale are documented in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Security notes

- Passwords are bcrypt-hashed.
- JWTs contain user identity and role with an expiry.
- Consumer registration cannot select a privileged role.
- Creator upload permissions are enforced on the server.
- Creator ownership is checked before video modification/deletion.
- Upload MIME type, extension and size are validated.
- Azure Blob can remain private; thumbnails are streamed through the API.
- Production secrets must never be committed to Git.

## Scalability limitations and roadmap

The coursework implementation is intentionally practical rather than a full commercial video platform. The main remaining production improvements are a durable distributed media-processing queue, Azure Managed Redis for multi-instance caching/rate limiting, Alembic migrations, stronger private networking and optional Front Door/WAF.
