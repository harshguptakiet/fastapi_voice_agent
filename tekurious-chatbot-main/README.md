# Darshan AI Monorepo

This repository now contains one shared UI and two bot backends.

## Folder structure

- `tekurious-chatbot-ui/` - shared Next.js UI.
- `bots/religious-ai/` - Darshan AI backend (religious domain).
- `bots/education-ai/` - Tekurious backend (education domain).

## Run both bots locally

### 1) Darshan AI backend

```powershell
cd c:\tekurious-chatbot-main\bots\religious-ai\src
python -m venv ..\.venv
..\.venv\Scripts\activate
pip install -r requirements.txt
python -m server.main
```

Default port: `8000`

### 2) Tekurious backend

Open another terminal:

```powershell
cd c:\tekurious-chatbot-main\bots\education-ai\src
python -m venv ..\.venv
..\.venv\Scripts\activate
pip install -r requirements.txt
$env:PORT="8002"
python -m server.main
```

Default local port for Tekurious in UI proxy: `8002`.

### 3) Shared UI

```powershell
cd c:\tekurious-chatbot-main\tekurious-chatbot-ui
npm install
npm run dev
```

## Environment setup

- Backend env files:
	- `bots/religious-ai/src/.env.example` -> `bots/religious-ai/src/.env`
	- `bots/education-ai/src/.env.example` -> `bots/education-ai/src/.env`
- UI env file:
	- `tekurious-chatbot-ui/.env.local.example` -> `tekurious-chatbot-ui/.env.local`

## API routing in UI

The UI proxies through `tekurious-chatbot-ui/app/api/*`:

- `ReligiousAI` route uses `DARSHAN_AI_BASE_URL`.
- `Eduthum` routes use `TEKURIOUS_AI_BASE_URL` (fallback: `EDUTHUM_BASE_URL`) and `EDUTHUM_STUDENT_ID`.
