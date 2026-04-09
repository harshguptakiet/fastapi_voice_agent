# Deploy: Vercel (frontend) + AWS Docker (FastAPI)

This matches the layout under `deployment/aws/` and `tekurious-chatbot-main/vercel.json`.

## Prerequisites

- **Git** repo pushed to GitHub/GitLab/Bitbucket (Vercel imports from Git).
- **AWS CLI** configured (`aws configure`) for Docker/ECR/ECS steps.
- **Docker Desktop** running for image builds.

---

## 1. Frontend → Vercel

### Recommended: Root directory = Next.js app

1. In [Vercel](https://vercel.com) → **Add New…** → **Project** → import your repository.
2. **Root Directory**: set to  
   `tekurious-chatbot-main/tekurious-chatbot-ui`  
   (if your repo root is the `MAIN` folder; if the repo is only `tekurious-chatbot-main`, use `tekurious-chatbot-ui`).
3. Framework preset: **Next.js** (auto-detected).
4. **Environment variables** (Production — and Preview if you want):

| Name | Example | Purpose |
|------|---------|---------|
| `TEKURIOUS_FASTAPI_URL` | `https://api.example.com` or `http://1.2.3.4:8001` | Primary backend URL (no trailing slash). |
| `FASTAPI_TENANT_ID` | `tenant-demo` | Tenant header for FastAPI. |

Optional fallbacks (same URL is fine): `TEKURIOUS_AI_BASE_URL`, `EDUTHUM_BASE_URL`, `FASTAPI_BASE_URL`, `FASTAPI_VOICE_BASE_URL`.

5. **Deploy**.

### Alternative: Monorepo Git root = `tekurious-chatbot-main` (leave Vercel “Root Directory” empty)

Use this when the connected Git folder is the monorepo and you do **not** set Vercel’s Root Directory to `tekurious-chatbot-ui`.

Repo `vercel.json` installs and builds **only** under `tekurious-chatbot-ui` (one `npm ci`, one lockfile — same as a normal Next app). The small **root** `package.json` only lists `next` / `react` / `react-dom` so Vercel’s framework check passes (it reads the repo root manifest).

**Commit** `tekurious-chatbot-ui/package-lock.json`. Do **not** add a root `package-lock.json` (avoids duplicate-lockfile noise).

**CLI from monorepo root:** `npx vercel deploy --prod`

**CLI when the linked project uses the UI folder:**  
`npx vercel deploy --prod --cwd tekurious-chatbot-ui`

---

## 2. FastAPI → Docker → AWS (ECR + ECS)

### What the repo already provides

| Item | Path |
|------|------|
| Dockerfile | `fastapi_server/Dockerfile` (listens on **8001**) |
| Push all service images | `deployment/aws/push-images.ps1` |
| Build + push + redeploy FastAPI only | `deployment/aws/redeploy-fastapi.ps1` |
| ECS task definition template | `deployment/aws/task-definitions/fastapi-server.task.json` |
| Full AWS checklist | `deployment/aws/deploy-checklist.md` |
| Short overview | `deployment/aws/README.md` |

### One-command FastAPI redeploy (typical)

From a PowerShell prompt on your machine (adjust paths if your clone is not `c:\New folder (6)\MAIN`):

```powershell
cd "c:\New folder (6)\MAIN\deployment\aws"
.\redeploy-fastapi.ps1 -AccountId YOUR_12_DIGIT_AWS_ACCOUNT_ID -Region us-east-1 -Cluster tekurious-prod -Service fastapi-server
```

Parameters:

- **`-AccountId`** — required; `aws sts get-caller-identity --query Account --output text`
- **`-Region`** — default `us-east-1`
- **`-Cluster` / `-Service`** — must match your ECS cluster and service name

The script builds `fastapi_server`, pushes to ECR `fastapi-server:<tag>`, registers a new task definition, and forces a new deployment.

**Note:** Scripts default to `$RepoRoot = "c:/New folder (6)/MAIN"`. If your repo lives elsewhere, edit `RepoRoot` in `redeploy-fastapi.ps1` and `push-images.ps1`.

### Push all four images (optional)

```powershell
.\push-images.ps1 -AccountId YOUR_ACCOUNT_ID -Region us-east-1 -Tag v2026-03-29-1
```

Builds: `chatbot-frontend`, `fastapi-server`, `religious-bot`, `education-bot`.

### Get FastAPI base URL for Vercel

After ECS is running:

```powershell
.\print-fastapi-vercel-env.ps1 -Region us-east-1 -Cluster tekurious-prod -Service fastapi-server
```

Copy the printed `TEKURIOUS_FASTAPI_URL` value into Vercel → Environment Variables → Production → **Redeploy** the frontend.

---

## 3. Production details

- **Port:** Docker/ECS use **8001** for FastAPI. Local dev may use **8010**; set Vercel to whatever URL/port your deployed API exposes (often **443** behind HTTPS, not `:8001` in the public URL).
- **CORS:** Default `CORS_ALLOW_ORIGINS=*` with `allow_credentials=false` (valid for `*`). For browser credentialed calls from a fixed origin, set `CORS_ALLOW_ORIGINS=https://your-app.vercel.app` and optionally `CORS_ALLOW_CREDENTIALS=true`.
- **Vercel uploads:** `app/api/Eduthum/route.js` caps PDF size at **4 MB** when `VERCEL=1` (platform body limits). For larger files, use direct-to-S3 uploads or a non-serverless path.
- **Secrets:** Prefer AWS Secrets Manager for API keys (see `fastapi-server.task.json` `secrets` block).
- **Stable URL:** For production, use an **ALB + HTTPS** (see `deploy-checklist.md`) instead of relying on changing task public IPs.

---

## 4. Quick validation

- Backend: `GET https://<your-api-host>/health` (or `http://<ip>:8001/health`).
- Frontend: open the Vercel URL and send a chat message; confirm network calls hit your FastAPI host.
