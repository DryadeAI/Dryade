"""HuggingFace connector for local embedding model testing and discovery.

Tests that sentence-transformers can load the specified model locally.
No API key or endpoint required -- models download from HuggingFace Hub
and run locally via sentence-transformers.
"""

import asyncio
import logging

from core.providers.connectors.base import ConnectionTestResult, ProviderConnector

logger = logging.getLogger(__name__)

class HuggingFaceConnector(ProviderConnector):
    """Connector for HuggingFace embedding models via sentence-transformers.

    Connection test: Attempts to load the model with SentenceTransformer.
    Model discovery: Returns a static list of popular embedding models.
    """

    # Popular embedding models with their dimensions
    POPULAR_MODELS = {
        "all-MiniLM-L6-v2": 384,
        "all-mpnet-base-v2": 768,
        "BAAI/bge-small-en-v1.5": 384,
        "BAAI/bge-base-en-v1.5": 768,
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": 384,
    }

    def _load_and_test_model(self, model_name: str) -> ConnectionTestResult:
        """Synchronous model loading (runs in thread to avoid blocking event loop).

        Args:
            model_name: HuggingFace model name to load.

        Returns:
            ConnectionTestResult with success/failure and model info.
        """
        try:
            from sentence_transformers import SentenceTransformer

            encoder = SentenceTransformer(model_name)
            dim = encoder.get_sentence_embedding_dimension()
            return ConnectionTestResult(
                success=True,
                message=f"Model '{model_name}' loaded successfully ({dim}d embeddings)",
                models=[model_name],
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                message=f"Failed to load model '{model_name}': {e}",
                models=[],
            )

    async def test_connection(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> ConnectionTestResult:
        """Test that a HuggingFace embedding model can be loaded locally.

        Args:
            api_key: Ignored (no API key needed for local models).
            base_url: Ignored (models run locally).
            **kwargs: May contain 'model' key specifying which model to test.

        Returns:
            ConnectionTestResult with success/failure and model info.
        """
        test_model = kwargs.get("model") or "all-MiniLM-L6-v2"
        return await asyncio.to_thread(self._load_and_test_model, test_model)

    async def discover_models(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> list[str]:
        """Return list of popular HuggingFace embedding models.

        Returns a curated static list -- HuggingFace Hub has thousands
        of models, so we provide well-known options. Users can type
        any valid model name in the Settings UI.

        Args:
            api_key: Ignored (no API key needed).
            base_url: Ignored (models run locally).
            **kwargs: Additional keyword arguments (ignored).

        Returns:
            List of popular embedding model names.
        """
        return list(self.POPULAR_MODELS.keys())
