// app/api/Eduthum/route.js
import { NextResponse } from "next/server";

import { getFastApiBaseUrl, getFastApiTenantId } from "@/lib/fastapi-backend";

// Vercel serverless request bodies are capped (~4.5 MB on Hobby); avoid opaque 413s.
const MAX_FILE_SIZE =
  process.env.VERCEL === "1"
    ? 4 * 1024 * 1024
    : 10 * 1024 * 1024;

// 🔹 Helper: Upload a single file
async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  const baseUrl = getFastApiBaseUrl();
  const uploadUrl = `${baseUrl}/documents/upload?topic=education&language=en`;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);

  try {
    const res = await fetch(uploadUrl, {
      method: "POST",
      headers: {
        "X-Tenant-Id": getFastApiTenantId(),
      },
      body: formData,
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`Upload failed: ${res.status} - ${errorText}`);
    }

    return await res.json();
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("Upload timeout (file too large or server slow)");
    }
    throw err;
  }
}

export async function POST(request) {
  try {
    const formData = await request.formData();
    const query = formData.get("query");

    // Collect all files
    const files = [];
    let i = 0;
    while (formData.get(`file_${i}`)) {
      files.push(formData.get(`file_${i}`));
      i++;
    }

    if (files.length === 0) {
      return NextResponse.json({
        response: "Please upload at least one PDF file.",
      });
    }

    // 🔹 Validate + Upload files
    for (const file of files) {
      if (file.size === 0) {
        return NextResponse.json({ response: `File "${file.name}" is empty.` });
      }
      if (file.size > MAX_FILE_SIZE) {
        return NextResponse.json({
          response: `File "${file.name}" is too large. Max 10MB allowed.`,
        });
      }
      if (file.type !== "application/pdf") {
        return NextResponse.json({
          response: `File "${file.name}" must be a PDF. Got: ${file.type}`,
        });
      }
    }

    const results = await Promise.allSettled(
      files.map((file) => uploadFile(file))
    );

    const failed = results.filter(r => r.status === "rejected");
    if (failed.length > 0) {
      return NextResponse.json({
        response: `Some uploads failed:\n${failed
          .map((f, idx) => `${files[idx].name}: ${f.reason.message}`)
          .join("\n")}`,
      });
    }

    // 🔹 Success response
    const names = files.map(f => f.name).join(", ");
    let response = `✅ Successfully uploaded ${files.length} file(s): ${names}.\n\n`;
    response += query?.trim()
      ? `Your question: "${query}"\n\nNow use the chat API to query the uploaded documents.`
      : "Now you can ask me anything about the uploaded documents.";

    return NextResponse.json({ response });
  } catch (err) {
    console.error("Upload API error:", err);
    return NextResponse.json(
      { response: "❌ Error processing upload. Please try again." },
      { status: 500 }
    );
  }
}

export async function GET() {
  return NextResponse.json({
    message: "Eduthum Upload API - Use POST with FormData to upload PDFs",
  });
}
