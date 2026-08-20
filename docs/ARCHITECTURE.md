# VideoStream — Final N-Tier Architecture

## 1. Coursework alignment

The coursework asks for a scalable, cloud-native video-sharing web application with consumer and creator accounts, video metadata, search/playback, comments/ratings, hosted persistence/object storage, authentication/roles, and deployment to the taught cloud platform. The marking rubric places particular weight on problem definition, technical solution architecture, advanced features, scalability/limitations, demonstration, and referencing.

This branch implements those concerns as an explicit N-tier design rather than keeping database operations inside every HTTP route.

## 2. N-tier architecture

```text
┌──────────────────────────────────────────────────────────────────────┐
│  PRESENTATION TIER                                                   │
│  Browser: HTML/CSS/JS                                                │
│  FastAPI routers: auth / admin / videos / comments / ratings /       │
│  reactions                                                           │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ DTOs / HTTP
┌───────────────────────────────▼──────────────────────────────────────┐
│  APPLICATION / BUSINESS TIER                                        │
│  AuthService                                                         │
│  Role/permission policies                                            │
│  Video upload/processing orchestration                               │
│  Validation, ownership checks, caching decisions                     │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ repository interfaces
┌───────────────────────────────▼──────────────────────────────────────┐
│  DATA ACCESS TIER                                                    │
│  UserRepository / VideoRepository / CommentRepository /             │
│  RatingRepository / ReactionRepository                              │
│  SQLAlchemy query and transaction operations                          │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ SQL / object operations
┌───────────────────────────────▼──────────────────────────────────────┐
│  INFRASTRUCTURE / PERSISTENCE TIER                                  │
│  SQLite (local) / Azure Database for PostgreSQL (cloud)             │
│  Local filesystem (local) / Azure Blob Storage (cloud)              │
│  TTL cache (local) / optional distributed Redis cache (cloud)       │
│  Media processor / FFmpeg                                           │
└──────────────────────────────────────────────────────────────────────┘
```

### Why this is N-tier

- **Presentation** receives HTTP requests and returns response DTOs.
- **Application/business** contains authentication decisions, role rules, upload orchestration and domain-level decisions.
- **Data access** owns SQLAlchemy queries and persistence operations in `app/repositories.py`.
- **Infrastructure** hides cloud-specific storage and runtime concerns in `app/services/storage.py`, `media.py`, `cache.py`, and `ratelimit.py`.

The repository boundary is deliberately replaceable: the application can move from SQLite to PostgreSQL without rewriting the HTTP contract, while the storage abstraction can switch from local files to Azure Blob Storage.

## 3. Authentication and authorisation

### Consumer

- `POST /api/auth/register` creates a `consumer` account.
- The public registration endpoint never accepts a role field.
- Passwords are hashed with bcrypt before persistence.
- `POST /api/auth/login` issues a signed JWT.

### Creator

- Creators **do not self-enrol publicly**, matching the coursework requirement.
- An authenticated administrator creates a creator through `POST /api/admin/creators`.
- The creator then uses the same JWT login service; an explicit `/creator-login.html` page is provided for demonstration.
- Creator upload access is enforced server-side with `require_role(Role.CREATOR, Role.ADMIN)`.

### Access-control matrix

| Operation | Consumer | Creator | Admin |
|---|---:|---:|---:|
| Public registration | Yes | No | No |
| Login | Yes | Yes | Yes |
| Browse/search/watch | Yes | Yes | Yes |
| Comment | Yes | Yes | Yes |
| Rate/react | Yes | Yes | Yes |
| Upload video | No | Yes | Yes |
| Edit own video | No | Yes | Yes |
| Delete own video | No | Yes | Yes |
| Create creator | No | No | Yes |
| Enable/disable creator | No | No | Yes |
| Admin statistics | No | No | Yes |

### JWT flow

```text
Browser
  │ POST /api/auth/login
  ▼
AuthService
  │ verify bcrypt hash
  ▼
JWT {sub, role, iat, exp}
  │
  ▼
Browser stores bearer token
  │ Authorization: Bearer <token>
  ▼
get_current_user → UserRepository → database
  │
  ├── require_role(CREATOR, ADMIN) for uploads
  └── require_role(ADMIN) for creator administration
```

## 4. Video workflow

```text
Creator
  │ multipart upload + metadata
  ▼
POST /api/videos
  │ role check
  ▼
VideoRepository → Video(status=processing)
  │
  ▼
StorageBackend → local filesystem / Azure Blob
  │
  ▼
Background processing
  ├── FFmpeg probe duration/size
  ├── transcode to MP4 when possible
  └── generate JPEG thumbnail
  │
  ▼
Video(status=ready)
  │
  ▼
Consumer dashboard/search/player
```

Video playback uses HTTP Range requests. This avoids downloading an entire video when the browser seeks and maps naturally to ranged object-storage reads.

## 5. Scalability mechanisms

| Concern | Local | Azure target |
|---|---|---|
| Compute | Uvicorn | Azure App Service Linux, multiple instances |
| Database | SQLite | Azure Database for PostgreSQL Flexible Server |
| Media | `data/media` | Azure Blob Storage |
| Cache | In-memory TTL | Azure Managed Redis (optional scale-out enhancement) |
| Rate limiting | In-memory window | Redis-backed implementation can be added for multi-instance deployment |
| Media processing | FastAPI background task | Queue/worker or Azure Container Apps Job for larger workloads |
| Edge/DNS/TLS | localhost | Azure Front Door + managed TLS (optional) |

The API is stateless with respect to login sessions because authentication state is carried in JWTs. Therefore additional App Service instances can serve requests without session affinity.

## 6. Advanced features demonstrated

1. **Identity framework:** JWT + bcrypt + role-based authorisation.
2. **Media conversion/analysis:** FFmpeg-based duration probing, MP4 conversion and thumbnail generation.
3. **CI/CD:** GitHub Actions runs tests and deploys successful changes to Azure App Service on `main`.
4. **Cloud object storage:** Azure Blob Storage backend is implemented behind the storage abstraction.
5. **Caching/rate limiting:** TTL response cache, gzip compression and request rate limiting are included.
6. **HTTP Range streaming:** supports seeking and partial-content responses.

## 7. Performance metrics for evaluation

For the presentation/demo, collect evidence for:

- HTTP response time for `GET /api/videos` with cold and warm cache.
- Upload-to-ready processing time.
- Video stream first-byte/response time.
- HTTP 4xx/5xx rate.
- Requests per second under a simple load test.
- App Service CPU/memory during load.
- Database query duration for dashboard/search.
- Cache hit/miss behaviour if distributed caching is enabled.

These metrics directly support the rubric's requirement to quantify and critically assess the solution's performance and scalability.

## 8. Security decisions

- Passwords are never stored in plaintext.
- Roles are assigned server-side; consumers cannot register as creators/admins.
- Creator uploads are protected by server-side role checks.
- Ownership checks prevent one creator editing/deleting another creator's video.
- Uploads are restricted by extension, MIME type and size.
- Azure Blob can remain private; thumbnails are streamed through the API rather than requiring public blob access.
- Production secrets are supplied through Azure App Service settings/Key Vault rather than committed to Git.
- Production CORS should be an explicit allow-list.

## 9. Known limitations and roadmap

- FastAPI `BackgroundTasks` is appropriate for coursework-scale processing but is not a durable distributed queue. A production system should move transcoding to a queue/worker architecture.
- The default TTL cache is process-local. For multiple App Service instances, use Azure Managed Redis.
- `Base.metadata.create_all()` is convenient for the coursework deployment but production evolution should use Alembic migrations.
- A single PostgreSQL server is a regional dependency; higher availability can be added with PostgreSQL HA/zone redundancy and a tested recovery plan.
- Front Door/WAF and distributed caching are optional cost-bearing scale-out layers and should be introduced when traffic justifies them.

## 10. Project structure

```text
app/
├── main.py                  # presentation composition/root application
├── config.py                # configuration/infrastructure settings
├── database.py              # persistence engine/session
├── models.py                # persistence/domain models
├── repositories.py          # DATA ACCESS TIER
├── schemas.py               # API DTOs
├── security.py              # JWT/bcrypt infrastructure
├── deps.py                  # authentication/authorisation dependencies
├── routers/                 # PRESENTATION TIER
│   ├── auth.py
│   ├── admin.py
│   ├── videos.py
│   ├── comments.py
│   ├── ratings.py
│   └── reactions.py
├── services/                # APPLICATION + INFRASTRUCTURE SERVICES
│   ├── auth.py              # application/business authentication service
│   ├── storage.py           # local/Azure/S3 object storage abstraction
│   ├── media.py             # media processing
│   ├── cache.py             # response caching
│   └── ratelimit.py         # request protection
└── static/                  # browser presentation
```

This architecture is intentionally documented alongside the implementation so the slide deck can show both the logical N-tier model and the actual repository structure.