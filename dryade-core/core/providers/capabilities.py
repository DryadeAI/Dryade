"""Provider capabilities and authentication types.

This module defines enums for provider authentication methods and capabilities.
String values enable JSON serialization for API responses and configuration.
"""

from enum import Enum


class AuthType(Enum):
    """Authentication method required by a provider."""

    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    AWS_SIGV4 = "aws_sigv4"
    NONE = "none"

class Capability(Enum):
    """Services that a provider can offer."""

    LLM = "llm"
    EMBEDDING = "embedding"
    AUDIO_ASR = "audio_asr"
    AUDIO_TTS = "audio_tts"
    VISION = "vision"
