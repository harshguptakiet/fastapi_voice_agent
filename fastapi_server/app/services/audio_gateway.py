from __future__ import annotations

import base64

from app.schemas.agent import AgentAudioInput


class AudioGateway:
    """Gateway abstraction for HTTP/WebRTC/SIP audio ingress.

    For now this normalizes inbound PCM16 payloads into a consistent in-memory format.
    """

    def normalize(self, payload: AgentAudioInput) -> tuple[bytes, int, str]:
        pcm16 = base64.b64decode(payload.audio_b64)
        return pcm16, payload.sample_rate_hz, payload.transport


audio_gateway = AudioGateway()
