const state = {
  chunks: [],
  mediaRecorder: null,
  stream: null,
  chatEl: null,
  logEl: null,
  audioPlayer: null,
  currentAssistantBubble: null,
  micBtn: null,
  metricsEl: null,
  audioQueue: [],
  isAudioPlaying: false,
};

const STATUS_CLASS_NAMES = ['status-ok', 'status-bad', 'status-warn', 'status-unknown'];

function byId(id) {
  return document.getElementById(id);
}

function now() {
  return new Date().toLocaleTimeString();
}

function appendLog(message) {
  if (!state.logEl) return;
  const line = `[${now()}] ${message}`;
  state.logEl.textContent += `${line}\n`;
  state.logEl.scrollTop = state.logEl.scrollHeight;
}

function setStatusChip(id, label, tone) {
  const el = byId(id);
  if (!el) return;
  el.textContent = label;
  STATUS_CLASS_NAMES.forEach((name) => el.classList.remove(name));
  el.classList.add(tone);
}

function createMessage(role, text) {
  const el = document.createElement('div');
  el.className = `msg ${role}`;
  el.textContent = text;
  state.chatEl.appendChild(el);
  state.chatEl.scrollTop = state.chatEl.scrollHeight;
  return el;
}

function setVoiceStatus(title, detail) {
  const strong = byId('voiceState');
  const small = byId('voiceDetail');
  if (strong) strong.textContent = title;
  if (small) small.textContent = detail;
}

function updateMetrics(metrics) {
  const keys = ['retrieval_ms', 'first_token_ms', 'llm_total_ms', 'total_ms', 'token_count', 'document_count'];
  const pills = [];
  keys.forEach((key) => {
    if (metrics[key] !== undefined && metrics[key] !== null) {
      pills.push(`<span class="metric-pill">${key}: ${metrics[key]}</span>`);
    }
  });
  state.metricsEl.innerHTML = pills.length
    ? pills.join('')
    : '<span class="metric-pill">metrics: pending</span>';
}

function readConfig() {
  return {
    baseUrl: byId('baseUrl').value.trim().replace(/\/$/, ''),
    tenantId: byId('tenantId').value.trim() || 'tenant-demo',
    domain: byId('agentDomain').value,
    sessionId: byId('sessionId').value.trim() || 'chat-session',
    mode: byId('mode').value,
    language: byId('language').value,
    provider: byId('provider').value || undefined,
    model: byId('llmModel').value.trim() || undefined,
    ttsVoice: byId('ttsVoice').value || null,
    ttsFormat: byId('ttsFormat').value || null,
    ttsEmotion: byId('ttsEmotion').value || null,
    useKnowledge: byId('useKnowledge').checked,
    accessLevel: byId('accessLevel').value || null,
    topK: Number(byId('knowledgeTopK').value || 3),
    outputAudio: byId('outputAudio').checked,
  };
}

function resolveFrontendBaseUrl() {
  if (window.location && /^https?:$/i.test(window.location.protocol)) {
    const host = (window.location.hostname || '').toLowerCase();
    const port = String(window.location.port || '');
    const isLocalHost = host === '127.0.0.1' || host === 'localhost';
    const isBackendPort = port === '8010' || port === '8000';
    if (isLocalHost && isBackendPort) {
      return window.location.origin.replace(/\/$/, '');
    }
  }
  return 'http://127.0.0.1:8010';
}

function payloadForText(config, text) {
  const payload = {
    session_id: config.sessionId,
    input_type: 'text',
    text,
    language: config.language,
    use_knowledge: config.useKnowledge,
    knowledge_top_k: config.topK,
    output_audio: config.outputAudio,
    domain: config.domain,
  };
  if (config.provider) payload.provider = config.provider;
  if (config.model) payload.llm_model = config.model;
  if (config.accessLevel) payload.access_level = config.accessLevel;
  if (config.ttsVoice) payload.tts_voice = config.ttsVoice;
  if (config.ttsFormat) payload.tts_format = config.ttsFormat;
  if (config.ttsEmotion) payload.tts_emotion = config.ttsEmotion;
  return payload;
}

function payloadForAudio(config, audioB64, sampleRateHz) {
  const payload = {
    session_id: config.sessionId,
    input_type: 'audio',
    one_shot_http_audio: true,
    audio: {
      audio_b64: audioB64,
      sample_rate_hz: sampleRateHz,
      transport: 'http',
    },
    language: config.language,
    use_knowledge: config.useKnowledge,
    knowledge_top_k: config.topK,
    output_audio: config.outputAudio,
    domain: config.domain,
  };
  if (config.provider) payload.provider = config.provider;
  if (config.model) payload.llm_model = config.model;
  if (config.accessLevel) payload.access_level = config.accessLevel;
  if (config.ttsVoice) payload.tts_voice = config.ttsVoice;
  if (config.ttsFormat) payload.tts_format = config.ttsFormat;
  if (config.ttsEmotion) payload.tts_emotion = config.ttsEmotion;
  return payload;
}

async function streamAgent(config, payload) {
  setStatusChip('statusStream', 'Running', 'status-warn');
  state.currentAssistantBubble = createMessage('assistant', '...');
  updateMetrics({});

  const endpoint = `${config.baseUrl}/agent/stream`;
  const headers = { 'Content-Type': 'application/json' };
  if (config.tenantId) {
    headers['X-Tenant-Id'] = config.tenantId;
  }

  appendLog(`POST ${endpoint}`);

  const response = await fetch(endpoint, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    setStatusChip('statusStream', 'Failed', 'status-bad');
    const bodyText = await response.text().catch(() => '');
    throw new Error(`stream failed (${response.status}) ${bodyText}`.trim());
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';
    parts.forEach((chunk) => handleSSEChunk(chunk));
  }

  appendLog('stream closed');
  setStatusChip('statusStream', 'Working', 'status-ok');
}

function handleSSEChunk(chunk) {
  const lines = chunk.split('\n');
  let eventName = 'message';
  let data = '';

  lines.forEach((line) => {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim();
    }
    if (line.startsWith('data:')) {
      data += line.slice(5).trim();
    }
  });

  if (!data) return;

  let parsed;
  try {
    parsed = JSON.parse(data);
  } catch {
    parsed = data;
  }

  applyEvent(eventName, parsed);
}

function applyEvent(eventName, payload) {
  if (eventName === 'input') {
    appendLog(`input: ${JSON.stringify(payload)}`);
    return;
  }

  if (eventName === 'status' || eventName === 'message') {
    const msg = (typeof payload === 'string') ? payload : (payload.message || JSON.stringify(payload));
    appendLog(`status: ${msg}`);
    return;
  }

  if (eventName === 'text') {
    const text = (typeof payload === 'string') ? payload : (payload.text || '');
    state.currentAssistantBubble.textContent = (state.currentAssistantBubble.textContent === '...')
      ? text
      : `${state.currentAssistantBubble.textContent}${text}`;
    state.chatEl.scrollTop = state.chatEl.scrollHeight;
    return;
  }

  if (eventName === 'final_text') {
    const text = (typeof payload === 'string') ? payload : (payload.text || '');
    if (text) state.currentAssistantBubble.textContent = text;
    appendLog('assistant final text received');
    return;
  }

  if (eventName === 'metrics') {
    const metrics = (typeof payload === 'object' && payload !== null) ? payload : {};
    updateMetrics(metrics);
    appendLog('metrics updated');
    return;
  }

  if (eventName === 'audio') {
    if (typeof payload === 'object' && payload !== null) {
      const audioB64 = payload.audio_b64;
      if (audioB64) {
        const mime = payload.mime_type || inferMimeFromFormat(byId('ttsFormat').value);
        enqueueAudioChunk(audioB64, mime);
        appendLog(`audio chunk queued (${state.audioQueue.length} waiting)`);
      }
    }
    return;
  }

  if (eventName === 'done') {
    appendLog(`done: ${typeof payload === 'string' ? payload : JSON.stringify(payload)}`);
    setStatusChip('statusStream', 'Idle', 'status-unknown');
    return;
  }

  appendLog(`${eventName}: ${typeof payload === 'string' ? payload : JSON.stringify(payload)}`);
}

function inferMimeFromFormat(format) {
  const value = (format || '').toLowerCase();
  if (value.includes('mp3')) return 'audio/mpeg';
  if (value.includes('pcm')) return 'audio/wav';
  return 'audio/mpeg';
}

function enqueueAudioChunk(audioB64, mime) {
  if (!audioB64) return;
  state.audioQueue.push({ audioB64, mime });
  if (!state.isAudioPlaying) playNextAudioChunk();
}

function playNextAudioChunk() {
  if (state.isAudioPlaying) return;
  const next = state.audioQueue.shift();
  if (!next) {
    setStatusChip('statusAudio', 'Idle', 'status-unknown');
    return;
  }

  state.audioPlayer.src = `data:${next.mime};base64,${next.audioB64}`;
  state.audioPlayer.play().then(() => {
    state.isAudioPlaying = true;
    setStatusChip('statusAudio', 'Working', 'status-ok');
  }).catch(() => {
    // Keep this chunk loaded in the player and continue after user-initiated play.
    setStatusChip('statusAudio', 'Blocked', 'status-warn');
    appendLog('audio autoplay blocked; press play manually');
  });
}

async function handleSendText() {
  const config = readConfig();
  const prompt = byId('messageInput').value.trim();
  if (!prompt) return;

  if (!config.sessionId) {
    createMessage('system', 'Session ID is required.');
    return;
  }

  createMessage('user', prompt);
  byId('messageInput').value = '';

  const payload = payloadForText(config, prompt);
  try {
    await streamAgent(config, payload);
  } catch (error) {
    setStatusChip('statusStream', 'Failed', 'status-bad');
    createMessage('system', `Request failed: ${error.message}`);
    appendLog(`request failed: ${error.message}`);
  }
}

async function decodeBlobToAudioBuffer(blob) {
  const arrayBuffer = await blob.arrayBuffer();
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) throw new Error('AudioContext is not supported in this browser');

  const context = new Ctx();
  try {
    return await context.decodeAudioData(arrayBuffer.slice(0));
  } finally {
    await context.close();
  }
}

async function resampleToMono(audioBuffer, targetSampleRate) {
  const targetLength = Math.ceil(audioBuffer.duration * targetSampleRate);
  const offline = new OfflineAudioContext(1, targetLength, targetSampleRate);
  const source = offline.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(offline.destination);
  source.start(0);
  const rendered = await offline.startRendering();
  return rendered.getChannelData(0);
}

function float32ToPcm16Base64(float32Array) {
  const buffer = new ArrayBuffer(float32Array.length * 2);
  const view = new DataView(buffer);
  let offset = 0;

  for (let i = 0; i < float32Array.length; i += 1) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }

  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

async function blobToPcm16Payload(blob, targetSampleRate = 16000) {
  const audioBuffer = await decodeBlobToAudioBuffer(blob);
  const mono = await resampleToMono(audioBuffer, targetSampleRate);
  return {
    audioB64: float32ToPcm16Base64(mono),
    sampleRateHz: targetSampleRate,
  };
}

async function startRecording() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    createMessage('system', 'Microphone API not available in this browser.');
    return;
  }

  state.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  state.chunks = [];

  let options = undefined;
  if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
    options = { mimeType: 'audio/webm;codecs=opus' };
  } else if (MediaRecorder.isTypeSupported('audio/webm')) {
    options = { mimeType: 'audio/webm' };
  }

  state.mediaRecorder = options ? new MediaRecorder(state.stream, options) : new MediaRecorder(state.stream);

  state.mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) state.chunks.push(event.data);
  };

  state.mediaRecorder.start();
  state.micBtn.classList.add('recording');
  setStatusChip('statusMic', 'Working', 'status-ok');
  setVoiceStatus('Listening...', 'Tap again to send voice prompt');
  appendLog('recording started');
}

async function stopRecordingAndSend() {
  if (!state.mediaRecorder) return;

  const blob = await new Promise((resolve) => {
    state.mediaRecorder.onstop = () => {
      const output = new Blob(state.chunks, { type: state.mediaRecorder.mimeType || 'audio/webm' });
      resolve(output);
    };
    state.mediaRecorder.stop();
  });

  state.stream.getTracks().forEach((track) => track.stop());
  state.stream = null;
  state.mediaRecorder = null;
  state.micBtn.classList.remove('recording');
  setStatusChip('statusMic', 'Idle', 'status-unknown');
  setVoiceStatus('Processing voice...', 'Converting to PCM16 and calling /agent/stream');
  appendLog('recording stopped; converting audio');

  const config = readConfig();
  if (!config.sessionId) {
    createMessage('system', 'Session ID is required.');
    setVoiceStatus('Ready', 'Tap round button to talk');
    return;
  }

  try {
    const pcm = await blobToPcm16Payload(blob, 16000);
    const payload = payloadForAudio(config, pcm.audioB64, pcm.sampleRateHz);
    createMessage('user', '[voice message]');

    await streamAgent(config, payload);
    setVoiceStatus('Ready', 'Tap round button to talk');
  } catch (error) {
    setStatusChip('statusStream', 'Failed', 'status-bad');
    createMessage('system', `Voice request failed: ${error.message}`);
    appendLog(`voice request failed: ${error.message}`);
    setVoiceStatus('Error', 'See log for details');
  }
}

async function toggleMic() {
  const active = !!state.mediaRecorder && state.mediaRecorder.state === 'recording';
  if (active) {
    await stopRecordingAndSend();
  } else {
    try {
      await startRecording();
    } catch (error) {
      setStatusChip('statusMic', 'Failed', 'status-bad');
      createMessage('system', `Mic error: ${error.message}`);
      appendLog(`mic error: ${error.message}`);
      setVoiceStatus('Mic unavailable', 'Permission or device issue');
    }
  }
}

async function checkHealth() {
  const baseUrl = byId('baseUrl').value.trim().replace(/\/$/, '');
  const target = `${baseUrl}/health`;
  appendLog(`GET ${target}`);
  try {
    const response = await fetch(target);
    const json = await response.json();
    byId('healthBadge').textContent = response.ok ? 'status: healthy' : 'status: degraded';
    setStatusChip('statusHealth', response.ok ? 'Working' : 'Not Working', response.ok ? 'status-ok' : 'status-bad');
    createMessage('system', `Health: ${JSON.stringify(json)}`);
  } catch (error) {
    byId('healthBadge').textContent = 'status: offline';
    setStatusChip('statusHealth', 'Not Working', 'status-bad');
    createMessage('system', `Health check failed: ${error.message}`);
  }
}

function init() {
  state.chatEl = byId('chat');
  state.logEl = byId('eventLog');
  state.audioPlayer = byId('audioPlayer');
  state.micBtn = byId('micButton');
  state.metricsEl = byId('metrics');

  state.audioPlayer.addEventListener('play', () => {
    state.isAudioPlaying = true;
  });

  state.audioPlayer.addEventListener('ended', () => {
    state.isAudioPlaying = false;
    playNextAudioChunk();
  });

  state.audioPlayer.addEventListener('error', () => {
    state.isAudioPlaying = false;
    appendLog('audio playback error; skipping chunk');
    playNextAudioChunk();
  });

  const baseUrlInput = byId('baseUrl');
  if (baseUrlInput) {
    const lockedBaseUrl = resolveFrontendBaseUrl();
    baseUrlInput.value = lockedBaseUrl;
    baseUrlInput.readOnly = true;
    baseUrlInput.title = 'Auto-locked to current frontend origin';
    appendLog(`base URL locked: ${lockedBaseUrl}`);
  }

  byId('btnSend').addEventListener('click', handleSendText);
  byId('messageInput').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      handleSendText();
    }
  });
  byId('micButton').addEventListener('click', toggleMic);
  byId('btnHealth').addEventListener('click', checkHealth);

  setStatusChip('statusHealth', 'Unknown', 'status-unknown');
  setStatusChip('statusStream', 'Idle', 'status-unknown');
  setStatusChip('statusMic', 'Idle', 'status-unknown');
  setStatusChip('statusAudio', 'Idle', 'status-unknown');

  appendLog('tester ready');
  createMessage(
    'system',
    'Ready — chat uses your server LLM from .env (no provider picker needed). Enable Output audio for voice replies.',
  );
}

document.addEventListener('DOMContentLoaded', init);