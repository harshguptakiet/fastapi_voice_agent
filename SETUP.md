# Project Setup Guide

This guide explains exactly what a new user must configure after cloning this repository.

## 1) Prerequisites

- Python 3.11+ (for backend and bot services)
- Node.js 18+ (for UI)
- Redis (local or hosted)
- Qdrant (local or hosted)
- One LLM provider key:
  - Gemini, or
  - OpenAI

Optional for voice features:
- Deepgram API key
- ElevenLabs API key + voice id

## 2) Clone and open

```bash
git clone https://github.com/harshguptakiet/fastapi_voice_agent.git
cd fastapi_voice_agent
```

## 3) Backend setup (FastAPI)

Location: `fastapi_server`

### Install

```bash
cd fastapi_server
python -m venv .venv
# Windows PowerShell
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

### Create backend env file

Create `fastapi_server/.env` and set at least:

```env
ENV=dev
LLM_PROVIDER=gemini

# choose one provider
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-2.0-flash-lite
# OR
OPENAI_API_KEY=your_openai_key

# memory / retrieval
REDIS_URL=redis://127.0.0.1:6379/0
QDRANT_URL=http://127.0.0.1:6333
# optional if your qdrant requires auth
QDRANT_API_KEY=
```

Optional voice settings:

```env
USE_DEEPGRAM_ELEVENLABS=true
DEEPGRAM_API_KEY=
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
ELEVENLABS_MODEL_ID=elevenlabs/flash-v2.5
```

### Run backend

```bash
python -m uvicorn app.main:app --reload --port 8010
```

Health check:
- `http://127.0.0.1:8010/health`

## 4) Frontend setup (Next.js UI)

Location: `tekurious-chatbot-main/tekurious-chatbot-ui`

### Install

```bash
cd ../tekurious-chatbot-main/tekurious-chatbot-ui
npm install
```

### Create frontend env file

Copy `.env.local.example` to `.env.local` and set values:

```env
TEKURIOUS_FASTAPI_URL=http://127.0.0.1:8010
FASTAPI_BASE_URL=http://127.0.0.1:8010
FASTAPI_VOICE_BASE_URL=http://127.0.0.1:8010
FASTAPI_TENANT_ID=tenant-demo
```

### Run UI

```bash
npm run dev
```

## 5) Optional bot services

If running bot services directly:

- `tekurious-chatbot-main/bots/education-ai/src/.env.example` -> copy to `.env`
- `tekurious-chatbot-main/bots/religious-ai/src/.env.example` -> copy to `.env`

Fill provider keys:
- `GOOGLE_API_KEY` or `OPENAI_API_KEY`
- optional speech keys for `/s2s`

## 6) AWS ECS deployment requirements

If deploying with ECS task definitions in `deployment/aws/task-definitions`:

- Configure AWS IAM/task execution role permissions for Secrets Manager.
- Create these secrets in AWS Secrets Manager:
  - `gemini-api-key`
  - `deepgram-api-key`
  - `elevenlabs-api-key`
  - `redis-url`
- Ensure task definitions reference secrets via `valueFrom` (not inline credentials).

## 7) Security checklist for contributors

- Never commit `.env`, `.env.local`, credentials, or private keys.
- Use `.env.example` files only for placeholders.
- Keep `.sfdx/` and local virtual environments untracked.
- If any credential is committed by mistake, rotate it immediately.

## 8) Quick start summary

1. Start Redis + Qdrant.
2. Run FastAPI backend from `fastapi_server` on port `8010`.
3. Run Next.js UI from `tekurious-chatbot-main/tekurious-chatbot-ui`.
4. Set API keys in local env files.
