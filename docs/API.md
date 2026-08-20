# VideoStream — REST API Reference

**Base URL:** `http://localhost:8000` (local)  
**OpenAPI Spec:** `GET /openapi.json`  
**Swagger UI:** `GET /docs`  
**Auth:** JWT Bearer token (`Authorization: Bearer <access_token>`)  
**Roles:** `admin`, `creator`, `consumer`

---

## Conventions

- All request/response bodies: **JSON** (`Content-Type: application/json`) unless noted.
- Video upload: **multipart/form-data**.
- Errors: `{ "detail": "human readable message" }` (FastAPI validation errors return array).
- Timestamps: ISO 8601 UTC (`2026-08-05T12:34:56.789Z`).
- Enums serialized as their string value (e.g., `"age_rating": "PG"`).
- Pagination: `offset` (default 0) + `limit` (default 12, max 100).

---

## 1. Authentication

### 1.1 Register Consumer
`POST /api/auth/register`

**Request**
```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "ConsumerPass1!",
  "full_name": "Alice Smith"
}
```
- `username`: 3–64 alphanumeric + underscore
- `password`: 8–128 chars

**Response** `201 Created`
```json
{
  "id": 4,
  "username": "alice",
  "email": "alice@example.com",
  "full_name": "Alice Smith",
  "role": "consumer",
  "is_active": true,
  "created_at": "2026-08-05T12:00:00Z"
}
```

**Errors:** `409` username/email taken, `422` validation.

---

### 1.2 Login
`POST /api/auth/login`

**Request**
```json
{ "username": "alice", "password": "ConsumerPass1!" }
```

**Response** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "role": "consumer",
  "username": "alice"
}
```
Store `access_token` and send as `Authorization: Bearer <token>`.

---

### 1.3 Current User
`GET /api/auth/me`  
**Auth:** Required  
**Response** `200 OK` — same shape as register response.

---

## 2. Admin — Creator Management

All require **`admin` role**.

### 2.1 Create Creator
`POST /api/admin/creators`

**Request**
```json
{
  "username": "new_creator",
  "email": "creator@example.com",
  "password": "CreatorPass1!",
  "full_name": "New Creator"
}
```

**Response** `201 Created` — User object with `"role": "creator"`.

---

### 2.2 List Creators
`GET /api/admin/creators`

**Response** `200 OK`
```json
[
  { "id": 2, "username": "creator_one", "email": "...", "full_name": "Creator One", "role": "creator", "is_active": true, "created_at": "..." },
  { "id": 3, "username": "creator_two", "email": "...", "full_name": "Creator Two", "role": "creator", "is_active": true, "created_at": "..." }
]
```

---

### 2.3 Update Creator
`PATCH /api/admin/creators/{creator_id}`

**Request** (any field optional)
```json
{ "is_active": false, "role": "consumer" }
```
- `role`: `creator` | `consumer` (cannot promote to `admin` via this endpoint — `400`)
- An admin cannot modify their own account here (`400`).

**Response** `200 OK` — updated User object.

---

### 2.4 Admin Stats
`GET /api/admin/stats`

**Response** `200 OK`
```json
{
  "total_creators": 2,
  "total_videos": 5,
  "total_views": 128,
  "total_comments": 3,
  "total_ratings": 7
}
```

---

## 3. Videos

### 3.1 List / Search / Filter
`GET /api/videos`

**Query Parameters**

| Param | Type | Description |
|-------|------|-------------|
| `search` | string | Free-text across title, publisher, producer, genre |
| `genre` | string | Exact genre match (e.g., `Music`, `Comedy`) |
| `age_rating` | enum | `U` \| `PG` \| `12` \| `15` \| `18` |
| `sort` | enum | `latest` (default) \| `popular` (by view_count desc) |
| `offset` | int | Default 0 |
| `limit` | int | Default 12, max 100 |

**Response** `200 OK`
```json
{
  "total": 42,
  "offset": 0,
  "limit": 12,
  "items": [
    {
      "id": 1,
      "title": "Neon City After Dark",
      "publisher": "Aurora Studios",
      "producer": "J. Malik",
      "genre": "Music",
      "age_rating": "PG",
      "description": "A cinematic test sequence...",
      "thumbnail_url": "/media/thumbnails/neon-city-after-dark.jpg",
      "duration_seconds": 6,
      "status": "ready",
      "view_count": 0,
      "uploader": "creator_one",
      "created_at": "2026-08-05T12:00:00Z",
      "rating_average": 4.5,
      "rating_count": 2,
      "comment_count": 1
    }
  ]
}
```

> Only videos with `status == "ready"` are returned.

---

### 3.2 Video Detail
`GET /api/videos/{video_id}`

**Response** `200 OK`
```json
{
  "id": 1,
  "title": "...",
  "publisher": "...",
  "producer": "...",
  "genre": "Music",
  "age_rating": "PG",
  "description": "...",
  "thumbnail_url": "/media/thumbnails/...",
  "duration_seconds": 6,
  "status": "ready",
  "view_count": 15,
  "uploader": "creator_one",
  "created_at": "2026-08-05T12:00:00Z",
  "rating_average": 4.5,
  "rating_count": 2,
  "comment_count": 1,
  "stream_url": "/api/videos/1/stream",
  "size_bytes": 651198,
  "content_type": "video/mp4"
}
```

**Errors:** `404` not found.

---

### 3.3 Upload Video (Creator only)
`POST /api/videos`  
**Auth:** Required (`creator` or `admin`)  
**Content-Type:** `multipart/form-data`

**Form Fields**

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `file` | file | Yes | MP4 / WebM / OGG / MOV; ≤ `MAX_UPLOAD_MB` (default 200 MB) |
| `title` | string | Yes | 1–255 chars |
| `publisher` | string | Yes | 1–128 chars |
| `producer` | string | No | 0–128 chars |
| `genre` | string | Yes | 1–64 chars |
| `age_rating` | enum | No (default `U`) | `U` \| `PG` \| `12` \| `15` \| `18` |
| `description` | string | No | 0–2000 chars |

**Response** `201 Created`
```json
{
  "id": 10,
  "title": "My New Clip",
  "publisher": "Me",
  "producer": "",
  "genre": "Comedy",
  "age_rating": "12",
  "description": "Funny moment",
  "thumbnail_url": "",
  "duration_seconds": 0,
  "status": "processing",
  "view_count": 0,
  "uploader": "creator_one",
  "created_at": "2026-08-05T12:30:00Z",
  "rating_average": null,
  "rating_count": 0,
  "comment_count": 0,
  "stream_url": "/api/videos/10/stream",
  "size_bytes": 0,
  "content_type": "video/mp4"
}
```

**Notes:**
- Returns immediately with `status: "processing"`.
- Background task runs ffmpeg probe + thumbnail; polls `GET /api/videos/{id}` until `status: "ready"`.
- `thumbnail_url` empty until processing completes.

**Errors:** `403` not a creator, `413` file too large, `415` unsupported format, `422` validation.

---

### 3.4 Stream Video (HTTP Range)
`GET /api/videos/{video_id}/stream`

**Headers**
- Optional: `Range: bytes=START-END`, `bytes=START-` (open-ended), or `bytes=-N` (last N bytes)

**Response**
- `200 OK` (full file) or `206 Partial Content` (range)
- `Content-Type: video/mp4` (or uploaded type)
- `Accept-Ranges: bytes`
- `Content-Range: bytes START-END/TOTAL` (on 206)
- `Cache-Control: public, max-age=3600`

**Behaviour:**
- Satisfiable ranges → `206`; unsatisfiable ranges → `416` with `Content-Range: bytes */TOTAL`; malformed `Range` headers are ignored (full `200`).
- `view_count` is incremented **at most once per 30 minutes per IP per video** (deduplicated), not once per byte-range request.

**Errors:** `404` not found / missing file, `409` video still processing, `416` range not satisfiable.

---

### 3.5 Update Video Metadata
`PATCH /api/videos/{video_id}`  
**Auth:** Required (uploader or `admin`)

**Request** (any field optional)
```json
{ "title": "New Title", "age_rating": "15" }
```

**Response** `200 OK` — full `VideoDetail` payload.

**Errors:** `401` unauthenticated, `403` not the uploader, `404` not found, `422` validation.

---

### 3.6 Delete Video
`DELETE /api/videos/{video_id}`  
**Auth:** Required (uploader or `admin`)

Deletes the media blob, thumbnail, comments and ratings.

**Response** `204 No Content`

**Errors:** `401` unauthenticated, `403` not the uploader, `404` not found.

---

## 4. Comments

### 4.1 List Comments
`GET /api/videos/{video_id}/comments`

**Response** `200 OK`
```json
[
  { "id": 1, "body": "Great clip!", "video_id": 1, "author": "alice", "created_at": "2026-08-05T12:05:00Z" },
  { "id": 2, "body": "Love the visuals", "video_id": 1, "author": "bob", "created_at": "2026-08-05T12:10:00Z" }
]
```

---

### 4.2 Add Comment
`POST /api/videos/{video_id}/comments`  
**Auth:** Required (any authenticated user)

**Request**
```json
{ "body": "This is awesome!" }
```

**Response** `201 Created`
```json
{ "id": 3, "body": "This is awesome!", "video_id": 1, "author": "alice", "created_at": "2026-08-05T12:15:00Z" }
```

**Errors:** `401` unauthenticated, `404` video not found.

---

## 5. Ratings

### 5.1 Get Rating Summary
`GET /api/videos/{video_id}/rating`  
**Auth:** Optional (include token to see your rating)

**Response** `200 OK`
```json
{
  "video_id": 1,
  "average": 4.2,
  "count": 5,
  "user_rating": 5
}
```
- `user_rating` is `null` if unauthenticated or user hasn't rated.

---

### 5.2 Set / Update Rating
`PUT /api/videos/{video_id}/rating`  
**Auth:** Required

**Request**
```json
{ "value": 4 }
```
- `value`: integer 1–5 (upserts per user)

**Response** `200 OK`
```json
{ "video_id": 1, "average": 4.1, "count": 6, "user_rating": 4 }
```

**Errors:** `401` unauthenticated, `404` video not found, `422` value out of range.

---

## 6. Static Frontend Routes

| Path | Serves |
|------|--------|
| `/` | `index.html` (Dashboard) |
| `/video.html` | Video player page |
| `/login.html` | Sign in |
| `/signup.html` | Consumer registration |
| `/admin.html` | Admin panel |
| `/css/style.css` | Stylesheet |
| `/js/*.js` | Client modules |
| `/favicon.svg` | Site icon |
| `/media/*` | Uploaded videos & thumbnails (local backend) |

---

## 7. Error Responses

| Status | Scenario |
|--------|----------|
| `400` | Malformed JSON / missing required field |
| `401` | Missing/invalid/expired JWT |
| `403` | Authenticated but insufficient role |
| `404` | Resource not found |
| `409` | Conflict (duplicate username/email, video processing) |
| `413` | Upload exceeds `MAX_UPLOAD_MB` |
| `415` | Unsupported media type |
| `416` | Range not satisfiable |
| `422` | Pydantic validation error (details in `detail` array) |
| `429` | Rate limit exceeded |
| `500` | Unexpected server error |

---

## 8. Example: Full Upload → Watch Flow (curl)

```bash
# 1. Login as creator
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"creator_one","password":"CreatorPass1!"}' | jq -r .access_token)

# 2. Upload video
curl -X POST http://localhost:8000/api/videos \
  -H "Authorization: Bearer $TOKEN" \
  -F 'file=@myclip.mp4' \
  -F 'title=My Clip' \
  -F 'publisher=Me' \
  -F 'genre=Comedy' \
  -F 'age_rating=PG' \
  -F 'description=Test upload'

# 3. Poll until ready
VIDEO_ID=12
while true; do
  STATUS=$(curl -s http://localhost:8000/api/videos/$VIDEO_ID | jq -r .status)
  echo "Status: $STATUS"
  [ "$STATUS" = "ready" ] && break
  sleep 2
done

# 4. Stream (with range)
curl -H "Range: bytes=0-999999" http://localhost:8000/api/videos/$VIDEO_ID/stream -o chunk.mp4
```

---

## 9. Rate Limits

Default: **30 requests / 60 seconds** per IP per path.  
Configurable via `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW_SECONDS`.

---

*Generated from `app/routers/*.py` and `app/schemas.py`. For interactive exploration, visit `/docs`.*