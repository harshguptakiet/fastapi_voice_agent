

import { NextResponse } from "next/server";
import {
  RELIGIOUS_FALLBACK,
  isReligiousTopicAllowedByIntent,
} from "@/lib/domain-guardrails";
import { createParser } from "../eventsource-parser.js";
import {
  getFastApiBaseUrl,
  getFastApiTenantId,
} from "@/lib/fastapi-backend";

export async function POST(request) {
  let body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ response: "Invalid JSON body." }, { status: 400 });
  }
  const { query, session_id } = body;
  const normalizedQuery = String(query ?? "").trim();
  const sid = session_id || `religious-${Date.now()}`;

  if (!isReligiousTopicAllowedByIntent(normalizedQuery)) {
    return NextResponse.json({ response: RELIGIOUS_FALLBACK });
  }

  const baseUrl = getFastApiBaseUrl();
  const apiUrl = `${baseUrl}/agent/stream`;

  let upstreamResponse;
  try {
    upstreamResponse = await fetch(apiUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Tenant-Id": getFastApiTenantId(),
      },
      body: JSON.stringify({
        session_id: sid,
        input_type: "text",
        text: normalizedQuery,
        domain: "religious",
        language: "en-US",
        output_audio: false,
        use_knowledge: true,
        knowledge_top_k: 3,
      }),
    });
  } catch {
    return NextResponse.json(
      { response: "Upstream service is unreachable." },
      { status: 502 }
    );
  }

  if (!upstreamResponse.ok) {
    return NextResponse.json(
      {
        response: `Upstream error (${upstreamResponse.status}).`,
      },
      { status: 502 }
    );
  }

  // --- STREAM SSE ---
  let finalText = "";
  let tokenText = "";
  let doneOk = true;
  let failReason = "";
  const decoder = new TextDecoder();
  const parser = createParser((event) => {
    if (event.type === "event") {
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
          tokenText += typeof data === "string" ? data : String(data?.text || "");
        } catch {
          tokenText += event.data;
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
    }
  });

  if (!upstreamResponse.body) {
    return NextResponse.json({ response: "No response body from upstream." }, { status: 502 });
  }
  for await (const chunk of upstreamResponse.body) {
    parser.feed(decoder.decode(chunk));
  }
  parser.flush();

  if (!doneOk) {
    return NextResponse.json(
      { response: failReason || "AI service failed to complete the response." },
      { status: 502 }
    );
  }

  const responseText = String(finalText || tokenText || "").trim();

  return NextResponse.json({
    response: responseText || RELIGIOUS_FALLBACK,
  });
}
