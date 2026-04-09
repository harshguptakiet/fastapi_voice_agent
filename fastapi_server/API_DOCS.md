# API Documentation for FastAPI Server

## Endpoints

### /agent/stream (POST)
- Streams agent responses for text/voice input.
- Guardrails enforced for domain (religious/education).
- Returns: SSE events with final_text, audio, done, etc.

### /agent/ws (WebSocket)
- Real-time voice/text agent interaction.
- Guardrails enforced for domain (religious/education).
- Returns: JSON events for input, final_text, audio, done, etc.

### /health (GET)
- Health check endpoint.
- Returns: `{ "status": "ok" }`

## Error Handling
- All endpoints return user-friendly errors for input normalization and LLM failures.
- Guardrails return fallback and explanation if out-of-scope.

## Guardrails
- Strictly enforced for all input types.
- Only Indian mythology (plus greetings) for religious.
- Only CBSE 9/10 for education.
- Returns YES/NO + explanation.

## Rate Limiting
- (To be added) All endpoints will be protected by rate limiting middleware.

## LLM Prompt Safety
- (To be added) User input will be sanitized before LLM calls to prevent prompt injection.

## Health Checks
- /health endpoint for ECS and monitoring.

## Deployment
- See deployment/aws/ for scripts and task definitions.

## Environment Variables
- FASTAPI_VOICE_BASE_URL, FASTAPI_TENANT_ID, etc.

---

For more details, see code comments and deployment/aws/README.md.
