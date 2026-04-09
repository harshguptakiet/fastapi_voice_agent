/**
 * Single FastAPI backend (agent stream, /voice/*, /documents/*).
 * TEKURIOUS_AI_BASE_URL / EDUTHUM_BASE_URL are checked before FASTAPI_VOICE_BASE_URL
 * so one server on 8010 works even if legacy FASTAPI_* vars still point at 8001.
 */
const DEFAULT_FASTAPI_BASE = "http://127.0.0.1:8010";

export function getFastApiBaseUrl() {
  const raw =
    process.env.TEKURIOUS_FASTAPI_URL ||
    process.env.TEKURIOUS_AI_BASE_URL ||
    process.env.EDUTHUM_BASE_URL ||
    process.env.FASTAPI_BASE_URL ||
    process.env.FASTAPI_VOICE_BASE_URL ||
    DEFAULT_FASTAPI_BASE;
  return String(raw).trim().replace(/\/+$/, "");
}

export function getFastApiTenantId() {
  return String(process.env.FASTAPI_TENANT_ID || "tenant-demo").trim();
}
