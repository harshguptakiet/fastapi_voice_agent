"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getFastApiBaseUrl, getFastApiTenantId } from "@/lib/fastapi-backend";

const DEFAULT_LANGUAGE = "en-US";
const DEFAULT_STOP_WORDS = ["stop", "exit", "quit"];

function int16ToBase64(int16Array) {
  const bytes = new Uint8Array(int16Array.buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

function mergeInt16(chunks) {
  const total = chunks.reduce((sum, c) => sum + c.length, 0);
  const merged = new Int16Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

function toWsUrl(baseUrl, tenantId) {
  const raw = String(baseUrl || "").trim().replace(/\/+$/, "");
  const wsBase = raw.startsWith("https://")
    ? `wss://${raw.slice("https://".length)}`
    : raw.startsWith("http://")
      ? `ws://${raw.slice("http://".length)}`
      : raw;
  const url = new URL(`${wsBase}/agent/ws`);
  url.searchParams.set("tenant_id", tenantId);
  return url.toString();
}

function parseWsEvent(payload) {
  if (!payload) return { event: "", data: {} };
  if (typeof payload === "string") {
    try {
      const parsed = JSON.parse(payload);
      return {
        event: String(parsed?.event || ""),
        data: parsed?.data ?? {},
      };
    } catch {
      return { event: "", data: {} };
    }
  }
  return {
    event: String(payload?.event || ""),
    data: payload?.data ?? {},
  };
}

function hasStopCommand(text, stopWords) {
  const normalized = String(text || "").trim().toLowerCase();
  if (!normalized) return false;
  return stopWords.some((word) => new RegExp(`\\b${word}\\b`, "i").test(normalized));
}

export function useRealtimeVoiceAgent({
  domain,
  getSessionId,
  language = DEFAULT_LANGUAGE,
  idleTimeoutMs = 45000,
  stopWords = DEFAULT_STOP_WORDS,
  onTranscript,
  onAssistantText,
  onError,
  onStateChange,
}) {
  const [isEnabled, setIsEnabled] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const wsRef = useRef(null);
  const streamRef = useRef(null);
  const audioContextRef = useRef(null);
  const sourceRef = useRef(null);
  const processorRef = useRef(null);
  const playbackQueueRef = useRef([]);
  const isPlayingRef = useRef(false);
  const waitingForTurnRef = useRef(false);
  const turnActiveRef = useRef(false);
  const speechStartedRef = useRef(false);
  const speechStartMsRef = useRef(0);
  const lastSpeechMsRef = useRef(0);
  const lastInteractionMsRef = useRef(Date.now());
  const finalizedOnceRef = useRef(false);
  const runningRef = useRef(false);
  const sampleRateRef = useRef(16000);
  const idleTimerRef = useRef(null);
  const noiseFloorRef = useRef(0.0025);
  const fallbackModeRef = useRef(false);
  const turnChunksRef = useRef([]);
  const preRollChunksRef = useRef([]);
  const isFinalizingRef = useRef(false);

  const stopWordList = useMemo(
    () => (Array.isArray(stopWords) && stopWords.length ? stopWords : DEFAULT_STOP_WORDS),
    [stopWords]
  );

  const setUiState = useCallback(
    (state) => {
      if (state === "listening") {
        setIsListening(true);
        setIsProcessing(false);
        setIsSpeaking(false);
      } else if (state === "processing") {
        setIsListening(false);
        setIsProcessing(true);
        setIsSpeaking(false);
      } else if (state === "speaking") {
        setIsListening(false);
        setIsProcessing(false);
        setIsSpeaking(true);
      } else {
        setIsListening(false);
        setIsProcessing(false);
        setIsSpeaking(false);
      }
      onStateChange?.(state);
    },
    [onStateChange]
  );

  const emitError = useCallback(
    (message) => {
      const msg = String(message || "Voice agent failed.");
      onError?.(msg);
    },
    [onError]
  );

  const playNextAudioChunk = useCallback(async () => {
    if (isPlayingRef.current) return;
    if (!playbackQueueRef.current.length) {
      if (finalizedOnceRef.current && runningRef.current) {
        finalizedOnceRef.current = false;
        setUiState("listening");
      }
      return;
    }

    const chunk = playbackQueueRef.current.shift();
    if (!chunk?.audio_b64) return;
    isPlayingRef.current = true;
    setUiState("speaking");
    lastInteractionMsRef.current = Date.now();

    try {
      const audio = new Audio(
        `data:${chunk.mime_type || "audio/mpeg"};base64,${String(chunk.audio_b64)}`
      );
      await new Promise((resolve, reject) => {
        audio.onended = resolve;
        audio.onerror = () => reject(new Error("Audio playback failed."));
        audio.play().catch(reject);
      });
    } catch (err) {
      emitError(err?.message || "Audio playback failed.");
    } finally {
      isPlayingRef.current = false;
      if (playbackQueueRef.current.length) {
        playNextAudioChunk();
      } else if (finalizedOnceRef.current && runningRef.current) {
        finalizedOnceRef.current = false;
        setUiState("listening");
      }
    }
  }, [emitError, setUiState]);

  const stopAll = useCallback(
    async (reason) => {
      runningRef.current = false;
      waitingForTurnRef.current = false;
      turnActiveRef.current = false;
      speechStartedRef.current = false;
      finalizedOnceRef.current = false;
      playbackQueueRef.current = [];
      turnChunksRef.current = [];
      preRollChunksRef.current = [];
      isFinalizingRef.current = false;
      fallbackModeRef.current = false;

      if (idleTimerRef.current) {
        clearInterval(idleTimerRef.current);
        idleTimerRef.current = null;
      }

      if (processorRef.current) {
        processorRef.current.disconnect();
        processorRef.current.onaudioprocess = null;
        processorRef.current = null;
      }
      if (sourceRef.current) {
        sourceRef.current.disconnect();
        sourceRef.current = null;
      }
      if (audioContextRef.current) {
        try {
          await audioContextRef.current.close();
        } catch {
          // best effort
        }
        audioContextRef.current = null;
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }

      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        try {
          wsRef.current.send(JSON.stringify({ type: "stop" }));
        } catch {
          // best effort
        }
      }
      if (wsRef.current) {
        try {
          wsRef.current.close(1000, "client-stop");
        } catch {
          // best effort
        }
        wsRef.current = null;
      }

      setIsEnabled(false);
      setUiState("idle");
      if (reason) emitError(reason);
    },
    [emitError, setUiState]
  );

  const finalizeTurn = useCallback(() => {
    if (!runningRef.current || isFinalizingRef.current) return;
    if (!turnActiveRef.current || waitingForTurnRef.current) return;

    isFinalizingRef.current = true;
    waitingForTurnRef.current = true;
    turnActiveRef.current = false;
    speechStartedRef.current = false;
    finalizedOnceRef.current = true;
    setUiState("processing");
    lastInteractionMsRef.current = Date.now();

    if (fallbackModeRef.current) {
      const merged = mergeInt16(turnChunksRef.current);
      turnChunksRef.current = [];
      if (!merged.length) {
        emitError("No speech detected. Please speak closer to the mic and try again.");
        waitingForTurnRef.current = false;
        isFinalizingRef.current = false;
        finalizedOnceRef.current = false;
        setUiState("listening");
        return;
      }

      fetch("/api/Voice/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: getSessionId?.() || `voice-${Date.now()}`,
          audio_b64: int16ToBase64(merged),
          sample_rate_hz: sampleRateRef.current,
          domain,
          language,
        }),
      })
        .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
        .then(({ ok, data }) => {
          if (!ok) {
            throw new Error(String(data?.error || data?.detail || "Voice turn failed."));
          }
          const transcript = String(data?.transcript || "").trim();
          const finalText = String(data?.final_text || "").trim();
          if (transcript) {
            onTranscript?.(transcript);
            lastInteractionMsRef.current = Date.now();
            if (hasStopCommand(transcript, stopWordList)) {
              stopAll("Voice session stopped.");
              return;
            }
          }
          if (finalText) onAssistantText?.(finalText);
          const chunks = Array.isArray(data?.audio_chunks) ? data.audio_chunks : [];
          chunks.sort((a, b) => Number(a?.index ?? 0) - Number(b?.index ?? 0));
          if (!transcript && !finalText && chunks.length === 0) {
            throw new Error("Voice turn completed with no transcript or response.");
          }
          for (const chunk of chunks) playbackQueueRef.current.push(chunk);
          playNextAudioChunk();
        })
        .catch((err) => {
          emitError(err?.message || "Voice turn failed.");
          finalizedOnceRef.current = false;
          setUiState("listening");
        })
        .finally(() => {
          waitingForTurnRef.current = false;
          isFinalizingRef.current = false;
          if (!isPlayingRef.current && playbackQueueRef.current.length === 0 && runningRef.current) {
            finalizedOnceRef.current = false;
            setUiState("listening");
          }
        });
      return;
    }

    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      waitingForTurnRef.current = false;
      isFinalizingRef.current = false;
      return;
    }
    wsRef.current.send(JSON.stringify({ type: "finalize" }));
  }, [
    domain,
    emitError,
    getSessionId,
    language,
    onAssistantText,
    onTranscript,
    playNextAudioChunk,
    setUiState,
    stopAll,
    stopWordList,
  ]);

  const start = useCallback(async () => {
    if (runningRef.current) return;
    runningRef.current = true;
    setIsEnabled(true);
    setUiState("listening");
    lastInteractionMsRef.current = Date.now();

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(1024, 1, 1);
      sampleRateRef.current = audioContext.sampleRate;

      streamRef.current = stream;
      audioContextRef.current = audioContext;
      sourceRef.current = source;
      processorRef.current = processor;

      const wsUrl = toWsUrl(getFastApiBaseUrl(), getFastApiTenantId());
      const mixedContentBlocked =
        typeof window !== "undefined" &&
        window.location.protocol === "https:" &&
        wsUrl.startsWith("ws://");

      fallbackModeRef.current = mixedContentBlocked;

      if (!mixedContentBlocked) {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
        if (!runningRef.current) return;
        ws.send(
          JSON.stringify({
            type: "start",
            session_id: getSessionId?.() || `voice-${Date.now()}`,
            sample_rate_hz: sampleRateRef.current,
            language,
            domain,
            output_audio: true,
            use_knowledge: true,
            knowledge_top_k: 3,
          })
        );
        };

        ws.onmessage = (evt) => {
        const { event, data } = parseWsEvent(evt.data);
        if (!event) return;

        if (event === "input") {
          const transcript = String(data?.transcript || "").trim();
          if (transcript) {
            onTranscript?.(transcript);
            lastInteractionMsRef.current = Date.now();
            if (hasStopCommand(transcript, stopWordList)) {
              stopAll("Voice session stopped.");
            }
          }
          return;
        }

        if (event === "final_text") {
          const text =
            typeof data === "string"
              ? data
              : String(data?.text || data?.final_text || "").trim();
          if (text) onAssistantText?.(text);
          return;
        }

        if (event === "audio") {
          playbackQueueRef.current.push(data || {});
          playNextAudioChunk();
          return;
        }

        if (event === "done") {
          waitingForTurnRef.current = false;
          isFinalizingRef.current = false;
          if (!isPlayingRef.current && playbackQueueRef.current.length === 0 && runningRef.current) {
            finalizedOnceRef.current = false;
            setUiState("listening");
          }
          return;
        }

        if (event === "error") {
          emitError(String(data?.reason || "Voice agent error."));
        }
        };

        ws.onerror = () => {
          fallbackModeRef.current = true;
          try {
            ws.close();
          } catch {
            // no-op
          }
        };
        ws.onclose = () => {
          wsRef.current = null;
          if (runningRef.current && !fallbackModeRef.current) {
            emitError("Voice connection closed.");
            stopAll();
          }
        };
      }

      const minSpeechMs = 140;
      const trailingSilenceMs = 800;
      const preRollChunkCount = 8; // ~500ms at 1024 frames / 16kHz
      const maxTurnMs = 9000;
      const minThreshold = 0.0028;
      const maxThreshold = 0.02;

      processor.onaudioprocess = (event) => {
        if (!runningRef.current || waitingForTurnRef.current || isPlayingRef.current) return;

        const input = event.inputBuffer.getChannelData(0);
        const int16Chunk = new Int16Array(input.length);
        let sumSquares = 0;
        for (let i = 0; i < input.length; i++) {
          const sample = Math.max(-1, Math.min(1, input[i]));
          sumSquares += sample * sample;
          int16Chunk[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
        }

        const rms = Math.sqrt(sumSquares / input.length);
        const now = Date.now();
        const floor = noiseFloorRef.current;
        // Only adapt floor downward/upward when chunk is likely non-speech.
        noiseFloorRef.current = floor * 0.995 + rms * 0.005;
        const adaptiveThreshold = Math.max(
          minThreshold,
          Math.min(maxThreshold, noiseFloorRef.current * 2.5)
        );
        const isSpeech = rms >= adaptiveThreshold * 0.65;

        const chunkCopy = new Int16Array(int16Chunk);
        preRollChunksRef.current.push(chunkCopy);
        if (preRollChunksRef.current.length > preRollChunkCount) {
          preRollChunksRef.current.shift();
        }

        if (isSpeech) {
          if (!speechStartedRef.current) {
            speechStartedRef.current = true;
            speechStartMsRef.current = now;
          }
          lastSpeechMsRef.current = now;
          lastInteractionMsRef.current = now;

          if (!turnActiveRef.current) {
            turnActiveRef.current = true;
            turnChunksRef.current = [...preRollChunksRef.current];
          }

          if (fallbackModeRef.current) {
            turnChunksRef.current.push(chunkCopy);
          } else if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(
              JSON.stringify({
                type: "audio_chunk",
                audio_b64: int16ToBase64(int16Chunk),
              })
            );
          }
          return;
        }

        if (!speechStartedRef.current || !turnActiveRef.current) return;
        if (fallbackModeRef.current) {
          // Keep brief trailing silence for better endpointing/transcription quality.
          turnChunksRef.current.push(chunkCopy);
        }
        const speechDuration = now - speechStartMsRef.current;
        const silenceMs = now - lastSpeechMsRef.current;

        if (speechDuration >= maxTurnMs) {
          finalizeTurn();
          return;
        }

        if (speechDuration >= minSpeechMs && silenceMs >= trailingSilenceMs) {
          finalizeTurn();
        }
      };

      source.connect(processor);
      processor.connect(audioContext.destination);
      await audioContext.resume();

      idleTimerRef.current = setInterval(() => {
        if (!runningRef.current) return;
        const idleFor = Date.now() - lastInteractionMsRef.current;
        if (idleFor >= idleTimeoutMs) {
          stopAll("Voice session timed out.");
        }
      }, 5000);
    } catch (err) {
      await stopAll();
      emitError(err?.message || "Microphone access denied.");
    }
  }, [
    domain,
    emitError,
    finalizeTurn,
    getSessionId,
    idleTimeoutMs,
    language,
    onAssistantText,
    onTranscript,
    playNextAudioChunk,
    setUiState,
    stopAll,
    stopWordList,
  ]);

  const stop = useCallback(async () => {
    await stopAll();
  }, [stopAll]);

  const toggle = useCallback(async () => {
    if (runningRef.current) {
      await stop();
    } else {
      await start();
    }
  }, [start, stop]);

  useEffect(() => {
    return () => {
      stopAll();
    };
  }, [stopAll]);

  return {
    isEnabled,
    isListening,
    isProcessing,
    isSpeaking,
    supported:
      typeof window !== "undefined" &&
      !!navigator.mediaDevices &&
      !!navigator.mediaDevices.getUserMedia,
    start,
    stop,
    toggle,
  };
}
