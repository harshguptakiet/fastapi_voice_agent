# FastAPI Voice Agent (Strict Minimal)

Minimal backend centered on one unified workflow:

`Client -> /agent/stream -> Input Router (text/audio) -> Orchestrator (RAG + LLM stream) -> Response Guard -> Sentence Buffer -> SSE text/audio events`

## Conversation Memory

- Short-term memory: Redis list per `tenant_id + session_id` (recent turns for active chat context).
- Long-term memory: Qdrant vector memory per `tenant_id + session_id` (semantic recall of prior turns).
- Prompt assembly now includes:
	- recent short-term chat history
	- semantic recalls from long-term memory
	- optional knowledge/RAG context

Set these env vars for memory:

```env
REDIS_URL=redis://127.0.0.1:6379/0
QDRANT_URL=http://127.0.0.1:6333

SHORT_TERM_MEMORY_MAX_MESSAGES=16
SHORT_TERM_MEMORY_TTL_SECONDS=7200
SHORT_TERM_MEMORY_PROMPT_MESSAGES=8

LONG_TERM_MEMORY_NAMESPACE=conversation-memory-v1
LONG_TERM_MEMORY_TOP_K=4
LONG_TERM_MEMORY_MAX_TEXT_CHARS=700
```

## Active Endpoints

- `POST /agent/stream` (primary, unified text/audio SSE)
- `POST /voice/transcribe` (STT utility)
- `POST /voice/synthesize` (TTS utility)
- `POST /documents/upload` (ingest + extract + reindex)
- `POST /knowledge/reindex`
- `POST /knowledge/search`
- `POST /knowledge/evaluate`
- `DELETE /knowledge/documents/{doc_id}`
- `GET /status`
- `GET /status/storage`
- `GET /status/knowledge`
- `GET /voice/health`
- `GET /health`

Tenant scoped endpoints require:

```http
X-Tenant-Id: tenant-demo
```

## Run

```bash
python -m uvicorn app.main:app --reload
```

## `/agent/stream` Example

```json
{
	"session_id": "s-001",
	"input_type": "text",
	"text": "Give a short summary of India.",
	"language": "en-US",
	"provider": "gemini",
	"use_knowledge": true,
	"knowledge_top_k": 3,
	"output_audio": false
}
```

SSE events emitted:

- `input`
- `status`
- `text`
- `metrics`
- `final_text`
- `audio` (when `output_audio=true`)
- `done`

