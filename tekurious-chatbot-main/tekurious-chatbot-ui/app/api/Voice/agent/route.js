import { NextResponse } from "next/server";
import {
  RELIGIOUS_FALLBACK,
  EDUCATION_FALLBACK,
  isReligiousTopicAllowedByIntent,
  isEducationTopicAllowedByIntent,
} from "@/lib/domain-guardrails";
import { createParser } from "../../eventsource-parser.js";
import {
  getFastApiBaseUrl,
  getFastApiTenantId,
} from "@/lib/fastapi-backend";

function getDomain(value) {
  const domain = String(value || "").trim().toLowerCase();
  return domain === "education" || domain === "religious" ? domain : "";
}

/**
 * Speech-safe clip: keep up to two sentences (answer + optional follow-up), within maxChars.
 * Matches FastAPI VOICE_AGENT_POLICY (concise but may end with a short follow-up question).
 */
function clampVoiceAssistantReply(text, maxChars = 280) {
  const t = String(text || "").trim().replace(/\s+/g, " ");
  if (!t) return "";
  const parts = t.split(/(?<=[.!?])\s+/).filter(Boolean);
  let out = parts.slice(0, 2).join(" ").trim() || t;
  if (out.length > maxChars) {
    const slice = out.slice(0, maxChars - 3);
    const lastSpace = slice.lastIndexOf(" ");
    out =
      (lastSpace > 20 ? slice.slice(0, lastSpace) : slice).trim() + "...";
  }
  return out;
}

async function synthesizeText(baseUrl, language, text) {
  const ttsResponse = await fetch(`${baseUrl}/voice/synthesize`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Tenant-Id": getFastApiTenantId(),
    },
    body: JSON.stringify({ text, language }),
  });

  const ttsData = await ttsResponse.json().catch(() => ({}));
  if (!ttsResponse.ok || !ttsData?.audio_b64) return null;

  return {
    final_text: text,
    audio_chunks: [
      {
        index: 0,
        text,
        mime_type: ttsData.mime_type || "audio/mpeg",
        audio_b64: ttsData.audio_b64,
      },
    ],
  };
}

async function streamAgentTextOnly(baseUrl, agentPayload) {
  const upstreamResponse = await fetch(`${baseUrl}/agent/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Tenant-Id": getFastApiTenantId(),
    },
    body: JSON.stringify(agentPayload),
  });

  if (!upstreamResponse.ok) {
    const errText = await upstreamResponse.text().catch(() => "");
    return {
      ok: false,
      status: upstreamResponse.status,
      mergedReply: "",
      failReason: errText || `Upstream ${upstreamResponse.status}`,
    };
  }
  if (!upstreamResponse.body) {
    return {
      ok: false,
      status: 502,
      mergedReply: "",
      failReason: "No response body",
    };
  }

  let finalText = "";
  let streamText = "";
  let doneOk = true;
  let failReason = "";
  const decoder = new TextDecoder();
  const parser = createParser((event) => {
    if (event.type !== "event") return;
    if (event.event === "final_text") {
      try {
        const data = JSON.parse(event.data);
        finalText = typeof data === "string" ? data : String(data?.text || "");
      } catch {
        finalText = event.data;
      }
    }
    if (event.event === "text") {
      try {
        const data = JSON.parse(event.data);
        streamText +=
          typeof data === "string" ? data : String(data?.text || "");
      } catch {
        streamText += event.data;
      }
    }
    if (event.event === "done") {
      try {
        const data = JSON.parse(event.data);
        doneOk = data.ok !== false;
        failReason = String(data.reason || "");
      } catch {
        doneOk = true;
      }
    }
  });

  for await (const chunk of upstreamResponse.body) {
    parser.feed(decoder.decode(chunk));
  }
  parser.flush();

  const mergedReply = String(finalText || streamText || "").trim();
  return {
    ok: doneOk,
    status: 200,
    mergedReply,
    failReason,
  };
}

export async function POST(request) {
  let body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  if (!body?.audio_b64 || !body?.sample_rate_hz) {
    return NextResponse.json(
      { error: "audio_b64 and sample_rate_hz are required." },
      { status: 400 }
    );
  }

  const baseUrl = getFastApiBaseUrl();
  const sampleRateHz = Number(body.sample_rate_hz || 16000);
  const language = body.language || "en-US";
  const domain = getDomain(body.domain);
  const sessionId = body.session_id || `voice-${Date.now()}`;
  const wantsStream = Boolean(body.stream);

  try {
    // STT is handled by FastAPI in this pipeline; we keep it here to validate transcript + apply intent guardrails.
    let transcriptText = "";
    try {
      const sttResponse = await fetch(`${baseUrl}/voice/transcribe`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Tenant-Id": getFastApiTenantId(),
        },
        body: JSON.stringify({
          audio: {
            audio_b64: String(body.audio_b64),
            sample_rate_hz: sampleRateHz,
            transport: "http",
          },
          language,
        }),
      });

      const sttData = await sttResponse.json().catch(() => ({}));
      if (sttResponse.ok) transcriptText = String(sttData.text || "").trim();
    } catch {
      /* handled below */
    }

    if (!transcriptText) {
      return NextResponse.json(
        { error: "No speech detected. Please speak clearly and try again.", transcript: "" },
        { status: 422 }
      );
    }

    // Domain guardrails (prevents streaming a disallowed answer).
    if (domain) {
      const allowed =
        domain === "religious"
          ? isReligiousTopicAllowedByIntent(transcriptText)
          : isEducationTopicAllowedByIntent(transcriptText);

      if (!allowed) {
        const fallbackText = domain === "religious" ? RELIGIOUS_FALLBACK : EDUCATION_FALLBACK;
        const shortFallback = clampVoiceAssistantReply(fallbackText, 200);

        const voicedFallback = await synthesizeText(baseUrl, language, shortFallback);
        if (!voicedFallback || voicedFallback.audio_chunks.length === 0) {
          return NextResponse.json(
            { error: "Voice synthesis failed for fallback response.", transcript: transcriptText },
            { status: 502 }
          );
        }

        return NextResponse.json({
          session_id: sessionId,
          transcript: transcriptText,
          final_text: shortFallback,
          audio_chunks: voicedFallback.audio_chunks,
          guardrail_blocked: true,
          guardrail_source: `chatbot_${domain}`,
          voice_reply_only: true,
        });
      }
    }

    const agentPayloadBase = {
      session_id: sessionId,
      input_type: "voice",
      text: transcriptText,
      language,
      use_knowledge: true,
      knowledge_top_k: 3,
    };
    if (domain) agentPayloadBase.domain = domain;

    if (wantsStream) {
      // Pass through FastAPI SSE directly so audio can start as soon as the backend emits it.
      const upstreamResponse = await fetch(`${baseUrl}/agent/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Tenant-Id": getFastApiTenantId(),
        },
        body: JSON.stringify({ ...agentPayloadBase, output_audio: true }),
      });

      if (!upstreamResponse.ok) {
        const errText = await upstreamResponse.text().catch(() => "");
        return NextResponse.json(
          { error: errText || "Voice agent stream failed.", transcript: transcriptText },
          { status: 502 }
        );
      }
      if (!upstreamResponse.body) {
        return NextResponse.json(
          { error: "No response body from voice agent.", transcript: transcriptText },
          { status: 502 }
        );
      }

      const upstreamBody = upstreamResponse.body;
      const stream = new ReadableStream({
        async start(controller) {
          const reader = upstreamBody.getReader();
          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              if (value?.byteLength) controller.enqueue(value);
            }
          } finally {
            reader.releaseLock?.();
            controller.close();
          }
        },
      });

      return new Response(stream, {
        status: 200,
        headers: {
          "Content-Type": "text/event-stream; charset=utf-8",
          "Cache-Control": "no-cache, no-transform",
          Connection: "keep-alive",
          "X-Accel-Buffering": "no",
        },
      });
    }

    // Non-stream (legacy): stream text only, then synthesize a single TTS clip.
    const agentPayload = { ...agentPayloadBase, output_audio: false };
    const { ok, mergedReply, failReason } = await streamAgentTextOnly(baseUrl, agentPayload);
    if (!ok) {
      return NextResponse.json(
        { error: failReason || "Voice agent failed.", transcript: transcriptText },
        { status: 502 }
      );
    }

    const shortText =
      clampVoiceAssistantReply(mergedReply, 280) ||
      "I’m not sure how to answer that briefly. Please try rephrasing.";

    const voiced = await synthesizeText(baseUrl, language, shortText);
    if (!voiced || voiced.audio_chunks.length === 0) {
      return NextResponse.json(
        { error: "Voice synthesis failed.", transcript: transcriptText },
        { status: 502 }
      );
    }

    return NextResponse.json({
      session_id: sessionId,
      transcript: transcriptText,
      final_text: shortText,
      audio_chunks: voiced.audio_chunks.filter((c) => c.audio_b64),
      guardrail_source: domain ? `chatbot_${domain}` : "pipeline",
      voice_reply_only: true,
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: "Voice agent service is unreachable.",
        detail: String(error?.message || error),
      },
      { status: 502 }
    );
  }
}

