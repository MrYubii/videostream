# VideoStream — Azure Deployment Guide (Task 2)

This guide provisions a production-ready VideoStream on **Microsoft Azure** using the same cloud platform explored in the practical exercises (App Service, PostgreSQL, Blob Storage, Cache for Redis, Front Door, Entra ID, Media Services).

> **Prerequisites:** Azure subscription, Owner/Contributor on resource group, Azure CLI (`az`) installed and logged in (`az login`).

---

## 1. Architecture on Azure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            AZURE REGION                                      │
│  ┌──────────────────┐   ┌──────────────────┐   ┌────────────────────────┐  │
│  │  Azure Front Door│──►│  App Service     │   │  Azure Database for    │  │
│  │  (WAF, TLS, DNS) │   │  (Linux, Python) │   │  PostgreSQL Flexible   │  │
│  └────────┬─────────┘   └────────┬─────────┘   │  Server (videos DB)    │  │
│           │                      │             └───────────┬────────────┘  │
│           │                      │                       │               │
│           │         ┌────────────┴────────────┐          │               │
│           │         │                         │          │               │
│           ▼         ▼                         ▼          ▼               │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Azure Blob     │  │ Azure Cache    │  │ Entra ID │  │ Media    │    │
│  │ Storage        │  │ for Redis      │  │ (OIDC)   │  │ Services │    │
│  │ (videos +      │  │ (session +     │  │          │  │ (optional│    │
│  │  thumbnails)   │  │  rate limit)   │  │          │  │  transc.)│    │
│  └────────────────┘  └────────────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Resource Provisioning (Bicep / ARM / CLI)

### 2.1 Create Resource Group
```bash
az group create --name rg-videostream --location uksouth
```

### 2.2 PostgreSQL Flexible Server
```bash
az postgres flexible-server create \
  --resource-group rg-videostream \
  --name pg-videostream \
  --location uksouth \
  --admin-user videostream_admin \
  --admin-password 'StrongP@ssw0rd!' \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 15 \
  --public-access 0.0.0.0  # or VNet integration
```

Get connection string:
```bash
CONN_STR=$(az postgres flexible-server show-connection-string \
  --server-name pg-videostream \
  --database videostream \
  --admin-user videostream_admin \
  --admin-password 'StrongP@ssw0rd!' \
  --query connectionStrings.psql -o tsv)
# Result: postgresql://videostream_admin:StrongP@ssw0rd!@pg-videostream.postgres.database.azure.com:5432/videostream?sslmode=require
```

### 2.3 Azure Blob Storage
```bash
az storage account create \
  --resource-group rg-videostream \
  --name stvideostream$(date +%s) \
  --location uksouth \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-blob-public-access false

CONN_STR=$(az storage account show-connection-string -n stvideostream... -g rg-videostream -o tsv)
az storage container create --name videos --account-name stvideostream... --connection-string "$CONN_STR"
az storage container create --name thumbnails --account-name stvideostream... --connection-string "$CONN_STR"
```

### 2.4 Azure Cache for Redis
```bash
az redis create \
  --resource-group rg-videostream \
  --name rc-videostream \
  --location uksouth \
  --sku Basic \
  --vm-size C0 \
  --enable-non-ssl-port false
```
Get primary key:
```bash
REDIS_KEY=$(az redis list-keys -n rc-videostream -g rg-videostream --query primaryKey -o tsv)
REDIS_HOST=rc-videostream.redis.cache.windows.net
```

### 2.5 App Service (Linux, Python 3.11)
```bash
az appservice plan create \
  --resource-group rg-videostream \
  --name asp-videostream \
  --location uksouth \
  --sku P1v3 \
  --is-linux

az webapp create \
  --resource-group rg-videostream \
  --plan asp-videostream \
  --name videostream-app \
  --runtime "PYTHON|3.11" \
  --deployment-container-image-name "python:3.11-slim"  # placeholder; we'll deploy zip
```

### 2.6 Configure App Settings
```bash
az webapp config appsettings set -g rg-videostream -n videostream-app --settings \
  ENVIRONMENT=production \
  SECRET_KEY="$(openssl rand -base64 48)" \
  TOKEN_EXPIRY_MINUTES=120 \
  DATABASE_URL="$CONN_STR" \
  STORAGE_BACKEND=azure \
  AZURE_CONNECTION_STRING="$CONN_STR" \
  AZURE_CONTAINER=videos \
  CACHE_TTL_SECONDS=30 \
  RATE_LIMIT_REQUESTS=100 \
  RATE_LIMIT_WINDOW_SECONDS=60 \
  CORS_ORIGINS="https://videostream.example.com" \
  PYTHONPATH=/home/site/wwwroot
```

### 2.7 Redis Session / Cache Middleware (Code Change)
In `app/services/cache.py`, add a Redis implementation:
```python
# app/services/cache.py — add RedisCache class
import redis.asyncio as redis
import json

class RedisCache:
    def __init__(self, url: str):
        self._client = redis.from_url(url, decode_responses=True)

    async def get(self, key: str):
        val = await self._client.get(key)
        return json.loads(val) if val else None

    async def set(self, key: str, value, ttl: float):
        await self._client.setex(key, int(ttl), json.dumps(value, default=str))

    async def invalidate_prefix(self, prefix: str):
        async for k in self._client.scan_iter(f"{prefix}*"):
            await self._client.delete(k)
```
Swap `TTLCache` for `RedisCache` in `app/main.py` lifespan (initialise from `REDIS_URL=rediss://:{REDIS_KEY}@{REDIS_HOST}:6380`).

### 2.8 Rate Limiter — Redis Backend
Replace in-memory `InMemoryRateLimiter` with Redis sorted-set:
```python
# app/services/ratelimit.py — RedisRateLimiter
import time, redis.asyncio as redis

class RedisRateLimiter:
    def __init__(self, url: str):
        self._r = redis.from_url(url)

    async def allow(self, key: str, limit: int, window: int) -> bool:
        now = time.time()
        pipe = self._r.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, window)
        _, count, _, _ = await pipe.execute()
        return count < limit
```

---

## 3. Deployment Pipeline (GitHub Actions / Azure DevOps)

### 3.1 Build & Deploy (GitHub Actions)
```yaml
# .github/workflows/azure-deploy.yml
name: Deploy to Azure
on:
  push:
    branches: [main]

jobs:
  build-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: Install deps
        run: pip install -r requirements.txt
      - name: Run tests
        run: pytest tests -q
      - name: Zip deploy
        uses: azure/webapps-deploy@v2
        with:
          app-name: videostream-app
          publish-profile: ${{ secrets.AZURE_WEBAPP_PUBLISH_PROFILE }}
          package: .
```
Add `AZURE_WEBAPP_PUBLISH_PROFILE` secret from `az webapp deployment list-publishing-profiles`.

### 3.2 Database Migrations
On startup, `Base.metadata.create_all(bind=engine)` runs (dev). For production, use **Alembic**:
```bash
pip install alembic
alembic init migrations
# edit env.py to use DATABASE_URL from os.environ
alembic revision --autogenerate -m "init"
alembic upgrade head
```
Run as a **pre-deploy** step or separate container job.

---

## 4. Optional: Entra ID (OIDC) Authentication

Replace self-issued JWT with Microsoft Entra ID tokens:

1. **App Registration** — Single-tenant, redirect URI `https://videostream.example.com/.auth/login/aad/callback`.
2. **Expose API** — Define `access_as_user` scope; add `roles` claim (`admin`, `creator`, `consumer`).
3. **App Service Easy Auth** — Enable Authentication → Microsoft Entra ID; set allowed token audiences.
4. **Middleware Swap** — In `app/deps.py`:
   ```python
   from msal import ConfidentialClientApplication
   # Validate Authorization: Bearer <aad_token> via jose.jwt.decode with Entra ID JWKS
   # Map `roles` claim → Role enum
   ```
5. **Admin Creator Enrolment** — Now UI can use Entra ID groups or Graph API.

---

## 5. Optional: Azure Media Services (Advanced Transcoding)

For production-grade transcoding (adaptive bitrate, HLS/DASH, DRM):

1. **Create Media Services Account** (same region).
2. **Transform** — Define `BuiltInStandardEncoderPreset` (H264MultipleBitrate720p, etc.).
3. **Upload Flow** —
   - `POST /api/videos` stores original in Blob `raw/` container.
   - Background task creates **Job** with Transform → outputs to `processed/` container.
   - Job completion Event Grid → webhook `/api/webhooks/media-services` updates `Video.status=ready`, writes `stream_url` (HLS manifest `.m3u8`).
4. **Streaming Endpoint** — Start Standard Streaming Endpoint; CDN in front.

---

## 6. DNS, TLS & WAF (Front Door)

```bash
az afd profile create -g rg-videostream -n afd-videostream --sku Premium_AzureFrontDoor
az afd endpoint create -g rg-videostream --profile-name afd-videostream -n videostream-fd --origin videostream-app.azurewebsites.net --origin-host-header videostream-app.azurewebsites.net
az afd custom-domain create -g rg-videostream --profile-name afd-videostream --endpoint-name videostream-fd -n video-custom --host-name videostream.example.com --validation-token <from DNS TXT>
az afd custom-domain enable-https -g rg-videostream --profile-name afd-videostream --endpoint-name videostream-fd --custom-domain-name video-custom --certificate-type ManagedCertificate
az afd waf-policy create -g rg-videostream -n waf-videostream --policy-mode Prevention
# Attach WAF policy to endpoint
```
Result: `https://videostream.example.com` → Front Door (WAF, TLS, caching) → App Service.

---

## 7. Monitoring & Observability

| Component | Tool |
|-----------|------|
| App logs / metrics | Azure Monitor → Log Analytics Workspace → `AppServiceConsoleLogs`, `AppServiceHTTPLogs` |
| Distributed tracing | Application Insights (auto-instrument Python via `opentelemetry-instrument`) |
| Alerts | CPU > 80%, 5xx > 1%, Redis memory > 85% |
| Cost | Cost Management + Advisor (right-size App Service plan, Redis tier) |

Add to `requirements.txt`:
```
opentelemetry-instrument
opentelemetry-exporter-azuremonitor
```
Start with `opentelemetry-instrument uvicorn app.main:app`.

---

## 8. Security Hardening Checklist

- [ ] `SECRET_KEY` from Key Vault (`@Microsoft.KeyVault(SecretUri=...)`)
- [ ] PostgreSQL: `sslmode=require`, firewall only App Service subnet (VNet integration)
- [ ] Blob: `allowBlobPublicAccess=false`, SAS tokens for signed URLs if needed
- [ ] App Service: `WEBSITE_VNET_ROUTE_ALL=1`, Private Endpoint for Postgres/Redis/Blob
- [ ] Front Door: WAF managed rules (OWASP 3.2), rate limit rule (100 req/10s/IP)
- [ ] Entra ID: Conditional Access (MFA for admins), token lifetime 60 min
- [ ] Secrets rotation: Key Vault rotation policy + App Service restart via Event Grid

---

## 9. Cost Estimation (Monthly, UK South, indicative)

| Resource | SKU | Est. Cost (GBP) |
|----------|-----|-----------------|
| App Service Plan | P1v3 (1 instance) | ~£110 |
| PostgreSQL Flexible | B1ms, 32 GB | ~£35 |
| Blob Storage (Hot) | 100 GB + ops | ~£2 |
| Cache for Redis | Basic C0 (250 MB) | ~£12 |
| Front Door | Premium, 1M req | ~£15 |
| Media Services (optional) | S1, 10 jobs/mo | ~£50 |
| **Total (core)** | | **~£174/mo** |

Scale down to **B1/B2** for dev/test; enable **autoscale** on App Service.

---

## 10. Rollback & Disaster Recovery

- **App Service** — Deployment slots (`staging`); swap for zero-downtime; rollback = swap back.
- **Database** — Point-in-time restore (PITR) up to 35 days; manual `pg_dump` to Blob weekly.
- **Blob** — Soft delete (14 days), versioning, lifecycle policy (cool/archive after 30/90 days).
- **Redis** — Geo-replication (Premium) for cross-region HA.

---

## 11. Validation Checklist (Task 2 Deliverable)

- [ ] Resource group with all resources deployed via CLI/Bicep
- [ ] App Service returns `200` at `/` and `/docs`
- [ ] `POST /api/auth/register` → `201` (consumer)
- [ ] Admin login → `POST /api/admin/creators` → `201`
- [ ] Creator login → `POST /api/videos` upload → `201` → background processing → `ready`
- [ ] `GET /api/videos/{id}/stream` plays in browser (seek works)
- [ ] Comments & ratings persist
- [ ] Front Door custom domain `https://videostream.example.com` loads
- [ ] WAF blocks test SQLi/XSS payload (403)
- [ ] Logs appear in Log Analytics

---

*This guide aligns with the practical exercises' Azure platform focus. Adjust SKUs, regions, and naming to your subscription policies.*