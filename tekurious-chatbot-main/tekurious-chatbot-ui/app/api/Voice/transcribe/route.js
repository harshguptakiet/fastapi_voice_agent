import { NextResponse } from "next/server";
import { getFastApiBaseUrl, getFastApiTenantId } from "@/lib/fastapi-backend";

export async function POST(request) {
  let body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  if (!body?.audio?.audio_b64) {
    return NextResponse.json(
      { error: "audio.audio_b64 is required." },
      { status: 400 }
    );
  }

  const baseUrl = getFastApiBaseUrl();
  const apiUrl = `${baseUrl}/voice/transcribe`;

  try {
    const upstreamResponse = await fetch(apiUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Tenant-Id": getFastApiTenantId(),
      },
      body: JSON.stringify(body),
    });

    const data = await upstreamResponse.json().catch(() => ({}));

    if (!upstreamResponse.ok) {
      return NextResponse.json(
        {
          error:
            data.detail || data.error || `Voice transcribe failed (${upstreamResponse.status}).`,
        },
        { status: 502 }
      );
    }

    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { error: "Voice service is unreachable." },
      { status: 502 }
    );
  }
}
