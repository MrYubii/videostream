# VideoStream — Azure Deployment + CI/CD Guide

This is the recommended Task 2 deployment path for the current VideoStream implementation.

The coursework requires the solution to be implemented, deployed and tested on the cloud platform taught in the module, and the demonstration must show the deployed system and backend activity. The guide below uses **Azure App Service + Azure Database for PostgreSQL Flexible Server + Azure Blob Storage + GitHub Actions**.

## 1. Target Azure architecture

```text
Browser
   │ HTTPS
   ▼
Azure Front Door (optional: WAF + custom DNS + TLS)
   │
   ▼
Azure App Service (Linux / Python 3.11)
   │
   ├──────────────► PostgreSQL Flexible Server
   │
   ├──────────────► Azure Blob Storage
   │
   └──────────────► Optional Azure Managed Redis

GitHub main
   │ push
   ▼
GitHub Actions
   ├── install dependencies
   ├── pytest
   └── deploy only after tests pass
```

Microsoft's current App Service documentation states that Python applications can use deployment build automation from `requirements.txt`; for FastAPI on Python 3.13 or earlier, a custom startup command is required. This project therefore uses Python 3.11 and an explicit Gunicorn/Uvicorn startup command. citeturn4search0turn4search1

## 2. Prerequisites

Install or access:

- Azure subscription.
- Azure CLI.
- Git and GitHub access to `MrYubii/videostream`.
- Python 3.11 locally for testing.

Login:

```bash
az login
az account show
```

Select the correct subscription if necessary:

```bash
az account set --subscription "YOUR_SUBSCRIPTION_ID"
```

## 3. Set deployment variables

Use unique names for Azure resources. App Service and Storage Account names are globally constrained.

```bash
export LOCATION="uksouth"
export RESOURCE_GROUP="rg-videostream-cw2"
export APP_NAME="YOUR-UNIQUE-VIDEOSTREAM-APP"
export PLAN_NAME="asp-videostream-cw2"
export PG_NAME="YOUR-UNIQUE-VIDEOSTREAM-PG"
export PG_ADMIN="videostreamadmin"
export PG_PASSWORD="USE-A-STRONG-PASSWORD"
export DB_NAME="videostream"
export STORAGE_ACCOUNT="YOURUNIQUEVIDEOSTREAM"
export STORAGE_CONTAINER="videos"
```

For Windows PowerShell, use `$env:NAME="value"` instead of `export NAME="value"`.

## 4. Create the resource group

```bash
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION"
```

## 5. Create PostgreSQL Flexible Server

Azure Database for PostgreSQL Flexible Server is the managed relational database target for the application. Microsoft documents Azure CLI provisioning and the standard PostgreSQL port as 5432. citeturn1search0turn1search3

For a coursework/dev deployment, a small burstable SKU is sufficient; choose a larger SKU only if your subscription/course requires it.

```bash
az postgres flexible-server create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$PG_NAME" \
  --location "$LOCATION" \
  --admin-user "$PG_ADMIN" \
  --admin-password "$PG_PASSWORD" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 15 \
  --public-access 0.0.0.0
```

Create the application database:

```bash
az postgres flexible-server db create \
  --resource-group "$RESOURCE_GROUP" \
  --server-name "$PG_NAME" \
  --database-name "$DB_NAME"
```

**Important:** `0.0.0.0` is convenient for a coursework demonstration but is broader than a production network design. For a hardened deployment, restrict firewall/network access or use private networking/VNet integration. Azure supports both public-access firewall rules and private VNet deployment. citeturn1search3turn1search9

### SQLAlchemy connection string

Use the `psycopg` SQLAlchemy dialect installed by `requirements.txt`:

```text
postgresql+psycopg://USERNAME:PASSWORD@SERVER.postgres.database.azure.com:5432/videostream?sslmode=require
```

If the password contains characters such as `@`, `:`, `/`, `#`, or `%`, URL-encode it before placing it in the connection string.

## 6. Create Azure Blob Storage

The application already contains a `StorageBackend` abstraction with an Azure Blob implementation. Azure's current Python guidance recommends the `azure-storage-blob` client library for Blob Storage. citeturn1search1turn1search2

Create the account:

```bash
az storage account create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$STORAGE_ACCOUNT" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-blob-public-access false
```

Get the connection string into a local shell variable:

```bash
export AZURE_STORAGE_CONNECTION_STRING="$(az storage account show-connection-string \
  --resource-group "$RESOURCE_GROUP" \
  --name "$STORAGE_ACCOUNT" \
  --query connectionString -o tsv)"
```

Create the container:

```bash
az storage container create \
  --name "$STORAGE_CONTAINER" \
  --account-name "$STORAGE_ACCOUNT" \
  --connection-string "$AZURE_STORAGE_CONNECTION_STRING"
```

The application streams thumbnails and videos through the API, so the Blob container does **not** need to be publicly readable.

## 7. Create Azure App Service

Create a Linux App Service plan:

```bash
az appservice plan create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$PLAN_NAME" \
  --location "$LOCATION" \
  --sku B1 \
  --is-linux
```

Create the web app:

```bash
az webapp create \
  --resource-group "$RESOURCE_GROUP" \
  --plan "$PLAN_NAME" \
  --name "$APP_NAME" \
  --runtime "PYTHON:3.11"
```

Enable App Service build automation so Azure installs `requirements.txt` during deployment. Microsoft's current documentation explicitly recommends `SCM_DO_BUILD_DURING_DEPLOYMENT=true` for this scenario. citeturn4search0turn4search1

```bash
az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APP_NAME" \
  --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true
```

## 8. Configure the FastAPI startup command

For Python 3.13 and earlier, Azure App Service requires a custom startup command for FastAPI. The project exposes `app.main:app`, so configure Gunicorn with Uvicorn workers. citeturn1search7

```bash
az webapp config set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APP_NAME" \
  --startup-file "gunicorn --bind=0.0.0.0:8000 --workers=2 --worker-class=uvicorn.workers.UvicornWorker app.main:app"
```

Two workers are enough for a small coursework deployment. Scaling out the App Service plan can add more instances later.

## 9. Configure application settings

Set the production database, Blob Storage, authentication and CORS values:

```bash
az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APP_NAME" \
  --settings \
    ENVIRONMENT=production \
    SECRET_KEY="$(openssl rand -hex 32)" \
    TOKEN_EXPIRY_MINUTES=120 \
    DATABASE_URL="postgresql+psycopg://$PG_ADMIN:$PG_PASSWORD@$PG_NAME.postgres.database.azure.com:5432/$DB_NAME?sslmode=require" \
    STORAGE_BACKEND=azure \
    AZURE_CONNECTION_STRING="$AZURE_STORAGE_CONNECTION_STRING" \
    AZURE_CONTAINER="$STORAGE_CONTAINER" \
    MEDIA_ROOT="/home/data/media" \
    MAX_UPLOAD_MB=200 \
    CACHE_TTL_SECONDS=30 \
    RATE_LIMIT_REQUESTS=100 \
    RATE_LIMIT_WINDOW_SECONDS=60 \
    CORS_ORIGINS="https://$APP_NAME.azurewebsites.net"
```

**Do not commit these values to GitHub.** Azure App Service application settings are exposed to the application as environment variables. For stronger production security, move secrets to Azure Key Vault and reference them from App Service.

## 10. Database initialization

The current application calls `Base.metadata.create_all()` during application startup. That is convenient for this coursework because the empty PostgreSQL database can create the required tables automatically.

For a production system with ongoing schema evolution, introduce Alembic migrations and run:

```bash
alembic upgrade head
```

as a controlled pre-deployment migration step. Do not rely on `create_all()` for destructive or complex production schema changes.

## 11. Local validation before deployment

From the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Linux/macOS:

```bash
python -m pytest tests -q
```

Expected result for the existing test suite is the full passing suite documented in the repository README. The CI pipeline uses the same test command.

## 12. First manual Azure deployment

Before configuring GitHub Actions, it is useful to prove that the Azure resources and application configuration work.

```bash
az webapp up \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APP_NAME" \
  --runtime "PYTHON:3.11" \
  --sku B1
```

Alternatively, use a ZIP deployment. Azure documents ZIP deployment with build automation enabled through `SCM_DO_BUILD_DURING_DEPLOYMENT`. citeturn4search1turn4search4

Check the application:

```bash
az webapp browse --resource-group "$RESOURCE_GROUP" --name "$APP_NAME"
```

Then verify:

```text
https://YOUR-APP.azurewebsites.net/
https://YOUR-APP.azurewebsites.net/docs
```

The `/docs` endpoint should show FastAPI Swagger UI.

## 13. GitHub Actions CI/CD

The repository now contains:

```text
.github/workflows/ci-cd.yml
```

The workflow performs:

```text
Pull Request → main
      │
      ▼
Install dependencies → pytest
      │
      └── fail → deployment stops

Push → main
      │
      ▼
Install dependencies → pytest
      │
      ▼
Azure OIDC login
      │
      ▼
azure/webapps-deploy@v3
      │
      ▼
Azure App Service
```

Microsoft's current App Service documentation recommends GitHub Actions and supports OpenID Connect authentication with `azure/login@v2` and deployment with `azure/webapps-deploy@v3`. citeturn2search0turn2search1

### 13.1 Create an Entra application for GitHub OIDC

Set:

```bash
export GITHUB_OWNER="MrYubii"
export GITHUB_REPO="videostream"
```

Create an app registration:

```bash
export APP_ID="$(az ad app create \
  --display-name "github-videostream-cicd" \
  --query appId -o tsv)"
```

Create the service principal:

```bash
az ad sp create --id "$APP_ID"
```

Grant it Contributor access to the coursework resource group. For stricter least privilege, use a more specific Website Contributor scope after the initial deployment is working.

```bash
export SUBSCRIPTION_ID="$(az account show --query id -o tsv)"

az role assignment create \
  --assignee "$APP_ID" \
  --role Contributor \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP"
```

Create the GitHub OIDC federated credential:

```bash
cat > /tmp/github-oidc.json <<EOF
{
  "name": "github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:$GITHUB_OWNER/$GITHUB_REPO:ref:refs/heads/main",
  "description": "GitHub Actions main branch deployment",
  "audiences": ["api://AzureADTokenExchange"]
}
EOF

az ad app federated-credential create \
  --id "$APP_ID" \
  --parameters /tmp/github-oidc.json
```

Record:

```text
AZURE_CLIENT_ID       = APP_ID
AZURE_TENANT_ID       = your Entra tenant ID
AZURE_SUBSCRIPTION_ID = your Azure subscription ID
```

## 14. Add GitHub Actions secrets and variable

In GitHub:

```text
Repository → Settings → Secrets and variables → Actions
```

Add **repository secrets**:

```text
AZURE_CLIENT_ID
AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID
```

Add a **repository variable**:

```text
AZURE_WEBAPP_NAME = YOUR-APP-NAME
```

Do not add the PostgreSQL password or Blob connection string to GitHub Actions. Those belong in Azure App Service configuration/Key Vault.

## 15. Test the pipeline

Create a small commit on a feature branch and open a Pull Request to `main`.

Expected:

1. GitHub Actions starts.
2. Python 3.11 is installed.
3. Dependencies are installed.
4. `pytest tests -q` executes.
5. A failing test blocks deployment.

After merging to `main`:

1. CI runs again.
2. Azure OIDC authentication occurs.
3. `azure/webapps-deploy@v3` deploys the repository.
4. App Service runs the configured Gunicorn startup command.
5. Oryx installs `requirements.txt` because `SCM_DO_BUILD_DURING_DEPLOYMENT=true`.

## 16. Validate authentication after deployment

### Consumer

Open:

```text
https://YOUR-APP.azurewebsites.net/signup.html
```

Register a consumer and then sign in.

Expected API flow:

```http
POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me
```

### Creator

1. Sign in as the seeded/admin account or another administrator.
2. Open the admin panel.
3. Create a creator account.
4. Sign out.
5. Open `/creator-login.html`.
6. Sign in with the new creator credentials.
7. Verify the Upload control appears.
8. Upload a video with Title, Publisher, Producer, Genre and Age Rating.

A consumer attempting `POST /api/videos` must receive `403 Forbidden`.

## 17. Validate video processing and streaming

After creator upload:

```text
processing → FFmpeg probe/transcode → thumbnail → ready
```

Verify:

```http
GET /api/videos
GET /api/videos/{id}
GET /api/videos/{id}/thumbnail
GET /api/videos/{id}/stream
```

Use browser seeking to demonstrate HTTP Range support. The response should include `206 Partial Content` for a valid Range request.

## 18. Backend evidence for the 5-minute demonstration

Show the Azure portal and deployed application together. A strong demonstration sequence is:

1. GitHub Actions successful CI/CD run.
2. Azure App Service overview and deployed URL.
3. Swagger `/docs` showing REST endpoints.
4. Admin creates a creator.
5. Creator signs in.
6. Creator uploads a video and metadata.
7. Backend initially returns `processing`.
8. Background media processing changes the video to `ready`.
9. Consumer signs in and watches the video.
10. Consumer comments, rates and reacts.
11. Show the PostgreSQL/Blob resources receiving application data.
12. Explain where scalability is achieved and identify remaining limitations.

This directly supports the coursework requirement that the recorded demonstration shows both solution functionality and deployment/backend activity.

## 19. Optional scale-out enhancements

### Azure Managed Redis

The original repository documentation mentioned Azure Cache for Redis. For a new 2026 deployment, prefer **Azure Managed Redis** rather than creating a new Azure Cache for Redis instance. Microsoft says Azure Cache for Redis is being retired and recommends migration to Azure Managed Redis; Basic/Standard/Premium instances are scheduled for retirement in 2028. citeturn0search0turn0search2turn0search13

Use Redis for:

- distributed dashboard cache;
- distributed rate limiting;
- future session/state coordination.

The current application keeps the local TTL cache as a coursework-friendly default. Redis should be added when running multiple App Service instances.

### Azure Front Door

Add Azure Front Door when you want:

- custom DNS;
- managed TLS;
- WAF rules;
- edge caching/routing;
- a single public entry point in front of App Service.

## 20. Monitoring

Enable Application Insights/Azure Monitor and record:

- request count;
- average response time;
- failed requests/HTTP 5xx;
- CPU and memory;
- App Service instance count;
- database performance;
- Blob storage usage.

These measurements provide evidence for the coursework rubric's scalability/performance evaluation rather than relying only on qualitative claims.

## 21. Security checklist

- [ ] HTTPS only.
- [ ] Strong random `SECRET_KEY`.
- [ ] Production CORS allow-list.
- [ ] PostgreSQL SSL enabled.
- [ ] Blob public access disabled.
- [ ] Secrets not committed to GitHub.
- [ ] Key Vault considered for production secrets.
- [ ] Consumer cannot self-register as creator/admin.
- [ ] Creator upload role enforced server-side.
- [ ] Creator ownership checks enforced server-side.
- [ ] Upload MIME type, extension and size validation enabled.
- [ ] Rate limiting enabled.
- [ ] GitHub Actions uses OIDC rather than a long-lived Azure password.

## 22. Rollback

If a deployment breaks the application:

1. Open GitHub Actions and identify the last successful commit.
2. Revert the bad commit and push to `main`, or deploy the previous known-good commit.
3. If using App Service deployment slots, deploy to staging first and swap only after validation.
4. Do not manually edit production source code in the App Service container.

## 23. Final acceptance checklist

- [ ] Azure resource group exists.
- [ ] PostgreSQL Flexible Server exists.
- [ ] `videostream` database exists.
- [ ] Blob Storage account/container exists.
- [ ] App Service is running Linux/Python 3.11.
- [ ] `SCM_DO_BUILD_DURING_DEPLOYMENT=true`.
- [ ] Gunicorn/Uvicorn startup command configured.
- [ ] Production `DATABASE_URL` configured.
- [ ] Azure Blob settings configured.
- [ ] Consumer registration works.
- [ ] Consumer login works.
- [ ] Admin can create creators.
- [ ] Creator login works.
- [ ] Consumer cannot upload.
- [ ] Creator can upload.
- [ ] Media reaches `ready`.
- [ ] Thumbnail displays.
- [ ] Range streaming works.
- [ ] Comments/ratings/reactions persist.
- [ ] GitHub Actions tests pass.
- [ ] GitHub Actions deploys `main` automatically.
- [ ] Azure logs show successful startup.
- [ ] Demonstration evidence has been recorded.
