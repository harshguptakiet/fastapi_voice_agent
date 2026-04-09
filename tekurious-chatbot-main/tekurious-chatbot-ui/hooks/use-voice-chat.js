"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const DEFAULT_LANGUAGE = "en-US";

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
  const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const merged = new Int16Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

export function useVoiceChat({ onTranscript, onAudioCaptured, onError, language = DEFAULT_LANGUAGE, manualMode = false }) {
  const [isListening, setIsListening] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const mediaStreamRef = useRef(null);
  const audioContextRef = useRef(null);
  const processorRef = useRef(null);
  const sourceRef = useRef(null);

  const utteranceChunksRef = useRef([]);
  const speechStartRef = useRef(0);
  const lastSpeechRef = useRef(0);
  const speechStartedRef = useRef(false);
  const isFinalizingRef = useRef(false);
  const isListeningRef = useRef(false);
  const stopListeningRef = useRef(null);

  const sampleRateRef = useRef(16000);

  const minSpeechMs = 350;
  const trailingSilenceMs = 900;
  const energyThreshold = 0.012;

  const reportError = useCallback(
    (msg) => {
      if (onError) onError(msg);
    },
    [onError]
  );

  const transcribeUtterance = useCallback(
    async (int16Audio, sampleRateHz) => {
      const audio_b64 = int16ToBase64(int16Audio);
      const payload = {
        audio: {
          audio_b64,
          sample_rate_hz: sampleRateHz,
        },
        language,
      };

      const res = await fetch("/api/Voice/transcribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.error || "Voice transcription failed.");
      }

      return (data.text || "").trim();
    },
    [language]
  );

  const finalizeUtterance = useCallback(async () => {
    if (isFinalizingRef.current) return;
    if (!manualMode && !speechStartedRef.current) return;
    if (manualMode && utteranceChunksRef.current.length === 0) return;

    const now = Date.now();
    const speechDurationMs = now - speechStartRef.current;
    if (!manualMode && speechDurationMs < minSpeechMs) {
      utteranceChunksRef.current = [];
      speechStartedRef.current = false;
      return;
    }

    isFinalizingRef.current = true;
    setIsTranscribing(true);

    try {
      const merged = mergeInt16(utteranceChunksRef.current);
      utteranceChunksRef.current = [];
      speechStartedRef.current = false;

      if (!merged.length) return;

      if (onAudioCaptured) {
        await onAudioCaptured({
          audio_b64: int16ToBase64(merged),
          sample_rate_hz: sampleRateRef.current,
        });
        return;
      }

      const text = await transcribeUtterance(merged, sampleRateRef.current);
      if (text && onTranscript) {
        await onTranscript(text);
      }
    } catch (err) {
      reportError(err?.message || "Failed to process voice input.");
    } finally {
      setIsTranscribing(false);
      isFinalizingRef.current = false;
    }
  }, [manualMode, onAudioCaptured, onTranscript, reportError, transcribeUtterance]);

  const startListening = useCallback(async () => {
    if (isListeningRef.current) return;

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
      const processor = audioContext.createScriptProcessor(4096, 1, 1);

      sampleRateRef.current = audioContext.sampleRate;
      mediaStreamRef.current = stream;
      audioContextRef.current = audioContext;
      sourceRef.current = source;
      processorRef.current = processor;

      utteranceChunksRef.current = [];
      speechStartRef.current = 0;
      lastSpeechRef.current = 0;
      speechStartedRef.current = false;

      processor.onaudioprocess = async (event) => {
        if (!isListeningRef.current || isFinalizingRef.current) return;

        const input = event.inputBuffer.getChannelData(0);
        let sumSquares = 0;
        const int16Chunk = new Int16Array(input.length);

        for (let i = 0; i < input.length; i++) {
          const sample = Math.max(-1, Math.min(1, input[i]));
          sumSquares += sample * sample;
          int16Chunk[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
        }

        const now = Date.now();

        if (manualMode) {
          if (!speechStartedRef.current) {
            speechStartedRef.current = true;
            speechStartRef.current = now;
            utteranceChunksRef.current = [];
          }
          utteranceChunksRef.current.push(int16Chunk);
          lastSpeechRef.current = now;
          return;
        }

        const rms = Math.sqrt(sumSquares / input.length);

        if (rms >= energyThreshold) {
          if (!speechStartedRef.current) {
            speechStartedRef.current = true;
            speechStartRef.current = now;
            utteranceChunksRef.current = [];
          }
          lastSpeechRef.current = now;
        }

        if (speechStartedRef.current) {
          utteranceChunksRef.current.push(int16Chunk);

          const silenceMs = now - lastSpeechRef.current;
          if (!manualMode && lastSpeechRef.current && silenceMs >= trailingSilenceMs) {
            await finalizeUtterance();
          }
        }
      };

      source.connect(processor);
      processor.connect(audioContext.destination);
      await audioContext.resume();

      isListeningRef.current = true;
      setIsListening(true);
    } catch (err) {
      reportError(err?.message || "Microphone access denied.");
    }
  }, [finalizeUtterance, manualMode, reportError]);

  const stopListening = useCallback(async (options = {}) => {
    const finalize = options?.finalize !== false;
    if (!isListeningRef.current) return;

    isListeningRef.current = false;
    setIsListening(false);

    try {
      if (finalize && speechStartedRef.current && utteranceChunksRef.current.length) {
        await finalizeUtterance();
      }
    } catch {
      // No-op: best effort finalize
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
      await audioContextRef.current.close();
      audioContextRef.current = null;
    }

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }

    utteranceChunksRef.current = [];
    speechStartedRef.current = false;
  }, [finalizeUtterance]);

  useEffect(() => {
    stopListeningRef.current = stopListening;
  }, [stopListening]);

  const toggleListening = useCallback(async () => {
    if (isListeningRef.current) {
      await stopListening();
    } else {
      await startListening();
    }
  }, [startListening, stopListening]);

  const speakText = useCallback(
    async (text) => {
      const content = (text || "").trim();
      if (!content) return;

      setIsSpeaking(true);
      try {
        const res = await fetch("/api/Voice/synthesize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: content, language }),
        });

        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(data.error || "Voice synthesis failed.");
        }

        if (!data.audio_b64) return;

        const mimeType = data.mime_type || "audio/wav";
        const audio = new Audio(`data:${mimeType};base64,${data.audio_b64}`);

        await new Promise((resolve, reject) => {
          audio.onended = resolve;
          audio.onerror = () => reject(new Error("Audio playback failed."));
          audio.play().catch(reject);
        });
      } catch (err) {
        reportError(err?.message || "Failed to play voice response.");
      } finally {
        setIsSpeaking(false);
      }
    },
    [language, reportError]
  );

  useEffect(() => {
    return () => {
      if (stopListeningRef.current) {
        stopListeningRef.current();
      }
    };
  }, []);

  return {
    isListening,
    isTranscribing,
    isSpeaking,
    startListening,
    stopListening,
    toggleListening,
    speakText,
    supported:
      typeof window !== "undefined" &&
      !!navigator.mediaDevices &&
      !!navigator.mediaDevices.getUserMedia,
  };
}
