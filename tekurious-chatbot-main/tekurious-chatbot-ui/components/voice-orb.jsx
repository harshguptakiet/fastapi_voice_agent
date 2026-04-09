'use client';

import { Mic, Square } from 'lucide-react';

/**
 * Minimal circular voice control (assistant-style): one surface, state via ring + motion.
 * `state`: idle | listening | processing | speaking
 */
export function VoiceOrb({
  state = 'idle',
  disabled = false,
  onClick,
  title,
}) {
  const listening = state === 'listening';
  const processing = state === 'processing';
  const speaking = state === 'speaking';

  const shapeClass =
    listening || (!processing && !speaking)
      ? 'rounded-full'
      : // Keep the mic button capsule-like while thinking/speaking.
        'rounded-2xl';

  const shell = [
    'relative flex h-12 w-12 shrink-0 items-center justify-center border transition-[transform,box-shadow] duration-200',
    shapeClass,
    listening
      ? 'border-red-500/40 bg-zinc-900 voice-orb-pulse scale-[1.05]'
      : processing
        ? 'border-blue-500/30 bg-zinc-900 scale-[1.03]'
        : speaking
          ? 'border-emerald-500/35 bg-zinc-900 voice-orb-glow scale-[1.08]'
          : 'border-zinc-200 bg-white shadow-sm scale-100',
    disabled
      ? 'cursor-not-allowed opacity-40'
      : 'cursor-pointer hover:border-zinc-300 active:scale-[0.98]',
  ].join(' ');

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title || (listening ? 'Stop and send' : 'Voice input')}
      className={shell}
    >
      {processing && (
        <span
          className="absolute inset-1 rounded-full border-2 border-transparent border-t-blue-400 border-r-blue-400/20 animate-spin"
          aria-hidden
        />
      )}
      {listening ? (
        <Square className="relative h-4 w-4 fill-white text-white" />
      ) : !processing ? (
        <Mic
          className={`relative h-5 w-5 ${speaking ? 'text-white' : 'text-zinc-600'}`}
        />
      ) : null}
      <span className="sr-only">
        {listening ? 'Stop recording' : processing ? 'Processing' : speaking ? 'Playing response' : 'Start voice'}
      </span>
    </button>
  );
}
