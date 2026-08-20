# VideoStream — Architecture & Design

## 1. High-Level Overview

VideoStream is a **cloud-native** video sharing platform decomposed into loosely-coupled components that can run on a single VM (local dev) or scale horizontally across managed cloud services (Azure). The architecture follows **separation of concerns**:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ Dashboard    │  │ Video Player │  │ Admin Panel  │              │
│  │ (index.html) │  │ (video.html) │  │ (admin.html) │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
└─────────┼─────────────────┼─────────────────┼──────────────────────┘
          │                 │                 │
          │   HTTPS / REST  │                 │
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        FASTAPI APPLICATION                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ Auth Router │ │ Admin Router│ │ Videos Router│ │Comments/Rat.│   │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘   │
│         │              │              │              │            │
│         └──────────────┼──────────────┼──────────────┘            │
│                        ▼              ▼                           │
│         ┌─────────────────────────────────────────────┐           │
│         │           SERVICE LAYER                      │           │
│         │  ┌─────────┐ ┌──────────┐ ┌───────┐ ┌─────┐  │           │
│         │  │ Storage │ │  Media   │ │ Cache │ │Rate │  │           │
│         │  │ Backend │ │Processor │ │(TTL)  │ │Limit│  │           │
│         │  └────┬────┘ └────┬─────┘ └───┬───┘ └──┬──┘  │           │
│         └───────┼────────────┼───────────┼─────────┘           │
│                 ▼            ▼           ▼                     │
└─────────────────┼────────────┼───────────┼─────────────────────┘
                  │            │           │
        ┌─────────┴────┐  ┌────┴────┐ ┌────┴────┐
        │  DATABASE    │  │ STORAGE │ │  CACHE  │
        │  (SQL)       │  │ (Blob/  │ │ (Redis/ │
        │              │  │  FS)    │ │  Mem)   │
        └──────────────┘  └─────────┘ └─────────┘
```

**Key characteristics:**
- **Stateless API** — any instance can serve any request; session state in JWT.
- **Storage abstraction** — `StorageBackend` protocol enables zero-code migration from local FS to Azure Blob / S3.
- **Async media pipeline** — upload returns immediately; background task handles ffmpeg probe + thumbnail.
- **Cache-first reads** — dashboard & search hit `TTLCache` (in-memory locally; Redis in cloud) with 30s TTL.
- **Rate limiting** — sliding-window per-IP middleware protects auth & upload endpoints.

---

## 2. Data Model

```
User ──────< Video >────── Comment
  │           │              │
  │           │              │
  └──────< Rating >──────────┘
```

### Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `users` | Authentication & authorisation | `id`, `username` (UK), `email` (UK), `password_hash`, `role` (admin/creator/consumer), `is_active`, `created_at` |
| `videos` | Video metadata + storage pointers | `id`, `title`, `publisher`, `producer`, `genre`, `age_rating` (U/PG/12/15/18), `description`, `storage_key`, `thumbnail_key`, `content_type`, `size_bytes`, `duration_seconds`, `status` (processing/ready/failed), `view_count`, `uploader_id` (FK→users), `created_at` |
| `comments` | Per-video discussion | `id`, `video_id` (FK), `user_id` (FK), `body`, `created_at` |
| `ratings` | 1–5 star per user per video | `id`, `video_id` (FK), `user_id` (FK), `value` (1–5), `created_at`; **unique**(`video_id`,`user_id`) |

**Enums** (stored as VARCHAR with CHECK constraint via SQLAlchemy `Enum(native_enum=False)`):
- `Role`: `admin`, `creator`, `consumer`
- `AgeRating`: `U`, `PG`, `12`, `15`, `18`
- `VideoStatus`: `processing`, `ready`, `failed`

---

## 3. REST API Surface

| Area | Endpoints | Auth |
|------|-----------|------|
| **Auth** | `POST /api/auth/register` (consumer), `POST /api/auth/login`, `GET /api/auth/me` | Public / JWT |
| **Admin** | `POST /api/admin/creators`, `GET /api/admin/creators`, `PATCH /api/admin/creators/{id}` | JWT + `admin` role |
| **Videos** | `GET /api/videos` (list/search), `GET /api/videos/{id}`, `POST /api/videos` (upload), `GET /api/videos/{id}/stream` | Public / JWT (creator+ for upload) |
| **Comments** | `GET /api/videos/{id}/comments`, `POST /api/videos/{id}/comments` | Public / JWT |
| **Ratings** | `GET /api/videos/{id}/rating`, `PUT /api/videos/{id}/rating` | Public / JWT |

**OpenAPI docs** at `/docs` (Swagger UI) and `/openapi.json`.

---

## 4. Authentication & Authorisation

- **JWT (HS256)** — issued on login; payload: `sub` (user id), `role`, `iat`, `exp`.
- **Token lifetime** — configurable (`TOKEN_EXPIRY_MINUTES`, default 120).
- **Password hashing** — bcrypt via `bcrypt` package (72-byte truncation enforced).
- **Role checks** — FastAPI dependency `require_role(Role.ADMIN, Role.CREATOR)` raises 403 if mismatched.
- **No public creator enrolment** — only admins call `POST /api/admin/creators`.

**Token flow:**
```
Client          Server
  │                │
  ├─ POST /login ──►│  (validates credentials)
  │◄─ {access_token}│  (JWT signed with SECRET_KEY)
  │                │
  ├─ GET /videos ──►│  (Authorization: Bearer <token>)
  │                │  (decodes, validates exp, loads User)
  │◄─ 200 OK ──────┤
```

---

## 5. Video Upload & Processing Pipeline

```
POST /api/videos (multipart)
      │
      ▼
Validate content-type ∈ allowed, size ≤ MAX_UPLOAD_MB
      │
      ▼
storage.save(key, file_stream, content_type)  ──► Local FS / Azure Blob / S3
      │
      ▼
INSERT Video row (status=PROCESSING)
      │
      ▼
Return 201 { ..., "status": "processing" }
      │
      ▼ (BackgroundTasks)
_process_video(video_id)
      │
      ▼
materialise_local_path(backend, storage_key)  ──► local Path (FS) or temp file (cloud)
      │
      ▼
ffmpeg -i → probe duration, size
      │
      ▼
ffmpeg -ss 0.5 -frames:v 1 -vf scale=640:-2 → thumbnail.jpg
      │
      ▼
storage.save(thumb_key, thumb_bytes, image/jpeg)
      │
      ▼
UPDATE Video SET duration=…, size=…, thumbnail_key=…, status=READY
```

- **Idempotent** — re-uploading same title (with `--replace-videos`) deletes old blobs + row.
- **Failure handling** — any exception marks `status=FAILED`; dashboard filters to `READY` only.

---

## 6. HTTP Range Streaming

Video playback uses standard `Range` requests so browsers can seek without full download.

```
GET /api/videos/{id}/stream
Headers: Range: bytes=0-999999
      │
      ▼
storage.iter_read(key, start, length)  ──► chunked async generator
      │
      ▼
StreamingResponse(gen(), 206 Partial Content, Content-Range, Accept-Ranges: bytes)
```

**Backend implementations:**
- `LocalStorageBackend` — `open(path, 'rb').seek(start); read(chunk)`
- `AzureBlobStorageBackend` — `download_blob(offset=start, length=length).chunks()`
- `S3StorageBackend` — `get_object(Range=f"bytes={start}-{end}")["Body"].iter_chunks()`

---

## 7. Caching Strategy

```
GET /api/videos?search=...&genre=...&age_rating=...&sort=...&offset=...&limit=...
      │
      ▼
cache_key = "videos:list:{search}:{genre}:{age_rating}:{sort}:{offset}:{limit}"
      │
      ▼ (TTLCache.get)
HIT ──► return cached VideoList (deserialised Pydantic model)
      │
MISS ──► DB query → aggregates (avg rating, comment count) → serialize → cache.set(…, TTL)
      │
      ▼
return VideoList
```

- **TTL**: `CACHE_TTL_SECONDS` (default 30s).
- **Invalidation**: `cache.invalidate_prefix("videos:list:")` on upload.
- **Production swap**: Replace `TTLCache` with `redis.asyncio.Redis` + JSON serialisation; same key pattern.

---

## 8. Rate Limiting

Sliding-window algorithm (in-memory `deque` per `client_ip:path`):

```python
# middleware
if not limiter.allow(key, limit=RATE_LIMIT_REQUESTS, window=RATE_LIMIT_WINDOW_SECONDS):
    return 429 Too Many Requests
```

- Applied globally; tune via env for stricter auth limits.
- Cloud: replace with Redis sorted-set (`ZADD` timestamp, `ZREMRANGEBYSCORE`, `ZCARD`).

---

## 9. Scalability Patterns (Cloud-Native)

| Concern | Local Implementation | Cloud Mapping (Azure) |
|---------|---------------------|----------------------|
| **Compute** | Single Uvicorn process | Azure App Service (multiple instances) / Container Apps |
| **Database** | SQLite file | Azure Database for PostgreSQL Flexible Server / Azure SQL |
| **Object Storage** | `data/media/` (FS) | Azure Blob Storage (Hot/Cool tiers, CDN) |
| **Cache** | In-process `TTLCache` | Azure Cache for Redis (Premium for clustering) |
| **Auth** | JWT (self-issued) | Microsoft Entra ID (OIDC) + token validation middleware |
| **Media Processing** | BackgroundTasks + bundled ffmpeg | Azure Media Services (Jobs, Transforms) or Container Apps Jobs |
| **DNS / TLS / WAF** | localhost:8000 | Azure Front Door / Application Gateway + Custom Domain + Managed Cert |
| **Observability** | stdout logs | Azure Monitor / App Insights / Log Analytics |

**Horizontal scaling:** All components stateless → add App Service instances. Session affinity not required (JWT).

---

## 10. Security Considerations

- **Secrets** — `SECRET_KEY`, DB passwords, storage keys via `.env` (excluded from git). In Azure: App Service Configuration + Key Vault references.
- **Upload validation** — MIME allow-list, size cap, extension allow-list. No execution of uploaded content.
- **CORS** — configurable via `CORS_ORIGINS`; restrict to known origins in prod.
- **Rate limiting** — prevents credential stuffing & upload abuse.
- **Role enforcement** — server-side on every mutating endpoint.
- **HTTPS** — terminate at Front Door / App Gateway; App Service receives HTTP internally.

---

## 11. Extensibility Hooks

| Extension Point | How to Implement |
|----------------|------------------|
| **OIDC / Entra ID** | Replace `get_current_user` dependency; validate `Authorization: Bearer <aad_token>` via `msal`/`jose`; map roles from `roles` claim. |
| **Advanced Transcoding** | Swap `MediaProcessor` for Azure Media Services client; `POST /api/videos` enqueues Job; webhook updates `Video.status`. |
| **Webhooks / Events** | Add `event_bus.py` (Redis Pub/Sub or Azure Event Grid); publish `video.uploaded`, `video.ready`. |
| **Search** | Add Azure Cognitive Search indexer on `videos` table; expose `/api/videos/search` with semantic ranking. |
| **Recommendations** | Background job computes co-watch / content-based vectors; store in Redis; serve via `/api/videos/recommended`. |

---

## 12. Sequence Diagram: Consumer Watches a Video

```
Consumer          Browser              API                    Storage              DB
  │                  │                   │                      │                   │
  │── GET /video.html?id=42 ────────────────────────────────────────────────────►│
  │                  │◄── HTML + JS ──────│                      │                   │
  │                  │                   │                      │                   │
  │                  │── GET /api/videos/42 ────────────────────────────────────►│
  │                  │                   │◄── VideoDetail ──────│                   │
  │                  │                   │                      │                   │
  │                  │── GET /api/videos/42/stream (Range: 0-) ─────────────────►│
  │                  │                   │                      │                   │
  │                  │                   │── iter_read(key,0,∞) ─────────────────►│
  │                  │                   │◄── video chunks ─────│                   │
  │                  │◄── 200 video/mp4 ──│                      │                   │
  │                  │                   │                      │                   │
  │  (seeks)         │                   │                      │                   │
  │                  │── GET /stream?Range=bytes=5000000- ─────────────────────►│
  │                  │                   │── iter_read(key,5M,∞) ───────────────►│
  │                  │◄── 206 Partial ───│◄── chunked bytes ────│                   │
  │                  │                   │                      │                   │
```

---

## 13. Technology Stack Summary

| Layer | Technology | Version |
|-------|------------|---------|
| Language | Python | 3.11+ |
| Web Framework | FastAPI | 0.115 |
| ASGI Server | Uvicorn | 0.34 |
| ORM | SQLAlchemy | 2.0 |
| Validation | Pydantic | 2.11 |
| Auth | PyJWT + bcrypt | 2.10 / 5.0 |
| Media | imageio-ffmpeg (bundled ffmpeg 7.1) | 0.6 |
| Testing | pytest + httpx (TestClient) | 8.3 |
| Frontend | Vanilla HTML/CSS/JS (ES6 modules) | — |

---

*Architecture version 1.0 — aligns with Task 1 deliverable. See `docs/DEPLOYMENT.md` for Task 2 cloud provisioning steps.*