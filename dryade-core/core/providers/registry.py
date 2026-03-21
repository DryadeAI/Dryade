"""Provider metadata registry.

Central registry of LLM provider metadata including authentication types,
capabilities, base URLs, and model specifications.
"""

from dataclasses import dataclass, field

from core.providers.capabilities import AuthType, Capability

@dataclass
class ModelMetadata:
    """Metadata for a specific model offered by a provider."""

    id: str
    context_length: int | None
    capabilities: list[Capability] = field(default_factory=list)
    supports_streaming: bool = True
    cost_per_1m_input: float | None = None
    cost_per_1m_output: float | None = None

    @property
    def supports_vision(self) -> bool:
        """Check if model supports vision (for backward compatibility)."""
        return Capability.VISION in self.capabilities

@dataclass
class ProviderMetadata:
    """Metadata for an LLM provider."""

    id: str
    display_name: str
    auth_type: AuthType
    base_url: str | None
    requires_api_key: bool
    supports_custom_endpoint: bool
    capabilities: list[Capability]
    models: dict[str, ModelMetadata] = field(default_factory=dict)

# Provider registry - single source of truth for provider metadata
PROVIDER_REGISTRY: dict[str, ProviderMetadata] = {
    "openai": ProviderMetadata(
        id="openai",
        display_name="OpenAI",
        auth_type=AuthType.BEARER_TOKEN,
        base_url="https://api.openai.com/v1",
        requires_api_key=True,
        supports_custom_endpoint=False,
        capabilities=[
            Capability.LLM,
            Capability.EMBEDDING,
            Capability.AUDIO_ASR,
            Capability.AUDIO_TTS,
            Capability.VISION,
        ],
        models={
            # LLM + Vision models
            "gpt-4o": ModelMetadata(
                id="gpt-4o",
                context_length=128000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
            "gpt-4o-mini": ModelMetadata(
                id="gpt-4o-mini",
                context_length=128000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
            "gpt-4-turbo": ModelMetadata(
                id="gpt-4-turbo",
                context_length=128000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
            # LLM only models
            "gpt-4": ModelMetadata(
                id="gpt-4",
                context_length=8192,
                capabilities=[Capability.LLM],
            ),
            "gpt-3.5-turbo": ModelMetadata(
                id="gpt-3.5-turbo",
                context_length=16000,
                capabilities=[Capability.LLM],
            ),
            # Embedding models
            "text-embedding-3-large": ModelMetadata(
                id="text-embedding-3-large",
                context_length=8191,
                capabilities=[Capability.EMBEDDING],
                supports_streaming=False,
            ),
            "text-embedding-3-small": ModelMetadata(
                id="text-embedding-3-small",
                context_length=8191,
                capabilities=[Capability.EMBEDDING],
                supports_streaming=False,
            ),
            "text-embedding-ada-002": ModelMetadata(
                id="text-embedding-ada-002",
                context_length=8191,
                capabilities=[Capability.EMBEDDING],
                supports_streaming=False,
            ),
            # Audio ASR models
            "whisper-1": ModelMetadata(
                id="whisper-1",
                context_length=None,
                capabilities=[Capability.AUDIO_ASR],
                supports_streaming=False,
            ),
            # Audio TTS models
            "tts-1": ModelMetadata(
                id="tts-1",
                context_length=4096,
                capabilities=[Capability.AUDIO_TTS],
            ),
            "tts-1-hd": ModelMetadata(
                id="tts-1-hd",
                context_length=4096,
                capabilities=[Capability.AUDIO_TTS],
            ),
        },
    ),
    "anthropic": ProviderMetadata(
        id="anthropic",
        display_name="Anthropic",
        auth_type=AuthType.BEARER_TOKEN,
        base_url="https://api.anthropic.com/v1",
        requires_api_key=True,
        supports_custom_endpoint=False,
        capabilities=[Capability.LLM, Capability.VISION],
        models={
            # Claude 3.5 models (LLM + Vision)
            "claude-sonnet-4-20250514": ModelMetadata(
                id="claude-sonnet-4-20250514",
                context_length=200000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
            "claude-3-5-sonnet-20241022": ModelMetadata(
                id="claude-3-5-sonnet-20241022",
                context_length=200000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
            "claude-3-5-haiku-20241022": ModelMetadata(
                id="claude-3-5-haiku-20241022",
                context_length=200000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
            # Claude 3 models (LLM + Vision)
            "claude-3-opus-20240229": ModelMetadata(
                id="claude-3-opus-20240229",
                context_length=200000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
            "claude-3-sonnet-20240229": ModelMetadata(
                id="claude-3-sonnet-20240229",
                context_length=200000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
            "claude-3-haiku-20240307": ModelMetadata(
                id="claude-3-haiku-20240307",
                context_length=200000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
        },
    ),
    "google": ProviderMetadata(
        id="google",
        display_name="Google AI",
        auth_type=AuthType.API_KEY,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        requires_api_key=True,
        supports_custom_endpoint=False,
        capabilities=[
            Capability.LLM,
            Capability.EMBEDDING,
            Capability.AUDIO_ASR,
            Capability.AUDIO_TTS,
            Capability.VISION,
        ],
        models={
            # Gemini 2.0 models (LLM + Vision + Audio)
            "gemini-2.0-flash": ModelMetadata(
                id="gemini-2.0-flash",
                context_length=1000000,
                capabilities=[Capability.LLM, Capability.VISION, Capability.AUDIO_ASR],
            ),
            "gemini-2.0-flash-lite": ModelMetadata(
                id="gemini-2.0-flash-lite",
                context_length=1000000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
            # Gemini 1.5 models (LLM + Vision)
            "gemini-1.5-pro": ModelMetadata(
                id="gemini-1.5-pro",
                context_length=2000000,
                capabilities=[Capability.LLM, Capability.VISION, Capability.AUDIO_ASR],
            ),
            "gemini-1.5-flash": ModelMetadata(
                id="gemini-1.5-flash",
                context_length=1000000,
                capabilities=[Capability.LLM, Capability.VISION, Capability.AUDIO_ASR],
            ),
            # Embedding models
            "text-embedding-004": ModelMetadata(
                id="text-embedding-004",
                context_length=2048,
                capabilities=[Capability.EMBEDDING],
                supports_streaming=False,
            ),
            "embedding-001": ModelMetadata(
                id="embedding-001",
                context_length=2048,
                capabilities=[Capability.EMBEDDING],
                supports_streaming=False,
            ),
        },
    ),
    "mistral": ProviderMetadata(
        id="mistral",
        display_name="Mistral AI",
        auth_type=AuthType.BEARER_TOKEN,
        base_url="https://api.mistral.ai/v1",
        requires_api_key=True,
        supports_custom_endpoint=False,
        capabilities=[Capability.LLM, Capability.EMBEDDING, Capability.VISION],
        models={
            # LLM + Vision models
            "pixtral-large-latest": ModelMetadata(
                id="pixtral-large-latest",
                context_length=128000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
            "pixtral-12b-2409": ModelMetadata(
                id="pixtral-12b-2409",
                context_length=128000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
            # LLM only models
            "mistral-large-latest": ModelMetadata(
                id="mistral-large-latest",
                context_length=128000,
                capabilities=[Capability.LLM],
            ),
            "mistral-small-latest": ModelMetadata(
                id="mistral-small-latest",
                context_length=32000,
                capabilities=[Capability.LLM],
            ),
            "codestral-latest": ModelMetadata(
                id="codestral-latest",
                context_length=32000,
                capabilities=[Capability.LLM],
            ),
            "open-mistral-nemo": ModelMetadata(
                id="open-mistral-nemo",
                context_length=128000,
                capabilities=[Capability.LLM],
            ),
            # Embedding models
            "mistral-embed": ModelMetadata(
                id="mistral-embed",
                context_length=8192,
                capabilities=[Capability.EMBEDDING],
                supports_streaming=False,
            ),
        },
    ),
    "cohere": ProviderMetadata(
        id="cohere",
        display_name="Cohere",
        auth_type=AuthType.BEARER_TOKEN,
        base_url="https://api.cohere.ai/v1",
        requires_api_key=True,
        supports_custom_endpoint=False,
        capabilities=[Capability.LLM, Capability.EMBEDDING],
        models={
            # LLM models
            "command-r-plus": ModelMetadata(
                id="command-r-plus",
                context_length=128000,
                capabilities=[Capability.LLM],
            ),
            "command-r": ModelMetadata(
                id="command-r",
                context_length=128000,
                capabilities=[Capability.LLM],
            ),
            "command-light": ModelMetadata(
                id="command-light",
                context_length=4096,
                capabilities=[Capability.LLM],
            ),
            "command": ModelMetadata(
                id="command",
                context_length=4096,
                capabilities=[Capability.LLM],
            ),
            # Embedding models
            "embed-english-v3.0": ModelMetadata(
                id="embed-english-v3.0",
                context_length=512,
                capabilities=[Capability.EMBEDDING],
                supports_streaming=False,
            ),
            "embed-multilingual-v3.0": ModelMetadata(
                id="embed-multilingual-v3.0",
                context_length=512,
                capabilities=[Capability.EMBEDDING],
                supports_streaming=False,
            ),
            "embed-english-light-v3.0": ModelMetadata(
                id="embed-english-light-v3.0",
                context_length=512,
                capabilities=[Capability.EMBEDDING],
                supports_streaming=False,
            ),
        },
    ),
    "azure_openai": ProviderMetadata(
        id="azure_openai",
        display_name="Azure OpenAI",
        auth_type=AuthType.BEARER_TOKEN,
        base_url=None,  # User-configured endpoint
        requires_api_key=True,
        supports_custom_endpoint=True,
        capabilities=[
            Capability.LLM,
            Capability.EMBEDDING,
            Capability.AUDIO_ASR,
            Capability.AUDIO_TTS,
            Capability.VISION,
        ],
        models={},  # User-configured deployment names
    ),
    "bedrock": ProviderMetadata(
        id="bedrock",
        display_name="AWS Bedrock",
        auth_type=AuthType.AWS_SIGV4,
        base_url=None,  # Region-specific endpoint
        requires_api_key=False,  # Uses AWS credentials
        supports_custom_endpoint=False,
        capabilities=[Capability.LLM, Capability.EMBEDDING, Capability.VISION],
        models={
            # Claude models via Bedrock (LLM + Vision)
            "anthropic.claude-3-5-sonnet-20241022-v2:0": ModelMetadata(
                id="anthropic.claude-3-5-sonnet-20241022-v2:0",
                context_length=200000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
            "anthropic.claude-3-opus-20240229-v1:0": ModelMetadata(
                id="anthropic.claude-3-opus-20240229-v1:0",
                context_length=200000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
            "anthropic.claude-3-sonnet-20240229-v1:0": ModelMetadata(
                id="anthropic.claude-3-sonnet-20240229-v1:0",
                context_length=200000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
            "anthropic.claude-3-haiku-20240307-v1:0": ModelMetadata(
                id="anthropic.claude-3-haiku-20240307-v1:0",
                context_length=200000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
            # Amazon Titan LLM models
            "amazon.titan-text-premier-v1:0": ModelMetadata(
                id="amazon.titan-text-premier-v1:0",
                context_length=32000,
                capabilities=[Capability.LLM],
            ),
            "amazon.titan-text-express-v1": ModelMetadata(
                id="amazon.titan-text-express-v1",
                context_length=8192,
                capabilities=[Capability.LLM],
            ),
            # Amazon Titan Embedding models
            "amazon.titan-embed-text-v2:0": ModelMetadata(
                id="amazon.titan-embed-text-v2:0",
                context_length=8192,
                capabilities=[Capability.EMBEDDING],
                supports_streaming=False,
            ),
            "amazon.titan-embed-text-v1": ModelMetadata(
                id="amazon.titan-embed-text-v1",
                context_length=8192,
                capabilities=[Capability.EMBEDDING],
                supports_streaming=False,
            ),
            # Meta Llama models
            "meta.llama3-70b-instruct-v1:0": ModelMetadata(
                id="meta.llama3-70b-instruct-v1:0",
                context_length=8192,
                capabilities=[Capability.LLM],
            ),
            "meta.llama3-8b-instruct-v1:0": ModelMetadata(
                id="meta.llama3-8b-instruct-v1:0",
                context_length=8192,
                capabilities=[Capability.LLM],
            ),
        },
    ),
    "ollama": ProviderMetadata(
        id="ollama",
        display_name="Ollama",
        auth_type=AuthType.NONE,
        base_url="http://localhost:11434",
        requires_api_key=False,
        supports_custom_endpoint=True,
        capabilities=[Capability.LLM, Capability.EMBEDDING],
        models={},  # Discovered dynamically via /api/tags
    ),
    "vllm": ProviderMetadata(
        id="vllm",
        display_name="vLLM",
        auth_type=AuthType.NONE,
        base_url="http://localhost:8000",
        requires_api_key=False,
        supports_custom_endpoint=True,
        capabilities=[Capability.LLM, Capability.AUDIO_ASR],
        models={},  # Discovered dynamically via /v1/models
    ),
    # --- OpenAI-compatible cloud providers ---
    "deepseek": ProviderMetadata(
        id="deepseek",
        display_name="DeepSeek",
        auth_type=AuthType.BEARER_TOKEN,
        base_url="https://api.deepseek.com/v1",
        requires_api_key=True,
        supports_custom_endpoint=False,
        capabilities=[Capability.LLM],
        models={
            "deepseek-chat": ModelMetadata(
                id="deepseek-chat",
                context_length=64000,
                capabilities=[Capability.LLM],
            ),
            "deepseek-reasoner": ModelMetadata(
                id="deepseek-reasoner",
                context_length=64000,
                capabilities=[Capability.LLM],
            ),
        },
    ),
    "qwen": ProviderMetadata(
        id="qwen",
        display_name="Qwen (DashScope)",
        auth_type=AuthType.BEARER_TOKEN,
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        requires_api_key=True,
        supports_custom_endpoint=True,
        capabilities=[Capability.LLM, Capability.VISION],
        models={
            "qwen-max": ModelMetadata(
                id="qwen-max",
                context_length=32000,
                capabilities=[Capability.LLM],
            ),
            "qwen-plus": ModelMetadata(
                id="qwen-plus",
                context_length=131072,
                capabilities=[Capability.LLM],
            ),
            "qwen-turbo": ModelMetadata(
                id="qwen-turbo",
                context_length=131072,
                capabilities=[Capability.LLM],
            ),
            "qwen-vl-plus": ModelMetadata(
                id="qwen-vl-plus",
                context_length=32000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
            "qwen-vl-max": ModelMetadata(
                id="qwen-vl-max",
                context_length=32000,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
        },
    ),
    "moonshot": ProviderMetadata(
        id="moonshot",
        display_name="Kimi (Moonshot)",
        auth_type=AuthType.BEARER_TOKEN,
        base_url="https://api.moonshot.ai/v1",
        requires_api_key=True,
        supports_custom_endpoint=True,
        capabilities=[Capability.LLM],
        models={
            "moonshot-v1-8k": ModelMetadata(
                id="moonshot-v1-8k",
                context_length=8000,
                capabilities=[Capability.LLM],
            ),
            "moonshot-v1-32k": ModelMetadata(
                id="moonshot-v1-32k",
                context_length=32000,
                capabilities=[Capability.LLM],
            ),
            "moonshot-v1-128k": ModelMetadata(
                id="moonshot-v1-128k",
                context_length=128000,
                capabilities=[Capability.LLM],
            ),
        },
    ),
    "xai": ProviderMetadata(
        id="xai",
        display_name="xAI (Grok)",
        auth_type=AuthType.BEARER_TOKEN,
        base_url="https://api.x.ai/v1",
        requires_api_key=True,
        supports_custom_endpoint=False,
        capabilities=[Capability.LLM, Capability.VISION],
        models={
            "grok-3": ModelMetadata(
                id="grok-3",
                context_length=131072,
                capabilities=[Capability.LLM],
            ),
            "grok-3-mini": ModelMetadata(
                id="grok-3-mini",
                context_length=131072,
                capabilities=[Capability.LLM],
            ),
            "grok-2": ModelMetadata(
                id="grok-2",
                context_length=131072,
                capabilities=[Capability.LLM],
            ),
            "grok-2-vision-1212": ModelMetadata(
                id="grok-2-vision-1212",
                context_length=32768,
                capabilities=[Capability.LLM, Capability.VISION],
            ),
        },
    ),
    "together_ai": ProviderMetadata(
        id="together_ai",
        display_name="Together AI",
        auth_type=AuthType.BEARER_TOKEN,
        base_url="https://api.together.xyz/v1",
        requires_api_key=True,
        supports_custom_endpoint=False,
        capabilities=[Capability.LLM, Capability.EMBEDDING],
        models={
            "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo": ModelMetadata(
                id="meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
                context_length=130815,
                capabilities=[Capability.LLM],
            ),
            "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo": ModelMetadata(
                id="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                context_length=131072,
                capabilities=[Capability.LLM],
            ),
            "mistralai/Mixtral-8x22B-Instruct-v0.1": ModelMetadata(
                id="mistralai/Mixtral-8x22B-Instruct-v0.1",
                context_length=65536,
                capabilities=[Capability.LLM],
            ),
            "Qwen/Qwen2.5-72B-Instruct-Turbo": ModelMetadata(
                id="Qwen/Qwen2.5-72B-Instruct-Turbo",
                context_length=32768,
                capabilities=[Capability.LLM],
            ),
        },
    ),
    "groq": ProviderMetadata(
        id="groq",
        display_name="Groq",
        auth_type=AuthType.BEARER_TOKEN,
        base_url="https://api.groq.com/openai/v1",
        requires_api_key=True,
        supports_custom_endpoint=False,
        capabilities=[Capability.LLM, Capability.VISION, Capability.AUDIO_ASR],
        models={
            "llama-3.3-70b-versatile": ModelMetadata(
                id="llama-3.3-70b-versatile",
                context_length=131072,
                capabilities=[Capability.LLM],
            ),
            "llama-3.1-8b-instant": ModelMetadata(
                id="llama-3.1-8b-instant",
                context_length=131072,
                capabilities=[Capability.LLM],
            ),
            "mixtral-8x7b-32768": ModelMetadata(
                id="mixtral-8x7b-32768",
                context_length=32768,
                capabilities=[Capability.LLM],
            ),
            "gemma2-9b-it": ModelMetadata(
                id="gemma2-9b-it",
                context_length=8192,
                capabilities=[Capability.LLM],
            ),
            "whisper-large-v3": ModelMetadata(
                id="whisper-large-v3",
                context_length=None,
                capabilities=[Capability.AUDIO_ASR],
                supports_streaming=False,
            ),
        },
    ),
    "litellm_proxy": ProviderMetadata(
        id="litellm_proxy",
        display_name="LiteLLM Proxy",
        auth_type=AuthType.BEARER_TOKEN,
        base_url="http://localhost:4000/v1",
        requires_api_key=False,
        supports_custom_endpoint=True,
        capabilities=[Capability.LLM, Capability.EMBEDDING],
        models={},  # Discovered dynamically from proxy
    ),
    # --- Local embedding provider ---
    "huggingface": ProviderMetadata(
        id="huggingface",
        display_name="HuggingFace",
        auth_type=AuthType.NONE,
        base_url=None,
        requires_api_key=False,
        supports_custom_endpoint=False,
        capabilities=[Capability.EMBEDDING],
        models={
            "all-MiniLM-L6-v2": ModelMetadata(
                id="all-MiniLM-L6-v2",
                context_length=256,
                capabilities=[Capability.EMBEDDING],
                supports_streaming=False,
            ),
            "all-mpnet-base-v2": ModelMetadata(
                id="all-mpnet-base-v2",
                context_length=384,
                capabilities=[Capability.EMBEDDING],
                supports_streaming=False,
            ),
            "BAAI/bge-small-en-v1.5": ModelMetadata(
                id="BAAI/bge-small-en-v1.5",
                context_length=512,
                capabilities=[Capability.EMBEDDING],
                supports_streaming=False,
            ),
            "BAAI/bge-base-en-v1.5": ModelMetadata(
                id="BAAI/bge-base-en-v1.5",
                context_length=512,
                capabilities=[Capability.EMBEDDING],
                supports_streaming=False,
            ),
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": ModelMetadata(
                id="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                context_length=128,
                capabilities=[Capability.EMBEDDING],
                supports_streaming=False,
            ),
        },
    ),
}

def get_provider(provider_id: str) -> ProviderMetadata | None:
    """Get provider metadata by ID.

    Args:
        provider_id: Provider identifier (e.g., "openai", "anthropic")

    Returns:
        Provider metadata if found, None otherwise
    """
    return PROVIDER_REGISTRY.get(provider_id)

def get_models_by_capability(provider_id: str, capability: Capability) -> list[ModelMetadata]:
    """Get models from a provider that support a specific capability.

    Args:
        provider_id: Provider identifier
        capability: The capability to filter by

    Returns:
        List of models that support the capability
    """
    provider = get_provider(provider_id)
    if not provider:
        return []

    return [model for model in provider.models.values() if capability in model.capabilities]

def get_model_ids_by_capability(provider_id: str, capability: Capability) -> list[str]:
    """Get model IDs from a provider that support a specific capability.

    Args:
        provider_id: Provider identifier
        capability: The capability to filter by

    Returns:
        List of model IDs that support the capability
    """
    return [model.id for model in get_models_by_capability(provider_id, capability)]
