import { createParser } from "@/app/api/eventsource-parser.js";

function normalizeVoiceErrorMessage(reason) {
  const text = String(reason || "").trim();
  if (!text) return "Voice streaming turn failed.";
  return text;
}

export async function streamRecordedVoiceTurn({
  audio_b64,
  sample_rate_hz,
  session_id,
  domain,
  language = "en-US",
  onAudioChunk,
  onFinalText,
  onTranscript,
  stream = false,
}) {
  const response = await fetch("/api/Voice/agent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id,
      audio_b64,
      sample_rate_hz,
      domain,
      language,
      stream,
    }),
  });

  if (stream && response.headers.get("content-type")?.includes("text/event-stream")) {
    if (!response.ok || !response.body) {
      throw new Error(normalizeVoiceErrorMessage("Voice stream failed."));
    }

    let transcript = "";
    let finalText = "";
    let streamedText = "";
    let guardrailBlocked = false;
    const audioChunks = [];
    let playChain = Promise.resolve();

    const parser = createParser((ev) => {
      if (ev.type !== "event") return;
      if (ev.event === "input") {
        try {
          const d = JSON.parse(ev.data);
          const t = String(d.transcript || "").trim();
          if (t) {
            transcript = t;
            onTranscript?.(t);
          }
        } catch {
          /* ignore */
        }
        return;
      }
      if (ev.event === "final_text") {
        try {
          const raw = JSON.parse(ev.data);
          finalText =
            typeof raw === "string"
              ? raw
              : String(raw?.text ?? raw ?? "").trim();
        } catch {
          finalText = String(ev.data || "").trim();
        }
        if (finalText) onFinalText?.(finalText);
        return;
      }
      if (ev.event === "audio") {
        let d = {};
        try {
          d = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (!d?.audio_b64) return;
        audioChunks.push(d);
        if (onAudioChunk) {
          playChain = playChain.then(() => onAudioChunk(d));
        }
        return;
      }
      if (ev.event === "text") {
        try {
          const raw = JSON.parse(ev.data);
          const part =
            typeof raw === "string" ? raw : String(raw?.text ?? raw ?? "");
          if (part) streamedText += part;
        } catch {
          streamedText += String(ev.data || "");
        }
        return;
      }
      if (ev.event === "done") {
        try {
          const d = JSON.parse(ev.data);
          if (d?.guardrail) guardrailBlocked = true;
        } catch {
          /* ignore */
        }
      }
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        parser.feed(decoder.decode(value, { stream: true }));
      }
      parser.flush();
      if (!finalText) {
        const fallbackText = String(streamedText || "").trim();
        if (fallbackText) {
          finalText = fallbackText;
          onFinalText?.(fallbackText);
        }
      }
      await playChain;
    } finally {
      reader.releaseLock?.();
    }

    return {
      ok: true,
      transcript,
      final_text: finalText,
      audio_chunks: audioChunks.sort(
        (a, b) => Number(a?.index ?? 0) - Number(b?.index ?? 0)
      ),
      guardrail_blocked: guardrailBlocked,
    };
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(normalizeVoiceErrorMessage(data?.error || data?.detail || "Voice request failed."));
  }

  const finalText = String(data?.final_text || "").trim();
  const transcript = String(data?.transcript || "").trim();
  if (finalText && onFinalText) {
    onFinalText(finalText);
  }

  const chunks = Array.isArray(data?.audio_chunks) ? data.audio_chunks : [];
  chunks.sort((a, b) => Number(a?.index ?? 0) - Number(b?.index ?? 0));

  for (const chunk of chunks) {
    if (chunk?.audio_b64 && onAudioChunk) {
      await onAudioChunk(chunk);
    }
  }

  return {
    ok: true,
    transcript,
    final_text: finalText,
    audio_chunks: chunks,
    guardrail_blocked: Boolean(data?.guardrail_blocked),
  };
}
