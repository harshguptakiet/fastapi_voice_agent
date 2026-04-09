# AWS Deployment Runbook

**End-to-end steps (Vercel + AWS):** see [`../DEPLOYMENT.md`](../DEPLOYMENT.md).

This folder contains deploy artifacts for your full stack:

- Frontend (Next.js): `tekurious-chatbot-main/tekurious-chatbot-ui`
- FastAPI gateway/server: `fastapi_server`
- Religious bot: `tekurious-chatbot-main/bots/religious-ai/src`
- Education bot: `tekurious-chatbot-main/bots/education-ai/src`

## What has been prepared

1. Dockerfiles for all four services.
2. ECS task definition templates.
3. Step checklist for manual AWS setup.

## Service ports

1. Frontend: 3000
2. FastAPI: 8001
3. Religious bot: 8000
4. Education bot: 8002

## Quick local build test

From repository root, run:

1. `docker build -t chatbot-frontend ./tekurious-chatbot-main/tekurious-chatbot-ui`
2. `docker build -t fastapi-server ./fastapi_server`
3. `docker build -t religious-bot ./tekurious-chatbot-main/bots/religious-ai/src`
4. `docker build -t education-bot ./tekurious-chatbot-main/bots/education-ai/src`

## Important production changes required

1. Replace localhost URLs with production/internal endpoints.
2. Store API keys in Secrets Manager.
3. Use private networking between FastAPI and bot services.
4. Expose only frontend and FastAPI through ALB.

## Suggested rollout order

1. Deploy religious-bot and education-bot (private).
2. Deploy fastapi-server and verify internal connectivity.
3. Deploy frontend and route to FastAPI public endpoint.
4. Run voice end-to-end validation.

See checklist: `deployment/aws/deploy-checklist.md`.
