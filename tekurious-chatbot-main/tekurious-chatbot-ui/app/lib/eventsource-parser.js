// Duplicate of app/api/eventsource-parser.js — keep in sync (used if imported from lib).
// Parses SSE frames from chunked HTTP bodies. `pending` persists across feed() calls.
// Call flush() after the stream ends.

export function createParser(onParse) {
  let buffer = "";
  let pending = { event: "message", data: "" };

  function dispatch() {
    if (pending.data !== "") {
      onParse({ type: "event", event: pending.event, data: pending.data });
      pending = { event: "message", data: "" };
    }
  }

  function consumeLine(line) {
    if (line === "") {
      dispatch();
    } else if (line.startsWith("event:")) {
      pending.event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      if (pending.data) pending.data += "\n";
      pending.data += line.slice(5).trim();
    }
  }

  return {
    feed(chunk) {
      buffer += chunk;
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        consumeLine(line);
      }
    },
    flush() {
      if (buffer) {
        consumeLine(buffer);
        buffer = "";
      }
      dispatch();
    },
  };
}
