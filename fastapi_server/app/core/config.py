import os

from dotenv import load_dotenv


# Load environment variables from .env if present
load_dotenv()


# Minimal app configuration
APP_NAME = os.getenv("APP_NAME", "Bot Backend")
ENV = os.getenv("ENV", "dev")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

# LLM configuration (provider-agnostic)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "dummy").strip() or "dummy"
LLM_MODEL: str | None = (os.getenv("LLM_MODEL") or None)

# Optional OpenAI-style configuration (used only by the OpenAI provider adapter)
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# Anthropic configuration
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_BASE_URL: str = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
ANTHROPIC_MODEL: str | None = os.getenv("ANTHROPIC_MODEL")

# Gemini configuration
GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
GEMINI_BASE_URL: str = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")
GEMINI_MODEL: str | None = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
GEMINI_TIMEOUT_SECONDS: float = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "18"))
GEMINI_MAX_OUTPUT_TOKENS: int = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "192"))
GEMINI_VOICE_MAX_OUTPUT_TOKENS: int = int(os.getenv("GEMINI_VOICE_MAX_OUTPUT_TOKENS", "80"))
GEMINI_TOP_P: float = float(os.getenv("GEMINI_TOP_P", "0.8"))
HTTP_CLIENT_TIMEOUT_SECONDS: float = float(os.getenv("HTTP_CLIENT_TIMEOUT_SECONDS", "12"))

DATABASE_URL = (os.getenv("DATABASE_URL") or "sqlite:///./bot.db").strip()

# Object storage configuration
OBJECT_STORAGE_PROVIDER: str = os.getenv("OBJECT_STORAGE_PROVIDER", "local")
OBJECT_STORAGE_BUCKET: str | None = os.getenv("OBJECT_STORAGE_BUCKET")
OBJECT_STORAGE_REGION: str | None = os.getenv("OBJECT_STORAGE_REGION")
OBJECT_STORAGE_ENDPOINT_URL: str | None = os.getenv("OBJECT_STORAGE_ENDPOINT_URL")
OBJECT_STORAGE_ACCESS_KEY: str | None = os.getenv("OBJECT_STORAGE_ACCESS_KEY")
OBJECT_STORAGE_SECRET_KEY: str | None = os.getenv("OBJECT_STORAGE_SECRET_KEY")
LOCAL_DOCUMENT_STORAGE_DIR: str = os.getenv("LOCAL_DOCUMENT_STORAGE_DIR", "storage/documents")

# Deepgram (STT) + ElevenLabs (TTS) configuration.
DEEPGRAM_API_KEY: str | None = os.getenv("DEEPGRAM_API_KEY")
DEEPGRAM_STT_URL: str = os.getenv("DEEPGRAM_STT_URL", "https://api.deepgram.com/v1/listen")
DEEPGRAM_MODEL: str = os.getenv("DEEPGRAM_MODEL", "nova-2")
DEEPGRAM_LANGUAGE: str = os.getenv("DEEPGRAM_LANGUAGE", "en-US")

ELEVENLABS_API_KEY: str | None = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_BASE_URL: str = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io/v1")
ELEVENLABS_VOICE_ID: str | None = os.getenv("ELEVENLABS_VOICE_ID")
ELEVENLABS_MODEL_ID: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

USE_DEEPGRAM_ELEVENLABS: bool = os.getenv(
    "USE_DEEPGRAM_ELEVENLABS", "false"
).lower() in {"1", "true", "yes"}


# Embedding configuration (adapter-style; defaults keep current behavior)
EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "local").strip().lower() or "local"
EMBEDDING_MODEL: str | None = (os.getenv("EMBEDDING_MODEL") or None)
EMBEDDING_DIMENSIONS: int = int(os.getenv("EMBEDDING_DIMENSIONS", "256"))
EMBEDDING_TIMEOUT_SECONDS: float = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "20"))
EMBEDDING_FALLBACK_TO_LOCAL: bool = _env_bool("EMBEDDING_FALLBACK_TO_LOCAL", True)
LOCAL_EMBEDDING_MODEL: str = os.getenv("LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

# Vector store configuration (adapter-style; defaults keep current behavior)
VECTOR_STORE_PROVIDER: str = os.getenv("VECTOR_STORE_PROVIDER", "memory").strip().lower() or "memory"
VECTOR_STORE_FALLBACK_TO_MEMORY: bool = _env_bool("VECTOR_STORE_FALLBACK_TO_MEMORY", True)

# Qdrant (used when VECTOR_STORE_PROVIDER=qdrant)
QDRANT_URL: str = os.getenv("QDRANT_URL", "http://127.0.0.1:6333").strip().rstrip("/")
QDRANT_API_KEY: str | None = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION_PREFIX: str = os.getenv("QDRANT_COLLECTION_PREFIX", "knowledge").strip() or "knowledge"
QDRANT_TIMEOUT_SECONDS: float = float(os.getenv("QDRANT_TIMEOUT_SECONDS", "20"))

# Retrieval pipeline configuration (Week 5 hardening)
RETRIEVAL_CANDIDATE_TOP_K: int = int(os.getenv("RETRIEVAL_CANDIDATE_TOP_K", "8"))
RETRIEVAL_LLM_TOP_K: int = int(os.getenv("RETRIEVAL_LLM_TOP_K", "3"))
SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.75"))
RETRIEVAL_CHUNK_CHAR_LIMIT: int = int(os.getenv("RETRIEVAL_CHUNK_CHAR_LIMIT", "700"))
RETRIEVAL_CONTEXT_TOP_K: int = int(os.getenv("RETRIEVAL_CONTEXT_TOP_K", "3"))
RETRIEVAL_TIMEOUT_SECONDS: float = float(os.getenv("RETRIEVAL_TIMEOUT_SECONDS", "0.25"))
RETRIEVAL_BUDGET_SECONDS: float = float(os.getenv("RETRIEVAL_BUDGET_SECONDS", "0.2"))
RETRIEVAL_EMPTY_STREAK_DISABLE: int = int(os.getenv("RETRIEVAL_EMPTY_STREAK_DISABLE", "2"))
FALLBACK_NO_KNOWLEDGE_RESPONSE: str = os.getenv(
    "FALLBACK_NO_KNOWLEDGE_RESPONSE",
    "I couldn't find relevant information in our documentation.",
)

# Retrieval cache
REDIS_URL: str | None = os.getenv("REDIS_URL")
RETRIEVAL_CACHE_TTL_SECONDS: int = int(os.getenv("RETRIEVAL_CACHE_TTL_SECONDS", "600"))
EMBEDDING_CACHE_ENABLED: bool = _env_bool("EMBEDDING_CACHE_ENABLED", True)
EMBEDDING_CACHE_TTL_SECONDS: int = int(os.getenv("EMBEDDING_CACHE_TTL_SECONDS", "3600"))

# Conversation memory
SHORT_TERM_MEMORY_MAX_MESSAGES: int = int(os.getenv("SHORT_TERM_MEMORY_MAX_MESSAGES", "16"))
SHORT_TERM_MEMORY_TTL_SECONDS: int = int(os.getenv("SHORT_TERM_MEMORY_TTL_SECONDS", "7200"))
SHORT_TERM_MEMORY_PROMPT_MESSAGES: int = int(os.getenv("SHORT_TERM_MEMORY_PROMPT_MESSAGES", "8"))
LONG_TERM_MEMORY_NAMESPACE: str = os.getenv("LONG_TERM_MEMORY_NAMESPACE", "conversation-memory-v1")
LONG_TERM_MEMORY_TOP_K: int = int(os.getenv("LONG_TERM_MEMORY_TOP_K", "4"))
LONG_TERM_MEMORY_MAX_TEXT_CHARS: int = int(os.getenv("LONG_TERM_MEMORY_MAX_TEXT_CHARS", "700"))
LONG_TERM_MEMORY_TIMEOUT_SECONDS: float = float(os.getenv("LONG_TERM_MEMORY_TIMEOUT_SECONDS", "0.4"))
