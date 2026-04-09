// eventsource-parser.js
// Parses SSE frames from chunked HTTP bodies. `pending` persists across feed() calls
// (required — the previous implementation reset state every chunk and broke streaming).
// Call flush() after the stream ends so the last event is emitted without a trailing \n\n.

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
